# Deployment

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

Everything that matters is in PostgreSQL — calculations, resolutions, the GSTIN master,
the audit trail. The uploaded spreadsheets are not needed to reproduce a run, because
each run stores its own rows and the masters it used.

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
