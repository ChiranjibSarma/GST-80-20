"""Closed-database handoff refuses silent loss of unsynced local work."""
from pathlib import Path
import sqlite3
import tempfile
from contextlib import closing

from sqlalchemy import create_engine

from app import backup, db, handoff


def _database(path, value):
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        connection.execute("INSERT INTO users (name) VALUES (?)", (value,))
        connection.commit()


def _rows(path):
    with closing(sqlite3.connect(path)) as connection:
        return [row[0] for row in connection.execute("SELECT name FROM users ORDER BY id")]


def main():
    with tempfile.TemporaryDirectory(prefix="gst8020-handoff-",
                                     dir=Path(__file__).resolve().parents[1] / "var") as root:
        root = Path(root)
        mirror = root / "drive-mirror"
        mirror.mkdir()
        local_a = root / "a" / "finops.db"
        local_a.parent.mkdir()
        local_b = root / "b" / "finops.db"
        local_b.parent.mkdir()
        _database(local_a, "first")
        _database(local_b, "bootstrap-only")
        original = (handoff.BACKUP_DIR, handoff.BACKUP_DIR_EXPLICIT,
                    handoff.STATE_PATH, backup.VAR_DIR, db.engine)
        try:
            handoff.BACKUP_DIR = mirror
            handoff.BACKUP_DIR_EXPLICIT = True
            handoff.STATE_PATH = local_a.parent / "state.json"
            backup.VAR_DIR = local_a.parent
            db.engine = create_engine(f"sqlite:///{local_a.as_posix()}")
            handoff.publish(initialize=True)
            assert _rows(mirror / handoff.CURRENT_NAME) == ["first"]
            with closing(sqlite3.connect(local_a)) as connection:
                connection.execute("INSERT INTO users (name) VALUES ('second')")
                connection.commit()
            try:
                handoff.pull()
                raise AssertionError("Pull overwrote unsynced local work")
            except RuntimeError as exc:
                assert "unhanded-off" in str(exc)
            handoff.publish()
            assert _rows(mirror / handoff.CURRENT_NAME) == ["first", "second"]

            db.engine.dispose()
            db.engine = create_engine(f"sqlite:///{local_b.as_posix()}")
            handoff.STATE_PATH = local_b.parent / "state.json"
            backup.VAR_DIR = local_b.parent
            try:
                handoff.pull()
                raise AssertionError("First-time local database was overwritten without adoption")
            except RuntimeError as exc:
                assert "--adopt" in str(exc)
            handoff.pull(adopt=True)
            assert _rows(local_b) == ["first", "second"]
            assert list(local_b.parent.glob("finops-before-pull-*.sqlite3"))
            with closing(sqlite3.connect(mirror / handoff.CURRENT_NAME)) as connection:
                connection.execute("INSERT INTO users (name) VALUES ('remote-update')")
                connection.commit()
            try:
                handoff.publish()
                raise AssertionError("Publish overwrote a changed mirrored database")
            except RuntimeError as exc:
                assert "changed" in str(exc)
        finally:
            db.engine.dispose()
            (handoff.BACKUP_DIR, handoff.BACKUP_DIR_EXPLICIT,
             handoff.STATE_PATH, backup.VAR_DIR, db.engine) = original
    print("PASS: handoff preserves local data and refuses visible conflicts")


if __name__ == "__main__":
    main()
