"""Pruebas puras del detector SIEM: sin base de datos ni red."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from security.detector.detector import (
    ACCION_BLOQUEAR_IP,
    ACCION_MARCAR_LECTURAS,
    ACCION_REVOCAR_TOKEN,
    BLOQUEO_MINUTOS,
    REGLA_FUERZA_BRUTA_ID,
    REGLA_LECTURAS_IMPOSIBLES_ID,
    REGLA_TOKEN_DESCONOCIDO_ID,
    FilaLectura,
    FilaLog,
    Hallazgo,
    detectar,
    evaluar_fuerza_bruta,
    evaluar_lecturas_imposibles,
    evaluar_token_desconocido,
)

AHORA = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
IPS_PERMITIDAS = {"127.0.0.1", "::1"}


def fila_log(
    *,
    segundos_atras: int = 0,
    ip: str = "127.0.0.2",
    ruta: str = "/api/telemetria",
    status: int = 401,
    credencial: str = "sensor",
    sujeto: str = "S-PES-01",
) -> FilaLog:
    return FilaLog(
        ts=AHORA - timedelta(seconds=segundos_atras),
        ip_origen=ip,
        ruta=ruta,
        status=status,
        credencial=credencial,
        sujeto=sujeto,
    )


def fila_lectura(
    *, id: int, camara_id: int = 1, temperatura_c: float, segundos_atras: int
) -> FilaLectura:
    return FilaLectura(
        id=id,
        camara_id=camara_id,
        temperatura_c=temperatura_c,
        recibida_en=AHORA - timedelta(seconds=segundos_atras),
    )


# --- Fuerza bruta -----------------------------------------------------------


def test_fuerza_bruta_dispara_con_diez_intentos():
    filas = [fila_log(segundos_atras=indice) for indice in range(10)]

    hallazgos = evaluar_fuerza_bruta(filas, AHORA)

    assert len(hallazgos) == 1
    hallazgo = hallazgos[0]
    assert hallazgo.regla_id == REGLA_FUERZA_BRUTA_ID
    assert hallazgo.ip_origen == "127.0.0.2"
    assert hallazgo.accion == ACCION_BLOQUEAR_IP
    assert hallazgo.clave == "ip:127.0.0.2"
    assert hallazgo.detalle == {
        "clave": "ip:127.0.0.2",
        "intentos": 10,
        "ventana_s": 300,
        "rutas": ["/api/telemetria"],
    }


def test_fuerza_bruta_no_dispara_con_nueve_intentos():
    filas = [fila_log(segundos_atras=indice) for indice in range(9)]

    assert evaluar_fuerza_bruta(filas, AHORA) == []


def test_fuerza_bruta_ignora_eventos_fuera_de_la_ventana():
    filas = [fila_log(segundos_atras=301 + indice) for indice in range(10)]
    filas += [fila_log(segundos_atras=indice) for indice in range(9)]

    assert evaluar_fuerza_bruta(filas, AHORA) == []


def test_fuerza_bruta_cuenta_telemetria_y_tick_pero_no_otras_rutas():
    otras = [fila_log(ruta="/api/camaras", segundos_atras=indice) for indice in range(15)]
    ingesta = [
        fila_log(ruta="/api/telemetria", segundos_atras=indice, status=403) for indice in range(5)
    ] + [
        fila_log(ruta="/api/simulador/tick", segundos_atras=indice, status=401)
        for indice in range(5)
    ]

    assert evaluar_fuerza_bruta(otras, AHORA) == []
    hallazgos = evaluar_fuerza_bruta(ingesta, AHORA)
    assert len(hallazgos) == 1
    assert hallazgos[0].detalle["rutas"] == ["/api/simulador/tick", "/api/telemetria"]


# --- Token desde IP desconocida --------------------------------------------


def test_token_desconocido_dispara_fuera_de_la_allowlist():
    filas = [
        fila_log(ip="187.190.12.4", status=202, sujeto="S-PES-01"),
    ]

    hallazgos = evaluar_token_desconocido(filas, IPS_PERMITIDAS)

    assert len(hallazgos) == 1
    hallazgo = hallazgos[0]
    assert hallazgo.regla_id == REGLA_TOKEN_DESCONOCIDO_ID
    assert hallazgo.ip_origen == "187.190.12.4"
    assert hallazgo.accion == ACCION_REVOCAR_TOKEN
    assert hallazgo.clave == "sensor:S-PES-01"
    assert hallazgo.detalle["sensor_id"] == "S-PES-01"


def test_token_desconocido_ignora_ips_de_confianza():
    filas = [fila_log(ip="127.0.0.1", status=202)]

    assert evaluar_token_desconocido(filas, IPS_PERMITIDAS) == []


def test_token_desconocido_ignora_autenticaciones_fallidas():
    filas = [fila_log(ip="187.190.12.4", status=401)]

    assert evaluar_token_desconocido(filas, IPS_PERMITIDAS) == []


# --- Lecturas imposibles ----------------------------------------------------


def test_lecturas_imposibles_dispara_con_salto_mayor_a_ocho():
    filas = [
        fila_lectura(id=1, temperatura_c=2.0, segundos_atras=30),
        fila_lectura(id=2, temperatura_c=12.0, segundos_atras=0),
    ]

    hallazgos = evaluar_lecturas_imposibles(filas, AHORA)

    assert len(hallazgos) == 1
    hallazgo = hallazgos[0]
    assert hallazgo.regla_id == REGLA_LECTURAS_IMPOSIBLES_ID
    assert hallazgo.accion == ACCION_MARCAR_LECTURAS
    assert hallazgo.ip_origen is None
    assert hallazgo.clave == "camara:1:lectura:2"
    assert hallazgo.detalle["lectura_id"] == 2
    assert hallazgo.detalle["lectura_anterior_id"] == 1
    assert hallazgo.detalle["delta_c"] == 10.0
    assert hallazgo.detalle["segundos"] == 30.0


def test_lecturas_imposibles_ordena_por_recibida_en():
    # Llegan al revés: la regla debe ordenarlas antes de comparar.
    filas = [
        fila_lectura(id=2, temperatura_c=12.0, segundos_atras=0),
        fila_lectura(id=1, temperatura_c=2.0, segundos_atras=30),
    ]

    hallazgos = evaluar_lecturas_imposibles(filas, AHORA)

    assert [hallazgo.detalle["lectura_id"] for hallazgo in hallazgos] == [2]


def test_lecturas_imposibles_no_dispara_con_exactamente_ocho():
    filas = [
        fila_lectura(id=1, temperatura_c=2.0, segundos_atras=30),
        fila_lectura(id=2, temperatura_c=10.0, segundos_atras=0),
    ]

    assert evaluar_lecturas_imposibles(filas, AHORA) == []


def test_lecturas_imposibles_no_dispara_fuera_de_la_ventana():
    filas = [
        fila_lectura(id=1, temperatura_c=2.0, segundos_atras=61),
        fila_lectura(id=2, temperatura_c=12.0, segundos_atras=0),
    ]

    assert evaluar_lecturas_imposibles(filas, AHORA) == []


def test_lecturas_imposibles_dispara_en_el_limite_de_sesenta_segundos():
    filas = [
        fila_lectura(id=1, temperatura_c=2.0, segundos_atras=60),
        fila_lectura(id=2, temperatura_c=12.0, segundos_atras=0),
    ]

    assert len(evaluar_lecturas_imposibles(filas, AHORA)) == 1


def test_lecturas_imposibles_evalua_cada_camara_por_separado():
    filas = [
        fila_lectura(id=1, camara_id=1, temperatura_c=2.0, segundos_atras=30),
        fila_lectura(id=2, camara_id=1, temperatura_c=12.0, segundos_atras=0),
        fila_lectura(id=3, camara_id=2, temperatura_c=5.0, segundos_atras=30),
        fila_lectura(id=4, camara_id=2, temperatura_c=-5.0, segundos_atras=0),
    ]

    hallazgos = evaluar_lecturas_imposibles(filas, AHORA)

    assert [hallazgo.detalle["camara_id"] for hallazgo in hallazgos] == [1, 2]
    assert [hallazgo.detalle["lectura_id"] for hallazgo in hallazgos] == [2, 4]


# --- Orquestación -----------------------------------------------------------


class RepositorioFalso:
    """Doble en memoria que imita la interfaz `Repositorio`."""

    def __init__(
        self,
        *,
        logs: Sequence[FilaLog] = (),
        lecturas: Sequence[FilaLectura] = (),
    ) -> None:
        self.logs = list(logs)
        self.lecturas = list(lecturas)
        self.alertas: list[tuple[Hallazgo, datetime]] = []
        self.bloqueos: dict[str, datetime] = {}
        self.sensores_desactivados: list[str] = []
        self.lecturas_marcadas: list[int] = []

    def logs_desde(self, desde: datetime) -> list[FilaLog]:
        return [fila for fila in self.logs if fila.ts >= desde]

    def lecturas_desde(self, desde: datetime) -> list[FilaLectura]:
        return [fila for fila in self.lecturas if fila.recibida_en >= desde]

    def alerta_reciente(self, regla_id: str, clave: str, desde: datetime) -> bool:
        return any(
            hallazgo.regla_id == regla_id and hallazgo.clave == clave and ts >= desde
            for hallazgo, ts in self.alertas
        )

    def bloqueo_activo(self, ip: str, ahora: datetime) -> bool:
        hasta = self.bloqueos.get(ip)
        return hasta is not None and hasta > ahora

    def registrar_alerta(self, hallazgo: Hallazgo, ahora: datetime) -> None:
        self.alertas.append((hallazgo, ahora))

    def bloquear_ip(self, ip: str, hasta: datetime, motivo: str) -> None:
        self.bloqueos[ip] = hasta

    def desactivar_sensor(self, sensor_id: str) -> None:
        self.sensores_desactivados.append(sensor_id)

    def marcar_lectura_sospechosa(self, lectura_id: int) -> None:
        self.lecturas_marcadas.append(lectura_id)


def test_detectar_bloquea_ip_y_no_duplica_en_la_siguiente_pasada():
    repo = RepositorioFalso(
        logs=[fila_log(segundos_atras=indice) for indice in range(10)],
    )

    primera = detectar(repo, AHORA, IPS_PERMITIDAS)
    segunda = detectar(repo, AHORA + timedelta(minutes=1), IPS_PERMITIDAS)

    assert len(primera) == 1
    assert repo.bloqueos["127.0.0.2"] == AHORA + timedelta(minutes=BLOQUEO_MINUTOS)
    assert len(repo.alertas) == 1
    assert segunda == []


def test_detectar_no_bloquea_una_ip_de_confianza():
    repo = RepositorioFalso(
        logs=[fila_log(ip="127.0.0.1", segundos_atras=indice) for indice in range(10)],
    )

    hallazgos = detectar(repo, AHORA, IPS_PERMITIDAS)

    assert hallazgos == []
    assert repo.alertas == []
    assert repo.bloqueos == {}


def test_detectar_revoca_el_sensor_con_token_desconocido():
    repo = RepositorioFalso(
        logs=[fila_log(ip="187.190.12.4", status=202, sujeto="S-PES-01")],
    )

    hallazgos = detectar(repo, AHORA, IPS_PERMITIDAS)

    assert [hallazgo.accion for hallazgo in hallazgos] == [ACCION_REVOCAR_TOKEN]
    assert repo.sensores_desactivados == ["S-PES-01"]
    assert repo.alertas[0][0].ip_origen == "187.190.12.4"


def test_detectar_dedupea_varios_eventos_del_mismo_sensor():
    repo = RepositorioFalso(
        logs=[
            fila_log(ip="187.190.12.4", status=202, segundos_atras=10),
            fila_log(ip="187.190.12.4", status=202, segundos_atras=5),
        ],
    )

    hallazgos = detectar(repo, AHORA, IPS_PERMITIDAS)

    assert len(hallazgos) == 1
    assert repo.sensores_desactivados == ["S-PES-01"]
    assert len(repo.alertas) == 1


def test_detectar_marca_la_lectura_sospechosa():
    repo = RepositorioFalso(
        lecturas=[
            fila_lectura(id=1, temperatura_c=2.0, segundos_atras=30),
            fila_lectura(id=2, temperatura_c=12.0, segundos_atras=0),
        ],
    )

    hallazgos = detectar(repo, AHORA, IPS_PERMITIDAS)

    assert [hallazgo.accion for hallazgo in hallazgos] == [ACCION_MARCAR_LECTURAS]
    assert repo.lecturas_marcadas == [2]
    assert repo.alertas[0][0].detalle["camara_id"] == 1


def test_detectar_sin_escribir_no_toca_la_base():
    repo = RepositorioFalso(
        logs=[fila_log(segundos_atras=indice) for indice in range(10)],
    )

    hallazgos = detectar(repo, AHORA, IPS_PERMITIDAS, escribir=False)

    assert len(hallazgos) == 1
    assert repo.alertas == []
    assert repo.bloqueos == {}
