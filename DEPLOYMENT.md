# Deployment

## Windows PCs: sequential handoff through Google Drive

The client has no shared server. Each operator runs `deploy.bat` on their own PC,
but **only one operator at a time**. Configure the same existing Google Drive
**mirrored** folder when prompted. The live `var/finops.db` stays on that PC;
`gst8020-current.sqlite3` in Drive is a *closed, consistent handoff copy*.
The Drive folder should be accessible only to the authorized client users.

1. Before starting, close the portal on every other PC and wait until Google
   Drive on the previous PC and this PC both report **Up to date**.
2. Start `deploy.bat`. It installs dependencies, then loads the latest current
   copy into the local SQLite database **before** opening the portal. On the
   first PC only, confirm `FIRST` to initialize the current copy. On a second
   PC's first load, confirm `ADOPT`: its initial local database is preserved
   as `var/finops-before-pull-*.sqlite3` before replacement. Use the shared
   database's administrator credentials, not the second PC's bootstrap ones.
3. Work normally. A dated, integrity-checked snapshot is written after the
   first successful calculation of each day to the same Drive folder. This is
   a recovery point, not the current handoff file.
4. Close the BAT window with Ctrl+C. The launcher publishes a consistent
   current copy after the web server stops. **Do not let the next PC start until
   Drive reports Up to date** on both PCs.

If the launcher says **HANDOFF FAILED**, do not let another PC start. Preserve
the local `var/finops.db` and Drive folder, then reconcile manually. The launcher
refuses to overwrite local work changed since its last handoff, or a visible
newer current copy in Drive. A failed or killed BAT session may leave work only
in the local database. To retry a publish after the app has stopped, run
`.venv\Scripts\python.exe -m app.handoff publish` on that PC. Do **not** manually
replace the current file or delete the local handoff state to bypass a conflict.

This is **not live multi-user synchronization**. Google Drive has no transaction
lock across the PCs, and a not-yet-synced remote edit is invisible to the
launcher. Sequential use and completed sync are operational requirements. If
two operators must work simultaneously, use one PC hosting the app over LAN
or a proper shared database service instead. If the client has no internet,
the mirrored copy remains local until Drive can sync; cross-PC handoff must wait.

## Offline 14-day licences

Each PC has a separate installation ID (`var/installation-id`, also printed by
the installer and shown under Administration → Licence). Send that ID to the
licence issuer. The issuer generates a signed `license.json` bound to that ID
and gives it to the client to put at `var/license.json` on that PC. Restart or
refresh the portal. The 14-day term starts when that valid licence is first
used. After expiry, the portal allows historical viewing and exports but
rejects new calculations and other business writes. An invalid/missing licence
also leaves the portal read-only. This is an offline commercial control, not
tamper-proof protection against someone with source-code and clock access.

The issuer keeps the Ed25519 private key **off client PCs and out of Git**.
Issuer-only commands (run from a protected machine, after installing
`requirements.txt`):

```powershell
python issue_license.py keygen --private-key C:\issuer-only\gst8020-private.pem --public-key app\license_public_key.pem
python issue_license.py issue --private-key C:\issuer-only\gst8020-private.pem --installation-id <CLIENT-PC-ID> --customer "Client name" --output C:\issuer-only\license.json
```

Only `app/license_public_key.pem` ships with the client package. Never run
`keygen` again after distributing the public key: it would invalidate existing
licences. Protect both the issuer private key and delivered licence files.

---

The application is a Python ASGI web app with a PostgreSQL database. It serves every
asset itself — no CDN, no web fonts, no outbound internet — so it runs on an isolated
server on the client's network.

**For a normal install, use `QUICKSTART.md` — one command does everything below.**
This document is for the parts the installer deliberately leaves to you (HTTPS, backups)
and for anyone who would rather set it up by hand.

---

## 1. What the server needs

| | |
|---|---|
| Python | 3.11 or newer |
| PostgreSQL | 13 or newer — optional; without it the portal runs on a local SQLite file |
| Disk | ~200 MB for the app, plus the database. One month is roughly 1,200 stored rows |
| Network | Inbound HTTP/HTTPS only. No outbound access required |

---

## 2. The one-command install

```bash
sudo ./install.sh          # Linux/macOS
.\install.ps1              # Windows Server, from an elevated PowerShell
```

It checks Python, creates `.venv`, installs the dependencies, provisions the PostgreSQL
role and database, writes `.env` with a generated `SECRET_KEY`, creates the first
administrator with a generated password, registers a service, and verifies the portal
answers on its port before reporting success. It stops with a plain explanation if any
step cannot complete.

Useful options:

| | |
|---|---|
| `--port 9000` | serve on a different port |
| `--sqlite` | skip PostgreSQL even if it is installed |
| `--no-service` | install without registering a startup service |
| `--uninstall` | remove the service; the database, `var/` and `.env` are left alone |

Running it again upgrades in place. It keeps an existing `.env` untouched — including the
database password — so a re-install never breaks a working configuration.

### Air-gapped servers

`pip` is the only step that wants the internet. On a machine that has it, running the same
operating system and Python version as the server:

```bash
./make-offline-bundle.sh
```

That fills `wheelhouse/` with every dependency. Copy the whole folder to the server and run
the installer there — it finds `wheelhouse/` and installs from it without reaching out.
Python wheels are built per platform, so a bundle made on macOS will not install on Linux.

---

## 3. Setting it up by hand

Skip this if you used the installer.

```sql
CREATE ROLE finops LOGIN PASSWORD 'choose-a-strong-password';
CREATE DATABASE finops OWNER finops;
```

On PostgreSQL 15 and newer, a role no longer gets `CREATE` on the `public` schema
automatically. If you create the database as another user, also run, connected to it:

```sql
GRANT ALL ON SCHEMA public TO finops;
```

Then:

```bash
python -m venv .venv
. .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

```
DATABASE_URL=postgresql+psycopg2://finops:choose-a-strong-password@localhost:5432/finops
SECRET_KEY=<paste the output of the command below>
SESSION_HTTPS_ONLY=1
BOOTSTRAP_ADMIN_EMAIL=chiranjib.sarma@protivitiglobal.in
ORG_NAME=Oswal Group
```

Generate the secret key — it signs session cookies, so everyone is signed out if it
changes, and sessions can be forged if it leaks:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Every setting has a working default, so a missing `.env` is not a failure: the application
generates a secret key into `var/secret.key`, falls back to a SQLite file at
`var/finops.db`, and generates the first administrator's password into
`var/first-admin-password.txt`. That file is deleted automatically once the administrator
changes their password.

The tables are created on first start. No migration step is needed for a new install.

---

## 4. Run it

The installer already registers a service — systemd on Linux, a startup task on Windows.
What it deliberately does not do is terminate TLS, because that needs your certificate.
Put a reverse proxy in front, as below, and set `SESSION_HTTPS_ONLY=1` once it is serving
over HTTPS.

### Linux — systemd behind nginx

The installer writes this file for you. It is reproduced here so you can see what it does
and adjust it.

`/etc/systemd/system/finops.service`:

```ini
[Unit]
Description=Finance Operations Portal
After=network.target postgresql.service

[Service]
User=finops
WorkingDirectory=/opt/finops
EnvironmentFile=/opt/finops/.env
ExecStart=/opt/finops/.venv/bin/uvicorn app.main:app \
          --host 127.0.0.1 --port 8080 --workers 4 --proxy-headers
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now finops
```

nginx in front — note the upload limit, because the Tally exports are a few hundred
kilobytes each but grow with history:

```nginx
server {
    listen 443 ssl;
    server_name finops.oswalgroup.local;
    ssl_certificate     /etc/ssl/certs/finops.crt;
    ssl_certificate_key /etc/ssl/private/finops.key;

    client_max_body_size 64M;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;          # a first run on a large month takes a while
    }
}
```

### Windows Server — as a service behind IIS

`uvicorn` runs fine on Windows. Register it with [NSSM](https://nssm.cc/) or
`sc.exe` so it starts with the machine:

```
nssm install FinOpsPortal "C:\finops\.venv\Scripts\uvicorn.exe" ^
      "app.main:app --host 127.0.0.1 --port 8080 --workers 4 --proxy-headers"
nssm set FinOpsPortal AppDirectory C:\finops
nssm start FinOpsPortal
```

Then put IIS in front with **Application Request Routing** reverse-proxying to
`http://127.0.0.1:8080`, and raise the request size limit
(`Request Filtering → Edit Feature Settings → Maximum allowed content length`) to at
least 64 MB.

If IIS is not available, point `uvicorn` at the network interface directly and let
Windows Firewall control who can reach it:

```
nssm set FinOpsPortal AppParameters ^
    "app.main:app --host 0.0.0.0 --port 8080 --workers 4"
```

Run it behind a reverse proxy in production either way, so TLS terminates somewhere
that holds the certificate.

### Serve over HTTPS

Set `SESSION_HTTPS_ONLY=1` once TLS terminates in front of the app. The session cookie
is then only sent over HTTPS. Leave it `0` for a plain-HTTP pilot, or sign-in will not
work.

---

## 5. Verify the install

```bash
curl http://127.0.0.1:8080/healthz     # -> ok
```

Then in a browser: sign in, go to **GST 80:20 → New calculation**, upload a known month,
and check the headline percentage against the last figure the team calculated by hand.

---

## 6. Backups

Calculations, resolutions, the GSTIN master, the audit trail, and licence
activations are in the database. The uploaded spreadsheets are not needed to
reproduce a saved run, because each run stores its own rows and masters.

For the Windows-PC workflow above, `BACKUP_DIR` points to the client's existing
mirrored Drive folder. A successful calculation creates one dated SQLite
snapshot per PC per local calendar day after its first run. The current handoff
copy is separate and is refreshed when the BAT session ends normally. Check
that Google Drive has actually synced; a successful local file copy does not
confirm upload to Google's cloud. Keep historical dated backups rather than
relying solely on the current copy. Test restoration on a spare PC.

For a PostgreSQL deployment, the app also attempts a daily `pg_dump` after the
first successful run; `pg_dump` must be installed and on PATH. A manual backup:

```bash
pg_dump -Fc -U finops finops > /backups/finops-$(date +%F).dump
```

Restore:

```bash
pg_restore -U finops -d finops --clean /backups/finops-2026-09-01.dump
```

Keep at least one backup per financial year end — the audit trail is the record of who
changed which figure, and it should outlive the assessment period.

---

## 7. Upgrading

Take a backup, replace the application files, and run the installer again:

```bash
sudo ./install.sh
```

It reuses the existing environment, installs any new dependencies, keeps your `.env` and
its database password, and restarts the service. By hand instead:

```bash
sudo systemctl stop finops
. .venv/bin/activate && pip install -r requirements.txt
sudo systemctl start finops
```

New columns are not added automatically by the app beyond the initial table creation. If
a future version changes the schema, that release will ship its migration SQL alongside
these notes.

---

## 8. Adding the next module

The portal reads its home page from `app/catalogue.py`. To add a module:

1. Add its entry to `SOLUTIONS` with `status: "live"` and a `url`.
2. Create `app/routers/<module>.py` with an `APIRouter(prefix="/<module>")`.
3. Mount it in `app/main.py` with `app.include_router(...)`.

Sign-in, roles, the audit helper and the shared creditors master are already available
to it — see `app/routers/gst8020.py` as the worked example.
