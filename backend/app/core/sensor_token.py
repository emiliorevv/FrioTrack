"""Tokens de sensores: generación y hash compartidos por CRUD, seed e ingesta."""

from __future__ import annotations

import hashlib
import secrets


def generar_token() -> str:
    """Token fuerte de un solo uso visible: 32 bytes en base64 URL-safe."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """SHA-256 en hex: lo único que se guarda en `sensores.token_hash`."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
