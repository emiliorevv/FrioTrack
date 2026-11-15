"""Pruebas puras del detector SIEM: sin base de datos ni red."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime, timedelta

import pytest
from security.detector import detector as modulo_detector
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
    cargar_configuracion,
    compilar_redes,
    detectar,
    es_ip_permitida,
    evaluar_fuerza_bruta,
    evaluar_lecturas_imposibles,
    evaluar_token_desconocido,
    filtrar_nuevos,
    normalizar_database_url,
    parsear_ips,
    validar_ips_produccion,
)

AHORA = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
IPS_PERMITIDAS = ["127.0.0.1", "::1"]
REDES_PERMITIDAS = compilar_redes(IPS_PERMITIDAS)


def fila_log(
    *,
    segundos_atras: int = 0,
    ip: str = "127.0.0.2",
    ruta: str = "/api/telemetria",
    status: int = 401,
    credencial: str = "sensor",
    sujeto: str = "S-PES-01",
    ahora: datetime = AHORA,
) -> FilaLog:
    return FilaLog(
        ts=ahora - timedelta(seconds=segundos_atras),
        ip_origen=ip,
        ruta=ruta,
        status=status,
        credencial=credencial,
        sujeto=sujeto,
    )


def fila_lectura(
    *,
    id: int,
    camara_id: int = 1,
    temperatura_c: float,
    segundos_atras: int,
    sospechosa: bool = False,
) -> FilaLectura:
    return FilaLectura(
        id=id,
        camara_id=camara_id,
        temperatura_c=temperatura_c,
        recibida_en=AHORA - timedelta(seconds=segundos_atras),
        sospechosa=sospechosa,
    )


def hallazgo_falso(clave: str) -> Hallazgo:
    return Hallazgo(
        regla_id="regla-de-prueba",
        regla="Regla de prueba",
        severidad="medium",
        ip_origen=None,
        detalle={"clave": clave},
        accion=ACCION_MARCAR_LECTURAS,
        clave=clave,
    )


# --- Allowlist: CIDR e IPv4-mapped -----------------------------------------


def test_compilar_redes_acepta_ips_y_cidr():
    redes = compilar_redes(["127.0.0.1", "::1", "203.0.113.0/28"])

    assert es_ip_permitida("127.0.0.1", redes)
    assert es_ip_permitida("::1", redes)
    assert es_ip_permitida("203.0.113.0", redes)
    assert es_ip_permitida("203.0.113.15", redes)
    assert not es_ip_permitida("203.0.113.16", redes)
    assert not es_ip_permitida("127.0.0.2", redes)


def test_allowlist_normaliza_ipv4_mapped_en_ambos_sentidos():
    redes = compilar_redes(["127.0.0.1", "::ffff:192.0.2.10"])

    assert es_ip_permitida("::ffff:127.0.0.1", redes)
    assert es_ip_permitida("192.0.2.10", redes)
    assert es_ip_permitida("::ffff:192.0.2.10", redes)
    assert not es_ip_permitida("192.0.2.11", redes)


def test_allowlist_rechaza_valores_invalidos():
    with pytest.raises(ValueError, match="allowlist"):
        compilar_redes(["127.0.0.1", "no-es-una-ip"])


def test_allowlist_ignora_textos_vacios():
    assert compilar_redes(["", " ", "127.0.0.1"]) == compilar_redes(["127.0.0.1"])


def test_parsear_ips_limpia_espacios_y_vacios():
    assert parsear_ips(" 127.0.0.1, ::1, ") == ["127.0.0.1", "::1"]


# --- Allowlist en producción ------------------------------------------------


def test_produccion_rechaza_allowlist_solo_loopback():
    with pytest.raises(RuntimeError, match="loopback"):
        validar_ips_produccion(
            ["127.0.0.1", "::1"],
            es_produccion=True,
            permitir_loopback=False,
        )


def test_produccion_acepta_allowlist_real():
    validar_ips_produccion(
        ["203.0.113.0/28"],
        es_produccion=True,
        permitir_loopback=False,
    )


def test_produccion_permite_loopback_solo_con_el_flag():
    validar_ips_produccion(
        ["127.0.0.1", "::1"],
        es_produccion=True,
        permitir_loopback=True,
    )


def test_produccion_rechaza_allowlist_vacia_aunque_haya_flag():
    with pytest.raises(RuntimeError, match="vacía"):
        validar_ips_produccion([], es_produccion=True, permitir_loopback=True)


def test_local_acepta_loopback_por_defecto():
    validar_ips_produccion(
        ["127.0.0.1", "::1"],
        es_produccion=False,
        permitir_loopback=False,
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

    hallazgos = evaluar_token_desconocido(filas, REDES_PERMITIDAS)

    assert len(hallazgos) == 1
    hallazgo = hallazgos[0]
    assert hallazgo.regla_id == REGLA_TOKEN_DESCONOCIDO_ID
    assert hallazgo.ip_origen == "187.190.12.4"
    assert hallazgo.accion == ACCION_REVOCAR_TOKEN
    assert hallazgo.clave == "sensor:S-PES-01"
    assert hallazgo.detalle["sensor_id"] == "S-PES-01"


def test_token_desconocido_ignora_ips_de_confianza():
    filas = [fila_log(ip="127.0.0.1", status=202)]

    assert evaluar_token_desconocido(filas, REDES_PERMITIDAS) == []


def test_token_desconocido_normaliza_mapped_y_usa_cidr():
    redes = compilar_redes(["127.0.0.1", "203.0.113.0/28"])
    filas = [
        fila_log(ip="::ffff:127.0.0.1", status=202),
        fila_log(ip="203.0.113.9", status=202),
        fila_log(ip="203.0.113.200", status=202),
    ]

    hallazgos = evaluar_token_desconocido(filas, redes)

    assert [hallazgo.ip_origen for hallazgo in hallazgos] == ["203.0.113.200"]


def test_token_desconocido_ignora_autenticaciones_fallidas():
    filas = [fila_log(ip="187.190.12.4", status=401)]

    assert evaluar_token_desconocido(filas, REDES_PERMITIDAS) == []


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


def test_lecturas_imposibles_no_marca_la_lectura_tras_un_pico():
    # 2.0 -> 15.0 (se marca) -> 2.1: la 2.1 no se compara contra el pico.
    filas = [
        fila_lectura(id=1, temperatura_c=2.0, segundos_atras=60),
        fila_lectura(id=2, temperatura_c=15.0, segundos_atras=30),
        fila_lectura(id=3, temperatura_c=2.1, segundos_atras=0),
    ]

    hallazgos = evaluar_lecturas_imposibles(filas, AHORA)

    assert [hallazgo.detalle["lectura_id"] for hallazgo in hallazgos] == [2]


def test_lecturas_imposibles_ignora_sospechosas_como_baseline():
    # La 15.0 ya venía marcada; la 20.0 se compara contra la última limpia (2.0).
    filas = [
        fila_lectura(id=1, temperatura_c=2.0, segundos_atras=60),
        fila_lectura(id=2, temperatura_c=15.0, segundos_atras=30, sospechosa=True),
        fila_lectura(id=3, temperatura_c=20.0, segundos_atras=0),
    ]

    hallazgos = evaluar_lecturas_imposibles(filas, AHORA)

    assert len(hallazgos) == 1
    assert hallazgos[0].detalle["lectura_id"] == 3
    assert hallazgos[0].detalle["lectura_anterior_id"] == 1


def test_lecturas_imposibles_ignora_una_sospechosa_previa():
    # Con el pico ya marcado no hay alerta nueva para la lectura normal.
    filas = [
        fila_lectura(id=1, temperatura_c=2.0, segundos_atras=60),
        fila_lectura(id=2, temperatura_c=15.0, segundos_atras=30, sospechosa=True),
        fila_lectura(id=3, temperatura_c=2.1, segundos_atras=0),
    ]

    assert evaluar_lecturas_imposibles(filas, AHORA) == []


# --- Dry-run -----------------------------------------------------------------


def test_filtrar_nuevos_no_repite_claves():
    primero = hallazgo_falso("a")
    segundo = hallazgo_falso("b")
    tercero = hallazgo_falso("c")
    vistos: set[tuple[str, str]] = set()

    assert filtrar_nuevos([primero, segundo], vistos) == [primero, segundo]
    assert filtrar_nuevos([primero, segundo], vistos) == []
    assert filtrar_nuevos([primero, tercero], vistos) == [tercero]


# --- Configuración del backend ----------------------------------------------


def test_normalizar_database_url_quita_el_driver_de_sqlalchemy():
    assert (
        normalizar_database_url("postgresql+psycopg://u:p@host:5432/db")
        == "postgresql://u:p@host:5432/db"
    )


def test_cargar_configuracion_prioriza_la_url_explicita(monkeypatch):
    monkeypatch.setenv("ENTORNO", "local")
    monkeypatch.delenv("RENDER", raising=False)

    configuracion = cargar_configuracion("postgresql+psycopg://u:p@host:5432/db")

    assert configuracion.database_url == "postgresql://u:p@host:5432/db"
    assert configuracion.es_produccion is False


# --- Repositorio Postgres (doble de conexión, sin red) ----------------------


class _CursorFalso:
    def __init__(self, conexion: _ConexionFalsa) -> None:
        self._conexion = conexion
        self._filas: list[tuple[object, ...]] = []

    def __enter__(self) -> _CursorFalso:
        return self

    def __exit__(self, *_excepcion: object) -> None:
        return None

    def execute(self, sql: str, parametros: Sequence[object] = ()) -> None:
        self._conexion.consultas.append(sql)
        self._filas = [(False,)] if "EXISTS" in sql else []

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._filas

    def fetchone(self) -> tuple[object, ...]:
        return self._filas[0]


class _ConexionFalsa:
    def __init__(self) -> None:
        self.consultas: list[str] = []
        self.transacciones = 0
        self.cerrada = False

    def cursor(self) -> _CursorFalso:
        return _CursorFalso(self)

    def transaction(self):
        self.transacciones += 1
        return nullcontext()

    def close(self) -> None:
        self.cerrada = True


def test_repositorio_abre_una_conexion_y_la_reutiliza(monkeypatch):
    conexion = _ConexionFalsa()
    llamadas: list[tuple[str, dict[str, object]]] = []

    def conectar(url: str, **opciones: object) -> _ConexionFalsa:
        llamadas.append((url, opciones))
        return conexion

    monkeypatch.setattr(modulo_detector.psycopg, "connect", conectar)

    repo = modulo_detector.RepositorioPostgres("postgresql://x")
    with repo as abierto:
        assert abierto.logs_desde(AHORA) == []
        assert abierto.lecturas_desde(AHORA) == []
        assert abierto.alerta_reciente("r", "c", AHORA) is False
        assert abierto.bloqueo_activo("127.0.0.2", AHORA) is False
        with abierto.transaccion():
            abierto.registrar_alerta(hallazgo_falso("c"), AHORA)
        assert len(conexion.consultas) == 5

    assert llamadas == [("postgresql://x", {"autocommit": True})]
    assert conexion.cerrada is True
    assert conexion.transacciones == 1
    with pytest.raises(RuntimeError, match="bloque with"):
        repo.logs_desde(AHORA)


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
        self.fallar_accion: str | None = None

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

    @contextmanager
    def transaccion(self) -> Iterator[None]:
        """Imita el rollback: si algo falla, la alerta y la acción no quedan."""
        estado = (
            list(self.alertas),
            dict(self.bloqueos),
            list(self.sensores_desactivados),
            list(self.lecturas_marcadas),
        )
        try:
            yield
        except Exception:
            self.alertas = list(estado[0])
            self.bloqueos = dict(estado[1])
            self.sensores_desactivados = list(estado[2])
            self.lecturas_marcadas = list(estado[3])
            raise

    def registrar_alerta(self, hallazgo: Hallazgo, ahora: datetime) -> None:
        self.alertas.append((hallazgo, ahora))

    def bloquear_ip(self, ip: str, hasta: datetime, motivo: str) -> None:
        if self.fallar_accion == ACCION_BLOQUEAR_IP:
            raise RuntimeError("fallo simulado al bloquear la IP")
        self.bloqueos[ip] = hasta

    def desactivar_sensor(self, sensor_id: str) -> None:
        if self.fallar_accion == ACCION_REVOCAR_TOKEN:
            raise RuntimeError("fallo simulado al revocar el token")
        self.sensores_desactivados.append(sensor_id)

    def marcar_lectura_sospechosa(self, lectura_id: int) -> None:
        if self.fallar_accion == ACCION_MARCAR_LECTURAS:
            raise RuntimeError("fallo simulado al marcar la lectura")
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


def test_detectar_no_bloquea_una_ip_mapeada_de_confianza():
    repo = RepositorioFalso(
        logs=[
            fila_log(ip="::ffff:127.0.0.1", segundos_atras=indice) for indice in range(10)
        ],
    )

    assert detectar(repo, AHORA, IPS_PERMITIDAS) == []
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


def test_accion_fallida_revierte_la_alerta_y_reintenta():
    repo = RepositorioFalso(
        logs=[fila_log(segundos_atras=indice) for indice in range(10)],
    )
    repo.fallar_accion = ACCION_BLOQUEAR_IP

    assert detectar(repo, AHORA, IPS_PERMITIDAS) == []
    assert repo.alertas == []
    assert repo.bloqueos == {}

    repo.fallar_accion = None
    hallazgos = detectar(repo, AHORA + timedelta(seconds=30), IPS_PERMITIDAS)

    assert len(hallazgos) == 1
    assert len(repo.alertas) == 1
    assert "127.0.0.2" in repo.bloqueos


def test_bloqueo_corto_expirado_vuelve_a_alertar():
    repo = RepositorioFalso(
        logs=[fila_log(segundos_atras=indice) for indice in range(10)],
    )

    detectar(repo, AHORA, IPS_PERMITIDAS, bloqueo_minutos=5)
    assert len(repo.alertas) == 1

    despues = AHORA + timedelta(minutes=6)
    repo.logs += [fila_log(segundos_atras=indice, ahora=despues) for indice in range(10)]
    hallazgos = detectar(repo, despues, IPS_PERMITIDAS, bloqueo_minutos=5)

    assert len(hallazgos) == 1
    assert len(repo.alertas) == 2
    assert repo.bloqueos["127.0.0.2"] == despues + timedelta(minutes=5)
