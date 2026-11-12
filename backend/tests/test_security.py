"""Pruebas de hash_password/verify_password; solo librería estándar."""

from app.core.security import ALGORITMO, hash_password, verify_password


def test_hash_usa_salt_aleatorio():
    primer_hash = hash_password("clave-secreta")
    segundo_hash = hash_password("clave-secreta")

    assert primer_hash != segundo_hash
    assert primer_hash.startswith(f"{ALGORITMO}$")
    assert segundo_hash.startswith(f"{ALGORITMO}$")
    assert "clave-secreta" not in primer_hash


def test_verify_acepta_la_password_correcta_y_rechaza_la_incorrecta():
    password_hash = hash_password("clave-secreta")

    assert verify_password("clave-secreta", password_hash) is True
    assert verify_password("otra-clave", password_hash) is False


def test_verify_rechaza_hashes_con_formato_invalido():
    invalidos = [
        "",
        "formato-invalido",
        "pbkdf2_sha256$390000$no-es-hex$tampoco",
        "pbkdf2_sha256$no-es-entero$00$00",
        "otro_algoritmo$390000$00$00",
    ]

    assert all(verify_password("clave-secreta", valor) is False for valor in invalidos)


def test_verify_rechaza_un_digest_alterado():
    password_hash = hash_password("clave-secreta")
    algoritmo, iteraciones, salt, digest = password_hash.split("$")
    alterado = f"{algoritmo}${iteraciones}${salt}${digest[:-1]}{'0' if digest[-1] != '0' else '1'}"

    assert verify_password("clave-secreta", alterado) is False
