"""Best-effort, one-operator-at-a-time SQLite handoff via a mirrored folder.

Drive is a transport for a *closed* database copy, never the live SQLite file.
The manifest detects changes visible in the local mirror; it cannot prove that
another PC's Drive sync has completed or provide a cross-PC lock.
"""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import uuid

from .config import BACKUP_DIR, BACKUP_DIR_EXPLICIT, DATABASE_URL, VAR_DIR

CURRENT_NAME = "gst8020-current.sqlite3"
STATE_PATH = VAR_DIR / "handoff-state.json"


def _paths():
    if not BACKUP_DIR_EXPLICIT or not BACKUP_DIR.is_dir():
        raise RuntimeError("Set BACKUP_DIR to an existing, client-controlled mirrored Drive folder")
    if not DATABASE_URL.startswith("sqlite"):
        raise RuntimeError("Database handoff supports local SQLite only")
    from .db import engine
    local = Path(engine.url.database).resolve()
    remote = (BACKUP_DIR / CURRENT_NAME).resolve()
    if local == remote or local in remote.parents or remote in local.parents:
        raise RuntimeError("Live database and handoff folder must be separate")
    return local, remote


def _digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _verify(path):
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError(f"Database integrity check failed: {path}")
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'").fetchone():
            raise RuntimeError(f"Not a portal database: {path}")


def _state():
    if not STATE_PATH.is_file():
        return None
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if state["schema"] != 1 or not state["remote_sha256"] or not state["local_sha256"]:
            raise ValueError("Invalid handoff state")
        return state
    except (KeyError, ValueError, TypeError) as exc:
        raise RuntimeError("Local handoff state is invalid; preserve this PC's database and reconcile manually") from exc


def _write_state(remote_hash, local_hash):
    VAR_DIR.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_name(f".{STATE_PATH.name}.{uuid.uuid4().hex}.partial")
    try:
        temporary.write_text(json.dumps({"schema": 1, "remote_sha256": remote_hash,
                                         "local_sha256": local_hash}, indent=2), encoding="utf-8")
        os.replace(temporary, STATE_PATH)
    finally:
        temporary.unlink(missing_ok=True)


def pull(*, adopt=False):
    """Load the mirrored current copy before the web server opens the DB."""
    local, remote = _paths()
    if not remote.is_file():
        raise RuntimeError(f"No shared current database at {remote}; initialize it from one PC first")
    _verify(remote)
    remote_hash = _digest(remote)
    state = _state()
    if state:
        if not local.is_file() or _digest(local) != state["local_sha256"]:
            raise RuntimeError("This PC has unhanded-off local changes; refusing to overwrite them")
    elif local.is_file() and not adopt:
        raise RuntimeError("This PC has a local database but no handoff history; use --adopt after checking it")
    local.parent.mkdir(parents=True, exist_ok=True)
    if local.is_file() and _digest(local) != remote_hash:
        # Never discard the pre-existing copy, even on first-time adoption.
        safety = local.with_name(f"{local.stem}-before-pull-{uuid.uuid4().hex[:8]}.sqlite3")
        shutil.copy2(local, safety)
        print(f"Preserved previous local database at {safety}")
    with tempfile.TemporaryDirectory(prefix="gst8020-pull-", dir=local.parent) as folder:
        staging = Path(folder) / local.name
        shutil.copy2(remote, staging)
        _verify(staging)
        if _digest(staging) != remote_hash:
            raise RuntimeError("Drive copy changed during loading; retry after Drive finishes syncing")
        if _digest(remote) != remote_hash:
            raise RuntimeError("Shared database changed during loading; retry after Drive finishes syncing")
        os.replace(staging, local)
    _write_state(remote_hash, _digest(local))
    print(f"Loaded current database from {remote}")


def publish(*, initialize=False):
    """Publish a consistent copy after the web server has fully stopped."""
    local, remote = _paths()
    if not local.is_file():
        raise RuntimeError(f"Local database not found at {local}")
    _verify(local)
    state = _state()
    if remote.is_file():
        _verify(remote)
        if state is None or _digest(remote) != state["remote_sha256"]:
            raise RuntimeError("Shared current database changed or was not loaded here; refusing to overwrite it")
    elif not initialize or state is not None:
        raise RuntimeError("Shared current database is missing; only a first operator may --initialize")
    from .backup import _sqlite_snapshot
    with tempfile.TemporaryDirectory(prefix="gst8020-publish-", dir=VAR_DIR) as folder:
        snapshot = Path(folder) / CURRENT_NAME
        _sqlite_snapshot(snapshot)
        _verify(snapshot)
        staging = remote.with_name(f".{CURRENT_NAME}.{uuid.uuid4().hex}.partial")
        try:
            shutil.copy2(snapshot, staging)
            if _digest(staging) != _digest(snapshot):
                raise RuntimeError("Drive copy did not match local snapshot")
            if remote.is_file() and (state is None or _digest(remote) != state["remote_sha256"]):
                raise RuntimeError("Shared database changed during publishing; refusing to overwrite it")
            os.replace(staging, remote)
        finally:
            staging.unlink(missing_ok=True)
    _write_state(_digest(remote), _digest(local))
    print(f"Published current database to {remote}")
    print("Wait until Google Drive reports Up to date before another PC starts.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("pull", "publish"))
    parser.add_argument("--adopt", action="store_true", help="preserve then replace an existing local DB on first pull")
    parser.add_argument("--initialize", action="store_true", help="create the first shared current DB")
    args = parser.parse_args(argv)
    try:
        if args.action == "pull":
            pull(adopt=args.adopt)
        else:
            publish(initialize=args.initialize)
    except (OSError, sqlite3.Error, RuntimeError) as exc:
        print(f"Handoff stopped: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
