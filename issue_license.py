#!/usr/bin/env python3
"""Offline licence issuer. Run only on the issuer's trusted machine.

The private key must NEVER be copied to the client or committed to Git.
One signed licence grants 14 days beginning on first valid use by its bound
installation. A renewal uses a new licence ID and starts its own 14-day term.
"""
import argparse
import base64
import datetime as dt
import json
import os
from pathlib import Path
import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def new_key(private_path, public_path):
    private_path, public_path = Path(private_path).resolve(), Path(public_path).resolve()
    app_root = Path(__file__).resolve().parent
    if private_path.is_relative_to(app_root):
        raise ValueError("Keep the private key outside the application folder that goes to the client")
    if private_path.exists() or public_path.exists():
        raise FileExistsError("Key file already exists; refusing to replace it")
    private_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    private_bytes = key.private_bytes(serialization.Encoding.PEM,
                                       serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption())
    public_bytes = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    fd = os.open(private_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(private_bytes)
    public_path.write_bytes(public_bytes)
    print(f"Public key: {public_path}")
    print(f"Private key: {private_path} (keep in a protected issuer-only location)")


def issue(private_path, installation_id, customer, output_path):
    installation_id = str(uuid.UUID(installation_id))
    customer = customer.strip()
    if not customer or len(customer) > 160:
        raise ValueError("Customer name is required (up to 160 characters)")
    output_path = Path(output_path).resolve()
    if output_path.exists():
        raise FileExistsError("Licence file already exists; use a new output filename")
    key = serialization.load_pem_private_key(Path(private_path).read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Issuer key must be Ed25519")
    payload = {
        "schema": 1,
        "license_id": str(uuid.uuid4()),
        "installation_id": installation_id,
        "customer": customer,
        "duration_days": 14,
        "issued_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    document = {"payload": payload,
                "signature": base64.b64encode(key.sign(canonical(payload))).decode("ascii")}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(f"Licence: {output_path}")
    print("Copy it to the client server as var/license.json. The term starts on first valid use.")


def main():
    parser = argparse.ArgumentParser(description="Issue 14-day offline GST 80:20 licences")
    commands = parser.add_subparsers(dest="command", required=True)
    keygen = commands.add_parser("keygen")
    keygen.add_argument("--private-key", required=True)
    keygen.add_argument("--public-key", required=True)
    grant = commands.add_parser("issue")
    grant.add_argument("--private-key", required=True)
    grant.add_argument("--installation-id", required=True)
    grant.add_argument("--customer", required=True)
    grant.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "keygen":
        new_key(args.private_key, args.public_key)
    else:
        issue(args.private_key, args.installation_id, args.customer, args.output)


if __name__ == "__main__":
    main()
