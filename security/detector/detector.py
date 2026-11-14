"""Detector SIEM de FríoTrack (ADR-0007).

CLI independiente de la API: lee `logs_acceso` y `lecturas`, aplica las reglas
Sigma de `security/siem/` y escribe en `alertas_seguridad`, `ips_bloqueadas`,
`sensores` y `lecturas`. Con `--dry-run` evalúa igual pero no escribe nada.

La lógica de evaluación es pura (recibe filas y devuelve hallazgos) para poder
probarla sin base de datos; el acceso a Postgres vive en `RepositorioPostgres`.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from collections import defaultdict
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import psycopg
from psycopg.types.json import Jsonb

logger = logging.getLogger("friotrack.siem")

# IDs y títulos deben coincidir con los YAML de security/siem/.
REGLA_FUERZA_BRUTA_ID = "3b8e2f6a-9c41-4d7e-8a15-2f6c0d9e7b41"
REGLA_FUERZA_BRUTA = "Fuerza bruta de tokens en ingesta de telemetría y cron"
REGLA_TOKEN_DESCONOCIDO_ID = "e26aa409-804c-47fb-b852-1786ddaa172d"
REGLA_TOKEN_DESCONOCIDO = "Token de sensor usado desde una IP desconocida"
REGLA_LECTURAS_IMPOSIBLES_ID = "26f277c2-6d7a-4ff2-b44c-452f2788f824"
REGLA_LECTURAS_IMPOSIBLES = "Lecturas imposibles de temperatura"

RUTAS_FUERZA_BRUTA = frozenset({"/api/telemetria", "/api/simulador/tick"})
ESTADOS_FUERZA_BRUTA = frozenset({401, 403})
RUTA_TELEMETRIA = "/api/telemetria"

VENTANA_FUERZA_BRUTA_SEG = 300
UMBRAL_FUERZA_BRUTA = 10
BLOQUEO_MINUTOS = 60
DELTA_TEMPERATURA_C = 8.0
VENTANA_LECTURAS_SEG = 60

# Una alerta igual (misma regla y clave) no se repite durante una hora.
VENTANA_DEDUPE_SEG = 3600
# Los logs se consultan de la última hora: la fuerza bruta filtra sus 5 minutos
# dentro del evaluador, y la regla de token así ve un evento que llegó mientras
# el detector estaba apagado.
VENTANA_LOGS_SEG = 3600
# Margen de lecturas para que la primera del lote tenga con quién compararse.
VENTANA_LECTURAS_CONSULTA_SEG = 600

IPS_PERMITIDAS_POR_DEFECTO = "127.0.0.1,::1"

ACCION_BLOQUEAR_IP = "bloquear_ip"
ACCION_REVOCAR_TOKEN = "revocar_token"
ACCION_MARCAR_LECTURAS = "marcar_lecturas"

RUTA_ENV_BACKEND = Path(__file__).resolve().parents[2] / "backend" / ".env"


@dataclass(frozen=True)
class FilaLog:
    """Las columnas de `logs_acceso` que usan las reglas."""

    ts: datetime
    ip_origen: str
    ruta: str
    status: int
    credencial: str = ""
    sujeto: str | None = None


@dataclass(frozen=True)
class FilaLectura:
    """Las columnas de `lecturas` que usa la regla de lecturas imposibles."""

    id: int
    camara_id: int
    temperatura_c: float
    recibida_en: datetime


@dataclass(frozen=True)
class Hallazgo:
    """Una regla disparada y la acción de respuesta que le corresponde."""

    regla_id: str
    regla: str
    severidad: str
    ip_origen: str | None
    detalle: dict[str, Any]
    accion: str
    clave: str


class Repositorio(Protocol):
    """Lo que el detector necesita de la base; las pruebas usan un doble."""

    def logs_desde(self, desde: datetime) -> list[FilaLog]: ...

    def lecturas_desde(self, desde: datetime) -> list[FilaLectura]: ...

    def alerta_reciente(self, regla_id: str, clave: str, desde: datetime) -> bool: ...

    def bloqueo_activo(self, ip: str, ahora: datetime) -> bool: ...

    def registrar_alerta(self, hallazgo: Hallazgo, ahora: datetime) -> None: ...

    def bloquear_ip(self, ip: str, hasta: datetime, motivo: str) -> None: ...

    def desactivar_sensor(self, sensor_id: str) -> None: ...

    def marcar_lectura_sospechosa(self, lectura_id: int) -> None: ...


def evaluar_fuerza_bruta(filas: Sequence[FilaLog], ahora: datetime) -> list[Hallazgo]:
    """IPs con 10 o más respuestas 401/403 en las rutas de ingesta en 5 minutos."""
    desde = ahora - timedelta(seconds=VENTANA_FUERZA_BRUTA_SEG)
    por_ip: dict[str, list[FilaLog]] = defaultdict(list)
    for fila in filas:
        if (
            fila.ruta in RUTAS_FUERZA_BRUTA
            and fila.status in ESTADOS_FUERZA_BRUTA
            and desde <= fila.ts <= ahora
        ):
            por_ip[fila.ip_origen].append(fila)

    hallazgos: list[Hallazgo] = []
    for ip in sorted(por_ip):
        eventos = por_ip[ip]
        if len(eventos) < UMBRAL_FUERZA_BRUTA:
            continue
        clave = f"ip:{ip}"
        hallazgos.append(
            Hallazgo(
                regla_id=REGLA_FUERZA_BRUTA_ID,
                regla=REGLA_FUERZA_BRUTA,
                severidad="high",
                ip_origen=ip,
                detalle={
                    "clave": clave,
                    "intentos": len(eventos),
                    "ventana_s": VENTANA_FUERZA_BRUTA_SEG,
                    "rutas": sorted({evento.ruta for evento in eventos}),
                },
                accion=ACCION_BLOQUEAR_IP,
                clave=clave,
            )
        )
    return hallazgos


def evaluar_token_desconocido(
    filas: Sequence[FilaLog], ips_permitidas: Collection[str]
) -> list[Hallazgo]:
    """Autenticaciones de sensor exitosas desde una IP fuera de la lista de confianza."""
    permitidas = set(ips_permitidas)
    ordenadas = sorted(filas, key=lambda fila: (fila.ts, fila.ip_origen, fila.sujeto or ""))
    hallazgos: list[Hallazgo] = []
    for fila in ordenadas:
        if (
            fila.credencial != "sensor"
            or fila.ruta != RUTA_TELEMETRIA
            or fila.status != 202
            or fila.ip_origen in permitidas
        ):
            continue
        sensor_id = fila.sujeto or ""
        clave = f"sensor:{sensor_id}" if sensor_id else f"ip:{fila.ip_origen}"
        hallazgos.append(
            Hallazgo(
                regla_id=REGLA_TOKEN_DESCONOCIDO_ID,
                regla=REGLA_TOKEN_DESCONOCIDO,
                severidad="high",
                ip_origen=fila.ip_origen,
                detalle={
                    "clave": clave,
                    "sensor_id": sensor_id or None,
                    "ip_origen": fila.ip_origen,
                    "status": fila.status,
                },
                accion=ACCION_REVOCAR_TOKEN,
                clave=clave,
            )
        )
    return hallazgos


def evaluar_lecturas_imposibles(
    filas: Sequence[FilaLectura], ahora: datetime
) -> list[Hallazgo]:
    """Saltos de más de 8 °C en 60 segundos o menos entre lecturas de una cámara.

    Se ordenan por `recibida_en` (hora del servidor) y se compara cada lectura
    con la anterior; el hallazgo apunta a la lectura posterior, que es la que se
    marca como sospechosa.
    """
    por_camara: dict[int, list[FilaLectura]] = defaultdict(list)
    for fila in filas:
        if fila.recibida_en <= ahora:
            por_camara[fila.camara_id].append(fila)

    hallazgos: list[Hallazgo] = []
    for camara_id in sorted(por_camara):
        lecturas = sorted(por_camara[camara_id], key=lambda fila: (fila.recibida_en, fila.id))
        for anterior, actual in zip(lecturas, lecturas[1:], strict=False):
            segundos = (actual.recibida_en - anterior.recibida_en).total_seconds()
            delta = abs(actual.temperatura_c - anterior.temperatura_c)
            if segundos < 0 or segundos > VENTANA_LECTURAS_SEG or delta <= DELTA_TEMPERATURA_C:
                continue
            clave = f"camara:{camara_id}:lectura:{actual.id}"
            hallazgos.append(
                Hallazgo(
                    regla_id=REGLA_LECTURAS_IMPOSIBLES_ID,
                    regla=REGLA_LECTURAS_IMPOSIBLES,
                    severidad="medium",
                    ip_origen=None,
                    detalle={
                        "clave": clave,
                        "camara_id": camara_id,
                        "lectura_id": actual.id,
                        "lectura_anterior_id": anterior.id,
                        "temperatura_anterior_c": anterior.temperatura_c,
                        "temperatura_c": actual.temperatura_c,
                        "delta_c": round(delta, 1),
                        "segundos": segundos,
                    },
                    accion=ACCION_MARCAR_LECTURAS,
                    clave=clave,
                )
            )
    return hallazgos


def detectar(
    repo: Repositorio,
    ahora: datetime,
    ips_permitidas: Collection[str],
    *,
    bloqueo_minutos: int = BLOQUEO_MINUTOS,
    escribir: bool = True,
) -> list[Hallazgo]:
    """Evalúa las tres reglas y ejecuta las acciones de los hallazgos nuevos.

    Devuelve solo los hallazgos atendidos (o que se atenderían con
    `escribir=False`). Las IPs de confianza nunca se bloquean y una alerta ya
    registrada en la última hora no se repite.
    """
    permitidas = set(ips_permitidas)
    logs = repo.logs_desde(ahora - timedelta(seconds=VENTANA_LOGS_SEG))
    lecturas = repo.lecturas_desde(ahora - timedelta(seconds=VENTANA_LECTURAS_CONSULTA_SEG))

    candidatos = [
        *evaluar_fuerza_bruta(logs, ahora),
        *evaluar_token_desconocido(logs, permitidas),
        *evaluar_lecturas_imposibles(lecturas, ahora),
    ]

    desde_dedupe = ahora - timedelta(seconds=VENTANA_DEDUPE_SEG)
    atendidos: list[Hallazgo] = []
    vistas: set[tuple[str, str]] = set()
    for hallazgo in candidatos:
        identidad = (hallazgo.regla_id, hallazgo.clave)
        if identidad in vistas:
            continue
        vistas.add(identidad)

        if hallazgo.accion == ACCION_BLOQUEAR_IP:
            ip = hallazgo.ip_origen or ""
            if not ip:
                continue
            if ip in permitidas:
                logger.warning(
                    "Fuerza bruta desde la IP de confianza %s (%s intentos); no se bloquea",
                    ip,
                    hallazgo.detalle.get("intentos"),
                )
                continue
            if repo.bloqueo_activo(ip, ahora):
                logger.info("La IP %s ya está bloqueada; se omite la alerta", ip)
                continue

        if repo.alerta_reciente(hallazgo.regla_id, hallazgo.clave, desde_dedupe):
            logger.info(
                "Alerta reciente de %s para %s; se omite", hallazgo.regla, hallazgo.clave
            )
            continue

        if escribir:
            repo.registrar_alerta(hallazgo, ahora)
            logger.warning(
                "Alerta %s (%s): ip=%s accion=%s detalle=%s",
                hallazgo.regla,
                hallazgo.regla_id,
                hallazgo.ip_origen or "-",
                hallazgo.accion,
                json.dumps(hallazgo.detalle, ensure_ascii=False, default=str),
            )
            _ejecutar_accion(repo, hallazgo, ahora, bloqueo_minutos)
        atendidos.append(hallazgo)
    return atendidos


def _ejecutar_accion(
    repo: Repositorio, hallazgo: Hallazgo, ahora: datetime, bloqueo_minutos: int
) -> None:
    """Aplica la respuesta de una regla después de registrar su alerta."""
    if hallazgo.accion == ACCION_BLOQUEAR_IP:
        hasta = ahora + timedelta(minutes=bloqueo_minutos)
        repo.bloquear_ip(hallazgo.ip_origen or "", hasta, hallazgo.regla_id)
        logger.warning(
            "IP %s bloqueada %s min (hasta %s) por la regla %s",
            hallazgo.ip_origen,
            bloqueo_minutos,
            hasta.isoformat(),
            hallazgo.regla_id,
        )
    elif hallazgo.accion == ACCION_REVOCAR_TOKEN:
        sensor_id = hallazgo.detalle.get("sensor_id")
        if sensor_id:
            repo.desactivar_sensor(str(sensor_id))
            logger.warning(
                "Sensor %s desactivado: su token se usó desde %s",
                sensor_id,
                hallazgo.ip_origen,
            )
        else:
            logger.warning("Alerta de token sin sensor_id: no hay token que revocar")
    elif hallazgo.accion == ACCION_MARCAR_LECTURAS:
        lectura_id = hallazgo.detalle.get("lectura_id")
        if lectura_id is not None:
            repo.marcar_lectura_sospechosa(int(lectura_id))
        logger.warning(
            "Lectura %s de la cámara %s marcada como sospechosa (%s °C en %s s)",
            lectura_id,
            hallazgo.detalle.get("camara_id"),
            hallazgo.detalle.get("delta_c"),
            hallazgo.detalle.get("segundos"),
        )


class RepositorioPostgres:
    """Implementación con psycopg; cada método abre y cierra su conexión."""

    def __init__(self, database_url: str) -> None:
        self._url = database_url

    def logs_desde(self, desde: datetime) -> list[FilaLog]:
        with psycopg.connect(self._url) as conexion, conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT ts, ip_origen, ruta, status, credencial, sujeto
                FROM logs_acceso
                WHERE ts >= %s
                ORDER BY ts
                """,
                (desde,),
            )
            return [FilaLog(*fila) for fila in cursor.fetchall()]

    def lecturas_desde(self, desde: datetime) -> list[FilaLectura]:
        with psycopg.connect(self._url) as conexion, conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, camara_id, temperatura_c, recibida_en
                FROM lecturas
                WHERE recibida_en >= %s
                ORDER BY recibida_en, id
                """,
                (desde,),
            )
            return [
                FilaLectura(
                    id=fila[0],
                    camara_id=fila[1],
                    temperatura_c=float(fila[2]),
                    recibida_en=fila[3],
                )
                for fila in cursor.fetchall()
            ]

    def alerta_reciente(self, regla_id: str, clave: str, desde: datetime) -> bool:
        with psycopg.connect(self._url) as conexion, conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM alertas_seguridad
                    WHERE regla_id = %s AND detalle->>'clave' = %s AND ts >= %s
                )
                """,
                (regla_id, clave, desde),
            )
            return bool(cursor.fetchone()[0])

    def bloqueo_activo(self, ip: str, ahora: datetime) -> bool:
        with psycopg.connect(self._url) as conexion, conexion.cursor() as cursor:
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM ips_bloqueadas WHERE ip = %s AND hasta > %s)",
                (ip, ahora),
            )
            return bool(cursor.fetchone()[0])

    def registrar_alerta(self, hallazgo: Hallazgo, ahora: datetime) -> None:
        with psycopg.connect(self._url) as conexion, conexion.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO alertas_seguridad
                    (regla_id, regla, severidad, ts, ip_origen, detalle, accion)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    hallazgo.regla_id,
                    hallazgo.regla,
                    hallazgo.severidad,
                    ahora,
                    hallazgo.ip_origen,
                    Jsonb(hallazgo.detalle),
                    hallazgo.accion,
                ),
            )

    def bloquear_ip(self, ip: str, hasta: datetime, motivo: str) -> None:
        # ON CONFLICT extiende el bloqueo si la IP ya estaba bloqueada.
        with psycopg.connect(self._url) as conexion, conexion.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO ips_bloqueadas (ip, hasta, motivo)
                VALUES (%s, %s, %s)
                ON CONFLICT (ip) DO UPDATE
                SET hasta = GREATEST(ips_bloqueadas.hasta, EXCLUDED.hasta),
                    motivo = EXCLUDED.motivo
                """,
                (ip, hasta, motivo),
            )

    def desactivar_sensor(self, sensor_id: str) -> None:
        with psycopg.connect(self._url) as conexion, conexion.cursor() as cursor:
            cursor.execute("UPDATE sensores SET activo = FALSE WHERE id = %s", (sensor_id,))

    def marcar_lectura_sospechosa(self, lectura_id: int) -> None:
        with psycopg.connect(self._url) as conexion, conexion.cursor() as cursor:
            cursor.execute("UPDATE lecturas SET sospechosa = TRUE WHERE id = %s", (lectura_id,))


def normalizar_database_url(url: str) -> str:
    """psycopg no entiende el prefijo de driver que usa SQLAlchemy."""
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def _leer_env(ruta: Path, nombre: str) -> str:
    """Lee una variable de un `.env` sin tocar el resto ni imprimir valores."""
    try:
        lineas = ruta.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for linea in lineas:
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        linea = linea.removeprefix("export ").strip()
        clave, separador, valor = linea.partition("=")
        if not separador or clave.strip() != nombre:
            continue
        return valor.strip().strip('"').strip("'")
    return ""


def resolver_database_url(explicita: str | None = None) -> str:
    """Resuelve `DATABASE_URL` del argumento, el entorno o `backend/.env`."""
    url = (explicita or os.getenv("DATABASE_URL", "")).strip()
    if not url:
        url = _leer_env(RUTA_ENV_BACKEND, "DATABASE_URL")
    if not url:
        raise RuntimeError(
            "Falta DATABASE_URL: defínela en el entorno, en backend/.env "
            "o pásala con --database-url."
        )
    return normalizar_database_url(url)


def _parsear_ips(texto: str) -> set[str]:
    return {ip.strip() for ip in texto.split(",") if ip.strip()}


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m security.detector",
        description=(
            "Detector SIEM de FríoTrack: aplica las reglas Sigma de security/siem/ "
            "sobre logs_acceso y lecturas."
        ),
    )
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument(
        "--once",
        action="store_true",
        help="evalúa una vez y termina (predeterminado)",
    )
    modo.add_argument(
        "--intervalo",
        type=int,
        metavar="SEGUNDOS",
        help="evalúa cada N segundos hasta Ctrl+C",
    )
    parser.add_argument(
        "--database-url",
        default="",
        help="cadena de Postgres; si falta se usa DATABASE_URL o backend/.env",
    )
    parser.add_argument(
        "--ips-permitidas",
        default=os.getenv("IPS_RESTAURANTE", IPS_PERMITIDAS_POR_DEFECTO),
        help=(
            "IPs de confianza separadas por comas "
            f"(default: IPS_RESTAURANTE o {IPS_PERMITIDAS_POR_DEFECTO})"
        ),
    )
    parser.add_argument(
        "--bloqueo-minutos",
        type=int,
        default=BLOQUEO_MINUTOS,
        help=f"duración del bloqueo de una IP (default: {BLOQUEO_MINUTOS})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="imprime los hallazgos sin escribir en la base",
    )
    return parser


def _imprimir_hallazgos(hallazgos: Sequence[Hallazgo]) -> None:
    if not hallazgos:
        print("Sin hallazgos nuevos.")
        return
    for hallazgo in hallazgos:
        detalle = json.dumps(hallazgo.detalle, ensure_ascii=False, default=str)
        print(
            f"[{hallazgo.severidad.upper()}] {hallazgo.regla} ({hallazgo.regla_id}) "
            f"ip={hallazgo.ip_origen or '-'} accion={hallazgo.accion} {detalle}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Entrada del CLI: `--once` o `--intervalo N`, con `--dry-run` opcional."""
    parser = construir_parser()
    args = parser.parse_args(argv)
    if args.intervalo is not None and args.intervalo < 1:
        parser.error("--intervalo debe ser al menos 1 segundo")
    if args.bloqueo_minutos < 1:
        parser.error("--bloqueo-minutos debe ser al menos 1")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    ips_permitidas = _parsear_ips(args.ips_permitidas)
    try:
        repo = RepositorioPostgres(resolver_database_url(args.database_url))
    except RuntimeError as error:
        logger.error("%s", error)
        return 1

    logger.info(
        "Detector SIEM iniciado: modo=%s ips_permitidas=%s bloqueo=%s min%s",
        "dry-run" if args.dry_run else "real",
        ",".join(sorted(ips_permitidas)),
        args.bloqueo_minutos,
        f" intervalo={args.intervalo}s" if args.intervalo is not None else "",
    )

    try:
        while True:
            ahora = datetime.now(UTC)
            try:
                hallazgos = detectar(
                    repo,
                    ahora,
                    ips_permitidas,
                    bloqueo_minutos=args.bloqueo_minutos,
                    escribir=not args.dry_run,
                )
            except Exception:
                logger.exception("Fallo al evaluar las reglas")
                if args.intervalo is None:
                    return 1
            else:
                if args.dry_run:
                    # En modo continuo solo se imprime cuando hay algo nuevo.
                    if hallazgos or args.intervalo is None:
                        _imprimir_hallazgos(hallazgos)
                else:
                    logger.info("Evaluación terminada: %s acción(es)", len(hallazgos))

            if args.intervalo is None:
                return 0
            time.sleep(args.intervalo)
    except KeyboardInterrupt:
        logger.info("Detector detenido por el usuario")
        return 0
