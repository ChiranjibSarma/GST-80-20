# Client installation package

Give the client `install_from_zip.bat` and `GST-80-20-client.zip` from this folder.
The ZIP is a source snapshot, excludes this distribution folder (no nested
packages), and contains no issuer utility, private key, licence or client data.
The repository commit packaged is recorded in `SOURCE_VERSION.txt`.

Run the BAT and select the ZIP. It prepares a local installation and displays
the installation ID. Send that ID to the issuer; rerun the BAT with the
separately issued licence JSON after receiving it.

New installations use admin@oswalgroup.net / admin123456789. Change the password
after login. Recovery restores the original accounts/passwords from a selected
backup instead; it never replaces an existing calculation database.

Backups are checked in both local var/backups and the configured backup folder.
Choose a backup number and type RESTORE to confirm, or Enter to start fresh.
Do not run any other copies during recovery. A new PC requires its own licence.
