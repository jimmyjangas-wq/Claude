#!/usr/bin/env python3
"""Generate a VAPID key pair for Web Push, printed ready to paste into config.json.

Run once: python make_vapid.py

Outputs:
  * private_key - PEM, used by the server to sign push messages (keep secret)
  * public_key  - base64url application server key, sent to the browser so it can
                  subscribe to push for this server

Uses `cryptography`, which pywebpush already depends on - no extra install.
"""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def main() -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    # The browser's applicationServerKey is the raw uncompressed public point,
    # base64url-encoded without padding.
    raw_public = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    public_b64 = base64.urlsafe_b64encode(raw_public).rstrip(b"=").decode()

    print("Paste these into the \"vapid\" block of config.json:\n")
    print(f'  "public_key": "{public_b64}",')
    print('  "private_key":', json_safe(private_pem) + ",")
    print('  "subject": "mailto:you@example.com"')


def json_safe(pem: str) -> str:
    """Render a multi-line PEM as a single JSON string with escaped newlines."""
    return '"' + pem.replace("\n", "\\n") + '"'


if __name__ == "__main__":
    main()
