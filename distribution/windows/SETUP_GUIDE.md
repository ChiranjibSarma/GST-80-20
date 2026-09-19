# Single-file Windows offline installer

Target: Windows 10/11 x64. No Python, Git, pip or internet is needed on the client.

1. Copy `GST-80-20-Setup.exe` to the client PC and double-click it. Confirm the per-user installation. Close existing running portal copies before upgrading.
2. Open **GST 80-20** from the Windows Start menu. Keep its launcher open while using the browser portal. Closing the launcher stops the server.
3. Copy the installation ID shown in the launcher and send it to the issuer. Import the separately supplied, signed licence JSON using **Import licence JSON**. The 14-day term begins on first valid application use. Without a licence or after expiry, existing results remain read-only and exportable.
4. For a new database only, sign in with `admin@oswalgroup.net` and `admin123456789`. Change the password immediately. Existing or restored accounts keep their original passwords.
5. Optionally select an existing Google Drive **mirrored** backup folder and restart the launcher. The live SQLite database remains local. Every successful calculation save creates a separate consistent backup.

Executable: `%LOCALAPPDATA%\Programs\GST-80-20\GST-80-20.exe`.
Persistent data/configuration: `%LOCALAPPDATA%\GST-80-20` (`var\finops.db`, `var\license.json`, `.env`, `var\backups`, `var\launcher.log`). Upgrades replace only the executable. They do not reset the licence, passwords or database. No automatic migration from a different PC or a project checkout is performed.

On initialization, an empty database checks local and configured backups. Recovery requires explicit selection/confirmation and restores original accounts/passwords. Existing calculations are not overwritten.

The local server listens only on `127.0.0.1`, selects the next available port from 8080, and uses one worker. This is a single-PC solution, not a shared database service.

Only public licence verification is shipped. The issuer private key and generation utility, client Excel files, existing licences and databases are excluded. A frozen executable is not tamper-proof DRM. This build is unsigned; obtain code signing before broad distribution. Do not disable Windows security protections to install it.

## Verification limitations

The build host did not have Windows Sandbox installed. A successful restricted-PATH test proves that no external Python executable is required, not that every clean Windows machine is compatible. Perform the supplied Windows Sandbox test and a real client-PC install before production handover.

On a PC with Windows Sandbox already enabled, edit `Offline-test.wsb` so `HostFolder` points to this folder, then double-click it. Networking is disabled; the package folder is read-only. The automated test uses only Windows PowerShell and the bundled EXE, creates data inside the sandbox, checks login/templates and verifies missing-licence writes are blocked. Results appear in the sandbox console and `C:\GSTQARun\test-result.json`. This does not test the interactive install dialogs; double-click the EXE inside the sandbox to verify them separately. [Microsoft Windows Sandbox configuration documentation](https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-configure-using-wsb-file).
