# Client setup guide — GST 80:20 Portal

## 1. Files to receive

Receive these two files from the supplier:

- `install_from_zip.bat`
- `GST-80-20-client.zip`

Download the actual files from GitHub using **Download raw file**, not the
GitHub web page. Keep the ZIP unopened; the BAT extracts it automatically.
The signed licence JSON is supplied separately after your installation ID is
known. Never request or accept the issuer's signing key or licence-generator tools.

## 2. Requirements

- Windows with PowerShell 5.1 or newer.
- Python 3.11-3.13 (3.12 recommended; 3.14 is not validated for this package). The installer attempts a per-user Python 3.12 installation
  through Windows Package Manager (`winget`) if Python is missing. If company
  policy blocks this, ask IT to install Python and select **Add Python to PATH**.
- Internet during installation for Python/dependencies, or a compatible offline
  dependency bundle supplied by IT. Normal application use and licensing are offline.
- Permission to run BAT/PowerShell files and write to your local user profile.

`deploy.bat` is the source-based route only; it never launches the separate
single-file EXE. Use the EXE guide for a no-Python/offline client PC. For a
locked-down BAT deployment, ask IT to preinstall Python 3.12 and provide a
matching `wheelhouse/` inside the source folder. Set `GST8020_PYTHON` to that
Python's full `python.exe` path if multiple Python versions are installed.
Set `GST8020_NO_AUTO_INSTALL=1` to forbid the BAT from invoking winget.
The BAT requires a short local installation path. A deeply nested OneDrive
checkout can fail at pip install with Windows `WinError 206`; the launcher
now rejects such paths before modifying the environment.

Each installation uses its own local SQLite database. Separate PCs do not share
or synchronize live data. Google Drive is an optional backup destination only.

## 3. First installation

1. Double-click `install_from_zip.bat`. If Windows security policy blocks it,
   ask IT to review the files; do not disable corporate security controls.
2. At **Repository ZIP**, enter the complete ZIP path. You can drag the ZIP
   from File Explorer into the console, then press Enter.
3. Wait for Python/dependency setup, database preparation, and the health check.
   The application is installed at `%LOCALAPPDATA%\GST-80-20`, outside Drive.
4. At **Backup folder**, optionally enter an existing client-controlled Google
   Drive **mirrored** folder. Leave blank for local `var\backups`. Drive must
   already be configured on this PC; the installer does not create or share it.
5. If previous backups are found and the current database has no calculations,
   choose a backup number and type `RESTORE`, or press Enter to start fresh.
   Close all other copies of the application before recovery.
6. Copy the displayed **Installation ID** and send it to the licence issuer.
7. If you do not yet have the licence, leave **Licence JSON path** blank. Setup
   remains prepared and can be resumed later. The 14-day licence has not started.

Do not rename or delete the installed `var` folder. It contains the database,
installation ID, configuration-related files, and backups.

## 4. Activate the separately supplied licence

1. Receive the signed licence JSON issued specifically for the displayed ID.
2. Double-click the same `install_from_zip.bat` again. It reuses the existing
   installation; you do not need to extract or reinstall the ZIP.
3. At **Licence JSON path**, enter or drag in the complete JSON file path.
4. The installer checks its signature and installation ID before placing it
   at `%LOCALAPPDATA%\GST-80-20\var\license.json`.
5. The portal starts and opens in the browser. Keep the console window open.

The 14-day period begins on first valid application use. After expiry, results
remain viewable/exportable, but calculations and other business writes are
blocked. A missing/invalid licence also leaves the portal read-only. Licences
are installation-specific; a new PC needs its own licence. The bootstrap BAT
does not overwrite an already installed licence. Contact the issuer for renewal
instructions rather than deleting licence or activation records.

## 5. Login and first calculation

For a new database, the initial credentials are:

| Field | Initial value |
| --- | --- |
| User ID | `admin@oswalgroup.net` |
| Password | `admin123456789` |

Change this shared temporary password immediately under **Administration →
Users**. Reinstalling/upgrading does not reset existing passwords.

If you restored a backup, use that backup's original accounts/passwords instead.
The new-installation password may not apply. The old pre-restore database is
retained in `var\recovery`; the temporary password file is archived rather than
presented as a valid restored password.

Open **GST 80:20 → New calculation**. Download the corresponding templates
beside each upload field, and upload the month's populated `.xlsx` files:

- Day Book Register
- Search Voucher
- Creditors Details

Blank templates are not valid calculation inputs. Review the result and export
it. Use **Freeze month** only after approval: freezing prevents replacement and
review changes through the application and is not reversible through the UI.

## 6. Start and stop after activation

For normal subsequent launches, press **Win + R** and enter:

```text
%LOCALAPPDATA%\GST-80-20\deploy.bat
```

The launcher uses port 8080 or the next available port and opens the matching
local browser address. Only one launcher should run per installation. Keep
its console open; **Ctrl+C** stops the portal. You may create a desktop shortcut
to the installed `deploy.bat`. Do not use the ZIP bootstrap for routine launches.

## 7. Backups and recovery

Every successful calculation save creates a separate, consistent, integrity-
checked database snapshot in the configured folder, or `var\backups` by default.
Monitor disk/Drive storage and retain snapshots according to your data policy.
If a backup fails, the calculation remains saved locally and a warning appears.
Resolve the warning and confirm Drive reports **Up to date** before relying on
cloud protection.

At initialization, the launcher checks both local `var\backups` and the
configured backup folder. It never replaces a database containing calculations.
For a reinstall, copy previous local backups into the new installation's
`var\backups`, or configure the previous Drive mirror. Enter skips restoration.
Only compatible backups passing integrity/schema/relationship checks are offered.

Recovery restores all data, users/passwords and frozen statuses. It retains
the current installation ID/licence file and existing activation dates. A
pre-restore snapshot is kept in `var\recovery`. Recovery is not automatic data
synchronization, and backups are not live shared databases.

## 8. Common problems

### Applying an updated source ZIP to an existing installation

Stop the portal, preserve copies of `var` and `.env`, and extract the new clean
client ZIP into a temporary folder. Copy the **contents** of its `GST-80-20`
folder into `%LOCALAPPDATA%\GST-80-20`, replacing source files. The clean ZIP
contains no `.env`, `.venv` or `var` data, so these are not replaced. Run the
installed `deploy.bat` afterwards. The ZIP bootstrap reuses an existing
installation; rerunning it alone does not update the source files.

| Message/problem | Action |
| --- | --- |
| Python/winget unavailable | Ask IT to install Python 3.11+ with PATH enabled, then rerun the BAT. |
| Existing PostgreSQL `DATABASE_URL` | This local BAT only supports SQLite and stops before installing dependencies. Preserve the existing database and arrange an explicit migration; do not just delete `.env`. |
| `WinError 206` / deep path | Install the clean source under a short local folder (the ZIP bootstrap uses `%LOCALAPPDATA%\GST-80-20`). Preserve existing `var` and `.env` before relocating an existing installation. |
| Dependency installation failed | Check network/proxy policy or request a compatible offline bundle. |
| `pg_config` / `psycopg2-binary` error using an older ZIP | Download the refreshed package. SQLite client installs no longer require the PostgreSQL driver. Preserve/rename the failed local installation before retrying with the new ZIP; never discard an installation containing data. |
| ZIP incomplete or contains runtime/issuer files | Use the clean `GST-80-20-client.zip` from `distribution/`, not a ZIP of a working installation. |
| Destination exists but is incomplete | Preserve/inspect the folder; ask support before renaming it. Do not delete databases to retry. |
| Another launcher is already running | Use its existing browser window, or stop it before launching/recovering again. |
| Licence invalid/belongs to another installation | Send the displayed ID to the issuer and request the matching signed JSON. |
| Application read-only | Check **Administration → Licence** for missing, invalid, expired or clock-related status. |
| Database/admin preparation fails or stdout log is empty | Review both `var/install-first-run.log` and `var/install-first-run.log.err`. The `.err` file contains the Python traceback. Unsupported/broken `.venv` folders are archived and rebuilt with supported Python; data/configuration are retained. |
| Login fails after recovery | Use the original credentials from the recovered installation; contact its administrator. |
| Backup folder unavailable | Reconnect the configured Drive mirror and resolve the warning. Saved calculations remain local. |

For support, provide the installation ID, displayed error, and relevant installer
logs from `var`. Never send passwords, private signing keys, or the database to
an unauthorized recipient.

`SOURCE_VERSION.txt` identifies the source snapshot in the client ZIP. Issuer
tools, keys, client workbooks and databases are not part of the distributed ZIP.
