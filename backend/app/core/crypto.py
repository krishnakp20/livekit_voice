"""Reversible encryption for client-supplied provider API keys (STT/LLM/TTS).

Unlike passwords (one-way hash in security.py), these secrets must be
DECRYPTED at call time so the worker can actually use them — so this is
symmetric encryption (Fernet), keyed by FIELD_ENCRYPTION_KEY, which must live
only in the server .env, never in the database.

Generate a key once with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
and set it as FIELD_ENCRYPTION_KEY in backend/.env. Losing/rotating this key
means every previously-encrypted key in the DB becomes undecryptable — treat
it like any other production secret (back it up, don't commit it).
"""

from __future__ import annotations

import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

logger = logging.getLogger("vbots.crypto")

_fernet: Fernet | None = None


def _get_fernet() -> Fernet | None:
    global _fernet
    if _fernet is None:
        key = (settings.FIELD_ENCRYPTION_KEY or "").strip()
        if not key:
            return None
        _fernet = Fernet(key.encode())
    return _fernet


def encrypt_secret(plain: str | None) -> str | None:
    """Encrypt a client-supplied API key before storing it. Returns None if
    input is empty or no encryption key is configured (caller should treat
    that as 'do not store this field')."""
    if not plain or not plain.strip():
        return None
    fernet = _get_fernet()
    if fernet is None:
        logger.warning("FIELD_ENCRYPTION_KEY not set — refusing to store a plaintext API key")
        return None
    return fernet.encrypt(plain.strip().encode()).decode()


def decrypt_secret(token: str | None) -> str | None:
    """Decrypt a stored API key at call time. Returns None on any failure
    (missing key, wrong encryption key, corrupted value) rather than raising —
    callers should fall back to the global/company API key in that case."""
    if not token:
        return None
    fernet = _get_fernet()
    if fernet is None:
        return None
    try:
        return fernet.decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        logger.warning("Could not decrypt a stored provider API key — check FIELD_ENCRYPTION_KEY")
        return None


def mask_secret(token: str | None) -> str | None:
    """For API responses: never return the decrypted key or the raw encrypted
    blob. Just indicate one is configured, so the UI can show 'key set'."""
    return "••••••••" if token else None
