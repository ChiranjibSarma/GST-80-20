"""Recovery discovery, schema checks, preservation and overwrite protection."""
import datetime as dt
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.models import Base, User, Run, LicenseActivation
from app.recovery import discover_backups, restore_backup, validate_backup


def make_db(path, runs=False, activation=False):
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(email="original@test.local" if runs else "fresh@test.local",
                    name="Admin", password_hash="original-hash" if runs else "fresh-hash", role="admin")
        db.add(user)
        db.flush()
        if runs:
            db.add(Run(label="Old approved run", period_month="Jul-26", financial_year="2026-2027",
                       status="frozen", created_by_id=user.id))
        if activation:
            db.add(LicenseActivation(license_id="local-licence", installation_id="current-pc",
                                    activated_at=dt.datetime(2026, 9, 1), last_seen_at=dt.datetime(2026, 9, 15)))
        db.commit()
    engine.dispose()


def main():
    with tempfile.TemporaryDirectory(prefix="gst-recovery-") as folder:
        root = Path(folder)
        local, drive = root / "local", root / "drive"
        local.mkdir(); drive.mkdir()
        source = drive / "gst8020-previous.sqlite3"
        make_db(source, runs=True)
        invalid = local / "gst8020-invalid.sqlite3"
        invalid.write_bytes(b"not sqlite")
        assert len(discover_backups([local, drive, drive])) == 2
        assert validate_backup(source) == 1
        try:
            validate_backup(invalid)
            raise AssertionError("Invalid backup accepted")
        except sqlite3.Error:
            pass
        live = root / "live.sqlite3"
        make_db(live, activation=True)
        saved = restore_backup(source, live, root / "recovery")
        assert saved.is_file()
        with closing(sqlite3.connect(live)) as db:
            assert db.execute("SELECT status FROM runs").fetchone()[0] == "frozen"
            assert db.execute("SELECT password_hash FROM users").fetchone()[0] == "original-hash"
            assert db.execute("SELECT installation_id FROM license_activations").fetchone()[0] == "current-pc"
        with closing(sqlite3.connect(saved)) as db:
            assert db.execute("SELECT count(*) FROM runs").fetchone()[0] == 0
        try:
            restore_backup(source, live, root / "recovery")
            raise AssertionError("Existing calculations overwritten")
        except ValueError as exc:
            assert "Existing calculations" in str(exc)
    print("PASS: both backup folders; invalid rejection; original accounts/freeze and local licence retained; overwrite blocked")


if __name__ == "__main__":
    main()
