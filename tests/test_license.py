"""Offline licence: signed terms, first activation and read-only expiry."""
import datetime as dt
import json
from pathlib import Path
import tempfile
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import license as licensing
from app.models import LicenseActivation

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def main():
    with tempfile.TemporaryDirectory(prefix="gst8020-license-") as root:
        root = Path(root)
        public = root / "public.pem"
        public.write_bytes((FIXTURES / "license_public_key.pem").read_bytes())
        document = json.loads((FIXTURES / "license_valid.json").read_text(encoding="utf-8"))
        payload = document["payload"]
        install_id = payload["installation_id"]
        (root / "installation-id").write_text(install_id, encoding="ascii")
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
                checked, checked_id, checked_customer = licensing.verify_license_file(
                    licensing.LICENSE_FILE, install_id)
                assert checked == payload and checked_id == payload["license_id"]
                assert checked_customer == "Automated Test Client"
                assert db.get(LicenseActivation, payload["license_id"]) is None
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
