"""
Token encryption helpers.

Instagram long-lived access tokens are sensitive credentials. Storing them as
plaintext in the database means a single DB leak hands an attacker full access
to every connected account. We encrypt them at rest with Fernet (AES-128-CBC +
HMAC) from the `cryptography` package.

The encryption key is taken from the `TOKEN_ENCRYPTION_KEY` env var when set
(must be a urlsafe-base64 32-byte Fernet key). Otherwise it is deterministically
derived from `SECRET_KEY` so the app keeps working in development without extra
configuration — but production should set an explicit, rotated key.

`decrypt_token` is intentionally tolerant: if a value is not valid ciphertext
(e.g. a legacy plaintext token written before encryption was introduced) it is
returned unchanged, so existing databases keep working.
"""

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

_fernet = None


def _build_fernet():
    """Construct (once) the Fernet instance from configured key material."""
    explicit = os.environ.get("TOKEN_ENCRYPTION_KEY")
    if explicit:
        key = explicit.encode()
    else:
        # Derive a stable 32-byte key from SECRET_KEY. SHA-256 → urlsafe base64.
        secret = os.environ.get("SECRET_KEY") or "change-me-in-production"
        digest = hashlib.sha256(secret.encode()).digest()
        key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def _get_fernet():
    global _fernet
    if _fernet is None:
        _fernet = _build_fernet()
    return _fernet


def encrypt_token(token):
    """Encrypt a token string for storage. Returns None for falsy input."""
    if not token:
        return token
    return _get_fernet().encrypt(token.encode()).decode()


def decrypt_token(value):
    """
    Decrypt a stored token. Returns the original value if it is not valid
    ciphertext (legacy plaintext tokens), or None for falsy input.
    """
    if not value:
        return value
    try:
        return _get_fernet().decrypt(value.encode()).decode()
    except (InvalidToken, ValueError, TypeError):
        # Legacy plaintext token or wrong key — return as-is so reads don't break.
        return value
