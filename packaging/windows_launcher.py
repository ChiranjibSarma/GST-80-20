"""Self-contained Windows installer/launcher. Never invokes system Python or pip."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser


def local_root():
    return Path(os.environ['LOCALAPPDATA']) / 'GST-80-20'


def configure(root):
    # An explicit test/data directory is isolated from any installed .env.
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    os.environ['VAR_DIR'] = str(root / 'var')
    os.environ['GST8020_DATA_DIR'] = str(root)
    from dotenv import load_dotenv
    load_dotenv(root / '.env')
    os.environ.setdefault('DATABASE_URL', f"sqlite:///{(root / 'var' / 'finops.db').as_posix()}")
    if not os.environ['DATABASE_URL'].startswith('sqlite:///'):
        raise RuntimeError('The offline EXE requires a local SQLite database. Existing configuration has not been changed.')
    os.environ['UPLOAD_DIR'] = str(root / 'var' / 'uploads')
    os.environ.setdefault('SESSION_HTTPS_ONLY', '0')
    return root


class InstanceLock:
    def __init__(self, root):
        api = ctypes.windll.kernel32
        api.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        api.CreateMutexW.restype = ctypes.c_void_p
        api.CloseHandle.argtypes = [ctypes.c_void_p]
        token = hashlib.sha256(str(root).lower().encode()).hexdigest()
        self.handle = api.CreateMutexW(None, False, 'Local\\GST8020-' + token)
        if not self.handle:
            raise ctypes.WinError()
        if api.GetLastError() == 183:
            api.CloseHandle(self.handle)
            self.handle = None
            raise RuntimeError('This installation is already running. Use its existing portal window.')

    def close(self):
        if self.handle:
            ctypes.windll.kernel32.CloseHandle(self.handle)
            self.handle = None


def bind_port(first):
    for port in range(first, 65536):
        sock = socket.socket()
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            sock.bind(('127.0.0.1', port))
            sock.listen(128)
            return sock, port
        except OSError:
            sock.close()
    raise RuntimeError('No available port found.')


def install_payload(target, shortcut=True):
    target = Path(target).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    source = Path(sys.executable).resolve()
    if source != target:
        staged = target.with_suffix('.new.exe')
        shutil.copy2(source, staged)
        os.replace(staged, target)
    if shortcut:
        link = Path(os.environ['APPDATA']) / 'Microsoft/Windows/Start Menu/Programs/GST 80-20.lnk'
        escape = lambda value: str(value).replace("'", "''")
        code = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut('" + escape(link) + "');"
                "$s.TargetPath='" + escape(target) + "';$s.Arguments='--run';"
                "$s.WorkingDirectory='" + escape(target.parent) + "';$s.Save()")
        subprocess.run([str(Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'),
                        '-NoProfile', '-NonInteractive', '-Command', code], check=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    return target


def install():
    import tkinter as tk
    from tkinter import messagebox
    window = tk.Tk()
    window.withdraw()
    target = Path(os.environ['LOCALAPPDATA']) / 'Programs' / 'GST-80-20' / 'GST-80-20.exe'
    if not messagebox.askyesno('GST 80-20 setup',
            f'Install the offline portal for this Windows user?\n\n{target.parent}\n\n'
            'Python, Git and internet are not required. Existing client data and licences are retained.'):
        window.destroy()
        return
    try:
        install_payload(target)
        messagebox.showinfo('Installed', 'Installed successfully. The portal launcher will now open.\n'
            'Send its installation ID to the licence issuer and import the separate licence JSON.\n'
            'Fresh-install login: admin@oswalgroup.net / admin123456789. Change the password after login.')
        subprocess.Popen([str(target), '--run'], cwd=target.parent)
    except Exception as exc:
        messagebox.showerror('Installation did not complete', str(exc) + '\nClose any running portal before upgrading.')
    finally:
        window.destroy()


def launch(args):
    root = configure(args.data_dir or local_root())
    lock = InstanceLock(root)
    log = root / 'var' / 'launcher.log'
    log.parent.mkdir(parents=True, exist_ok=True)
    # Windowed bundles have no stdout/stderr; libraries still need streams.
    output = log.open('a', encoding='utf-8', buffering=1)
    sys.stdout = sys.stderr = output
    from app.main import app, startup
    from app.license import installation_id, verify_license_file, LICENSE_FILE
    from app.db import engine
    import uvicorn
    startup()
    identity = installation_id()
    sock, port = bind_port(args.port)
    url = f'http://127.0.0.1:{port}'
    (root / 'var' / 'launcher-status.json').write_text(json.dumps(
        {'url': url, 'installation_id': identity, 'frozen': bool(getattr(sys, 'frozen', False)),
         'executable': sys.executable, 'pid': os.getpid()}), encoding='utf-8')
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port,
        workers=1, loop='asyncio', http='h11', ws='none', log_level='warning'))
    try:
        if args.serve:
            server.run(sockets=[sock])
            return
        import tkinter as tk
        from tkinter import filedialog, messagebox, simpledialog
        window = tk.Tk()
        window.title('GST 80-20 — offline portal')
        window.geometry('660x340')
        tk.Label(window, text='GST 80-20 Finance Operations Portal', font=('Arial', 16)).pack(pady=15)
        tk.Label(window, text='Installation ID (send to the licence issuer):').pack()
        value = tk.Entry(window, width=54)
        value.insert(0, identity)
        value.configure(state='readonly')
        value.pack(pady=5)
        tk.Label(window, text=f'Data: {root / "var"}\nPortal: {url}', wraplength=620).pack(pady=10)
        status = tk.StringVar(value='Starting the portal…')
        tk.Label(window, textvariable=status).pack(pady=8)

        def import_license():
            path = filedialog.askopenfilename(title='Select the separately supplied licence JSON', filetypes=[('Licence JSON', '*.json')])
            if not path:
                return
            try:
                verify_license_file(path, identity)
                if LICENSE_FILE.exists() and not messagebox.askyesno('Replace licence?', 'Replace the installed licence with this verified licence? Existing activation dates are not reset.'):
                    return
                staged = LICENSE_FILE.with_suffix('.new.json')
                shutil.copyfile(path, staged)
                os.replace(staged, LICENSE_FILE)
                status.set('Licence imported. Open the portal to activate/use it.')
            except Exception as exc:
                messagebox.showerror('Licence rejected', str(exc))

        def backup_folder():
            path = filedialog.askdirectory(title='Choose an existing local or mirrored Drive backup folder')
            if not path:
                return
            from dotenv import set_key
            set_key(root / '.env', 'BACKUP_DIR', Path(path).as_posix())
            messagebox.showinfo('Backup folder saved', 'Close and reopen the launcher to use this backup folder. The live database stays local.')

        def recover():
            from app.recovery import discover_backups, validate_backup, restore_backup
            from app.config import VAR_DIR, BACKUP_DIR
            from app.db import SessionLocal
            from app.models import Run
            from sqlalchemy import select, func
            with SessionLocal() as db:
                if db.scalar(select(func.count(Run.id))):
                    messagebox.showinfo('Current data retained', 'Existing calculations cannot be overwritten by initialization.')
                    return
            options = []
            for path in discover_backups([VAR_DIR / 'backups', BACKUP_DIR]):
                try:
                    if validate_backup(path):
                        options.append(path)
                except Exception:
                    pass
            if not options:
                return
            listing = '\n'.join(f'{i}. {p.name}' for i, p in enumerate(options, 1))
            choice = simpledialog.askinteger('Previous data available', 'Restore a backup, or Cancel to keep the current database:\n' + listing,
                                            minvalue=1, maxvalue=len(options))
            if choice and messagebox.askyesno('Confirm restore', 'Restore ALL data and original accounts/passwords from this backup? The current empty database is retained in recovery/.'):
                engine.dispose()
                restore_backup(options[choice - 1], engine.url.database, VAR_DIR / 'recovery')
                password = VAR_DIR / 'first-admin-password.txt'
                if password.exists():
                    password.rename(VAR_DIR / ('first-admin-password.pre-restore-' + str(time.time_ns()) + '.txt'))

        tk.Button(window, text='Open portal', command=lambda: webbrowser.open(url)).pack(pady=4)
        tk.Button(window, text='Import licence JSON', command=import_license).pack(pady=4)
        tk.Button(window, text='Choose backup folder', command=backup_folder).pack(pady=4)
        recover()
        worker = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
        worker.start()

        def ready(attempt=0):
            if server.started:
                status.set('Portal ready. No licence/expired licence means read-only access.')
                if not args.no_browser:
                    webbrowser.open(url)
            elif worker.is_alive() and attempt < 120:
                window.after(250, lambda: ready(attempt + 1))
            else:
                status.set(f'Startup failed. Review {log}')

        def stop():
            server.should_exit = True
            worker.join(timeout=10)
            window.destroy()

        window.protocol('WM_DELETE_WINDOW', stop)
        ready()
        window.mainloop()
    finally:
        sock.close()
        engine.dispose()
        lock.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--serve', action='store_true', help='Headless local server, for automated tests')
    parser.add_argument('--data-dir')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--install-only', action='store_true', help='Noninteractive payload installation, for automated deployment/tests')
    parser.add_argument('--install-dir', help='Explicit executable destination for --install-only')
    parser.add_argument('--no-shortcut', action='store_true')
    parser.add_argument('--check-gui', action='store_true', help='Verify the bundled Tk runtime without installing')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('Port must be between 1 and 65535')
    if args.check_gui:
        import tkinter as tk
        window = tk.Tk()
        window.withdraw()
        window.update()
        window.destroy()
    elif args.install_only and getattr(sys, 'frozen', False):
        target_dir = Path(args.install_dir) if args.install_dir else Path(os.environ['LOCALAPPDATA']) / 'Programs/GST-80-20'
        install_payload(target_dir / 'GST-80-20.exe', shortcut=not args.no_shortcut)
    elif args.run or args.serve:
        launch(args)
    elif getattr(sys, 'frozen', False):
        install()
    else:
        parser.error('Build the frozen EXE before running the installer.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        traceback.print_exc()
        if not '--serve' in sys.argv:
            import tkinter as tk
            from tkinter import messagebox
            w = tk.Tk()
            w.withdraw()
            messagebox.showerror('GST 80-20 could not start', str(exc))
            w.destroy()
        raise SystemExit(1)
