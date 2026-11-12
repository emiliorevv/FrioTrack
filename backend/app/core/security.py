"""Hashing de contraseñas con PBKDF2-HMAC-SHA256 de la librería estándar."""

import hashlib
import hmac
import secrets

ALGORITMO = "pbkdf2_sha256"
ITERACIONES = 390_000
SALT_BYTES = 16


def hash_password(password: str) -> str:
    """Devuelve `pbkdf2_sha256$iteraciones$salt_hex$hash_hex` con salt aleatorio."""
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERACIONES)
    return f"{ALGORITMO}${ITERACIONES}${salt.hex()}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """Compara una contraseña con el hash guardado, sin filtrar tiempos."""
    try:
        algoritmo, iteraciones, salt_hex, digest_hex = password_hash.split("$")
        if algoritmo != ALGORITMO:
            return False
        salt = bytes.fromhex(salt_hex)
        esperado = bytes.fromhex(digest_hex)
        calculado = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iteraciones))
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(calculado, esperado)
