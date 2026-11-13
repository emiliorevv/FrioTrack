"""Datos semilla idempotentes de FríoTrack."""

import hashlib
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings, leer_sensor_tokens
from app.core.security import hash_password
from app.db.models import Camara, Lote, Sensor, Usuario

# Rangos y tiempos del README (NOM-251-SSA1-2009 para refrigerados y congelados).
CAMARAS: list[dict[str, Any]] = [
    {"id": 1, "nombre": "Pescados y mariscos", "rango_min_c": Decimal("0.0"),
     "rango_max_c": Decimal("2.0"), "min_para_riesgo": 10, "min_para_merma": 60},
    {"id": 2, "nombre": "Carnes y aves", "rango_min_c": Decimal("0.0"),
     "rango_max_c": Decimal("4.0"), "min_para_riesgo": 15, "min_para_merma": 120},
    {"id": 3, "nombre": "Lácteos", "rango_min_c": Decimal("1.0"),
     "rango_max_c": Decimal("4.0"), "min_para_riesgo": 20, "min_para_merma": 180},
    {"id": 4, "nombre": "Verduras y frutas", "rango_min_c": Decimal("4.0"),
     "rango_max_c": Decimal("8.0"), "min_para_riesgo": 30, "min_para_merma": 240},
    {"id": 5, "nombre": "Congelador", "rango_min_c": Decimal("-22.0"),
     "rango_max_c": Decimal("-18.0"), "min_para_riesgo": 20, "min_para_merma": 120},
]

SENSORES = {
    1: "S-PES-01",
    2: "S-CAR-01",
    3: "S-LAC-01",
    4: "S-VER-01",
    5: "S-CON-01",
}

# (producto, camara_id, cantidad, unidad, costo_total_mxn, días de caducidad)
LOTES: list[tuple[str, int, Decimal, str, Decimal, int]] = [
    ("Robalo fresco", 1, Decimal("12.00"), "kg", Decimal("3240.00"), 2),
    ("Camarón", 1, Decimal("5.00"), "kg", Decimal("1610.00"), 3),
    ("Pulpo", 1, Decimal("4.00"), "kg", Decimal("1120.00"), 2),
    ("Arrachera", 2, Decimal("10.00"), "kg", Decimal("3100.00"), 5),
    ("Pechuga de pollo", 2, Decimal("15.00"), "kg", Decimal("1650.00"), 3),
    ("Cerdo", 2, Decimal("8.00"), "kg", Decimal("960.00"), 4),
    ("Crema", 3, Decimal("6.00"), "l", Decimal("420.00"), 7),
    ("Queso Oaxaca", 3, Decimal("4.00"), "kg", Decimal("640.00"), 10),
    ("Mantequilla", 3, Decimal("3.00"), "kg", Decimal("390.00"), 12),
    ("Lechuga", 4, Decimal("20.00"), "pz", Decimal("300.00"), 4),
    ("Cilantro y hierbas", 4, Decimal("3.00"), "kg", Decimal("180.00"), 3),
    ("Frutos rojos", 4, Decimal("6.00"), "kg", Decimal("540.00"), 2),
    ("Papas congeladas", 5, Decimal("10.00"), "kg", Decimal("520.00"), 30),
    ("Helado", 5, Decimal("8.00"), "l", Decimal("760.00"), 45),
    ("Carne de res congelada", 5, Decimal("12.00"), "kg", Decimal("2880.00"), 60),
]


def _tokens_de_entorno() -> dict[str, str]:
    """Lee SENSOR_TOKENS (JSON) de la configuración; un valor inválido se ignora."""
    try:
        return leer_sensor_tokens()
    except ValueError:
        return {}


def construir_seed(
    sensor_tokens: dict[str, str] | None = None,
    password: str | None = None,
) -> tuple[list[Camara], list[Sensor], list[Lote], list[Usuario]]:
    """Arma en memoria las filas del seed, sin tocar la base de datos.

    Exige un token para cada uno de los cinco sensores (parámetro o `SENSOR_TOKENS`)
    y una contraseña (parámetro o `SEED_PASSWORD`); si falta algo lanza RuntimeError.
    Es determinista salvo `caducidad`, que se calcula desde hoy.
    """
    settings = get_settings()
    tokens = sensor_tokens if sensor_tokens is not None else _tokens_de_entorno()
    faltantes = [sensor_id for sensor_id in SENSORES.values() if not tokens.get(sensor_id)]
    if faltantes:
        raise RuntimeError(
            f"Faltan tokens de sensor en SENSOR_TOKENS: {', '.join(faltantes)}. "
            "Configura SENSOR_TOKENS con un token para cada sensor."
        )

    password = password if password is not None else settings.seed_password
    if not password:
        raise RuntimeError(
            "Falta SEED_PASSWORD: define la contraseña inicial de los usuarios "
            "semilla `jefe` y `gerente`."
        )

    # `estado` explícito: al no tocar la base, los defaults del modelo no se aplican.
    camaras = [Camara(estado="en_rango", **datos) for datos in CAMARAS]

    sensores = []
    for camara_id, sensor_id in SENSORES.items():
        # Hash-only: el token en claro solo existe en SENSOR_TOKENS (ver docs/modelo-datos.md).
        token = tokens[sensor_id]
        sensores.append(
            Sensor(
                id=sensor_id,
                camara_id=camara_id,
                token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
                activo=True,
            )
        )

    hoy = date.today()
    lotes = [
        Lote(
            producto=producto,
            camara_id=camara_id,
            cantidad=cantidad,
            unidad=unidad,
            costo_total_mxn=costo,
            caducidad=hoy + timedelta(days=dias),
            estado="ok",
        )
        for producto, camara_id, cantidad, unidad, costo, dias in LOTES
    ]

    password_hash = hash_password(password)
    usuarios = [
        Usuario(usuario="jefe", password_hash=password_hash, rol="jefe_cocina"),
        Usuario(usuario="gerente", password_hash=password_hash, rol="gerente"),
    ]

    return camaras, sensores, lotes, usuarios


def cargar_seed(
    session: Session,
    sensor_tokens: dict[str, str] | None = None,
    password: str | None = None,
) -> bool:
    """Carga cámaras, sensores, lotes y usuarios si la base está vacía.

    Regresa True si insertó datos y False si ya había cámaras (idempotente).
    """
    if session.scalar(select(Camara.id).limit(1)) is not None:
        return False

    camaras, sensores, lotes, usuarios = construir_seed(sensor_tokens, password)
    session.add_all(camaras)
    session.flush()
    session.add_all(sensores)
    session.add_all(lotes)
    session.add_all(usuarios)
    session.commit()
    return True
