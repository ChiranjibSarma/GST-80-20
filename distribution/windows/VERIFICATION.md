# Windows EXE verification — 19 September 2026

Package: `GST-80-20-Setup.exe`, 29,877,219 bytes, Windows x64.

SHA-256: `E9B78279360FC7AA93D27391F84C5144C90DE79F10DF045BA3F2CB70EE914A12`.

Built from the repository source packaged with this release. Build tool: PyInstaller 6.22.0, Python 3.12.14. Only application templates/static assets/public verification key are explicitly included as data. The dependency manifest was checked for issuer utilities/private keys, reference workbooks and client data; none were found.

## Executed successfully on the build host

Tests invoked the frozen EXE from Windows PowerShell 5.1 with PATH restricted to Windows system directories and PYTHONPATH empty. No Python, py or pip command was available in the test process. Tests used separate new directories; live client databases, identities and licences were not opened or changed.

- Payload installation to a new folder and repeated payload upgrade. A persistent-data sentinel was unchanged, and the installed EXE hash matched the package.
- Bundled Tk GUI runtime initialization (hidden window creation/update/destruction).
- Frozen local HTTP server startup, default fresh-admin login, CSRF/form rendering, the enlarged input-file callouts, CSS/static routing and all three Excel template downloads.
- Missing licence: reads/login available; write request rejected with HTTP 423.
- Separately issuer-signed QA licence: July source upload, permanent July freeze, rejection of July replacement (HTTP 409), supplied actual August upload saved as Aug-26 (HTTP redirect), August Excel export (HTTP 200).
- Isolated persisted data: Jul-26 frozen, Aug-26 draft, 542 August reportable rows. Both per-save SQLite backups and the live test database passed integrity checks.
- Occupied requested port 19100: launcher selected another port; the same no-Python startup/login/template/licence checks passed.
- Source golden regression: all 1,232 July canonical rows and 20 review items matched the approved workbook after the configuration-path change.

## Not verified

Windows Sandbox was absent from the host, so these are **restricted-environment host tests, not a clean Windows VM/Sandbox certification**. No system Python installation was removed. Visual installer dialog/Start-menu shortcut interaction, a real client PC, and antivirus/code-signing reputation were not tested. The package is unsigned. Perform the supplied offline .wsb test and interactive install on a clean Windows machine before production deployment.

QA workbooks and the QA licence remain in a separate local-only test directory, not in the client distribution. Give the client only the setup EXE and their separately issued installation-specific licence JSON.
