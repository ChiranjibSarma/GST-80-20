"""Offline licence: signed terms, first activation and read-only expiry."""
import base64
import datetime as dt
import json
from pathlib import Path
import tempfile
import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import license as licensing
from app.models import LicenseActivation


def main():
    with tempfile.TemporaryDirectory(prefix="gst8020-license-") as root:
        root = Path(root)
        key = Ed25519PrivateKey.generate()
        public = root / "public.pem"
        public.write_bytes(key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        install_id = str(uuid.uuid4())
        (root / "installation-id").write_text(install_id, encoding="ascii")
        payload = {"schema": 1, "license_id": str(uuid.uuid4()),
                   "installation_id": install_id, "customer": "Test Client",
                   "duration_days": 14, "issued_at": "2026-09-01T00:00:00+00:00"}
        document = {"payload": payload,
                    "signature": base64.b64encode(key.sign(licensing.canonical(payload))).decode("ascii")}
        (root / "license.json").write_text(json.dumps(document), encoding="utf-8")

        old = (licensing.PUBLIC_KEY_PATH, licensing.LICENSE_FILE,
               licensing.INSTALLATION_ID_FILE)
        licensing.PUBLIC_KEY_PATH = public
        licensing.LICENSE_FILE = root / "license.json"
        licensing.INSTALLATION_ID_FILE = root / "installation-id"
        engine = create_engine("sqlite+pysqlite:///:memory:")
        LicenseActivation.__table__.create(engine)
        start = dt.datetime(2026, 9, 14, 10, 0, tzinfo=dt.timezone.utc)
        try:
            with Session(engine) as db:
                first = licensing.evaluate(db, start)
                assert first.code == "active" and first.activated_at == start
                assert first.expires_at == start + dt.timedelta(days=14)
                assert licensing.evaluate(db, start + dt.timedelta(days=13)).code == "active"
                assert licensing.evaluate(db, start).code == "clock"
                assert licensing.evaluate(db, start + dt.timedelta(days=14)).code == "expired"
                document["payload"]["duration_days"] = 28
                licensing.LICENSE_FILE.write_text(json.dumps(document), encoding="utf-8")
                assert licensing.evaluate(db, start).code == "invalid"
                licensing.LICENSE_FILE.unlink()
                assert licensing.evaluate(db, start).code == "missing"
        finally:
            (licensing.PUBLIC_KEY_PATH, licensing.LICENSE_FILE,
             licensing.INSTALLATION_ID_FILE) = old
    print("PASS: signed 14-day licence starts on first use and becomes read-only at expiry")


if __name__ == "__main__":
    main()
