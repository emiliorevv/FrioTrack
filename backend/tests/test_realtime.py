"""Pruebas del bus en memoria y de la tarea global de KPIs que alimentan el SSE."""

import asyncio
import threading
from contextlib import suppress

import pytest

from app.realtime import kpis as kpis_mod
from app.realtime.bus import EVENTO_CERRAR, TAMANO_COLA, EventBus


def test_suscribir_publicar_y_recibir():
    bus = EventBus()

    async def escenario():
        cola = bus.suscribir(1)
        try:
            bus.publicar("lectura", {"camara_id": 1}, 1)
            return await asyncio.wait_for(cola.get(), timeout=1)
        finally:
            bus.desuscribir(cola)

    assert asyncio.run(escenario()) == ("lectura", {"camara_id": 1})


def test_publicar_desde_otro_hilo_entrega_el_evento():
    """La ingesta corre en el threadpool: el bus debe cruzar de hilo."""
    bus = EventBus()

    async def escenario():
        cola = bus.suscribir(1)
        hilo = threading.Thread(target=bus.publicar, args=("lectura", {"camara_id": 7}, 1))
        try:
            hilo.start()
            return await asyncio.wait_for(cola.get(), timeout=1)
        finally:
            hilo.join()
            bus.desuscribir(cola)

    assert asyncio.run(escenario()) == ("lectura", {"camara_id": 7})


def test_publicar_sin_suscriptores_no_falla():
    bus = EventBus()

    bus.publicar("lectura", {"camara_id": 1}, 1)


def test_hay_suscriptores_refleja_las_conexiones():
    bus = EventBus()

    async def escenario():
        antes = bus.hay_suscriptores()
        cola = bus.suscribir(1)
        durante = bus.hay_suscriptores()
        bus.desuscribir(cola)
        return antes, durante, bus.hay_suscriptores()

    assert asyncio.run(escenario()) == (False, True, False)


def test_desuscribir_deja_de_entregar_eventos():
    bus = EventBus()

    async def escenario():
        cola = bus.suscribir(1)
        bus.desuscribir(cola)
        bus.publicar("lectura", {"camara_id": 1}, 1)
        await asyncio.sleep(0)
        return cola.empty()

    assert asyncio.run(escenario()) is True


def test_cola_llena_descarta_la_lectura_sin_bloquear():
    bus = EventBus()

    async def escenario():
        cola = bus.suscribir(1)
        try:
            for indice in range(TAMANO_COLA):
                cola.put_nowait(("relleno", {"indice": indice}))
            bus.publicar("lectura", {"camara_id": 1}, 1)
            await asyncio.sleep(0)
            return cola.qsize(), cola.get_nowait()
        finally:
            bus.desuscribir(cola)

    tamano, primer_evento = asyncio.run(escenario())
    assert tamano == TAMANO_COLA
    assert primer_evento == ("relleno", {"indice": 0})


def test_cola_llena_pide_reconectar_para_evento_de_estado():
    bus = EventBus()

    async def escenario():
        cola = bus.suscribir(1)
        try:
            for indice in range(TAMANO_COLA):
                cola.put_nowait(("relleno", {"indice": indice}))
            bus.publicar("alerta_abierta", {"id": 31}, 1)
            await asyncio.sleep(0)
            return cola.qsize(), cola.get_nowait()
        finally:
            bus.desuscribir(cola)

    tamano, evento = asyncio.run(escenario())
    assert tamano == 1
    assert evento == (EVENTO_CERRAR, {})


@pytest.mark.parametrize("descartable", ["lectura", "kpis"])
def test_cola_llena_hace_espacio_para_la_notificacion(descartable: str):
    """La notificación no se pierde: se descarta la muestra más antigua."""
    bus = EventBus()

    async def escenario():
        cola = bus.suscribir(1)
        try:
            for indice in range(TAMANO_COLA):
                cola.put_nowait((descartable, {"indice": indice}))
            bus.publicar("notificacion", {"camara_id": 1}, 1)
            await asyncio.sleep(0)
            eventos = []
            while not cola.empty():
                eventos.append(cola.get_nowait())
            return eventos
        finally:
            bus.desuscribir(cola)

    eventos = asyncio.run(escenario())
    assert len(eventos) == TAMANO_COLA
    assert eventos[0] == (descartable, {"indice": 1})  # se fue el más antiguo
    assert eventos[-1] == ("notificacion", {"camara_id": 1})


def test_notificacion_solo_descarta_el_primer_evento_descartable():
    """Los eventos de estado se conservan y mantienen su orden."""
    bus = EventBus()

    async def escenario():
        cola = bus.suscribir(1)
        try:
            for indice in range(TAMANO_COLA):
                tipo = "kpis" if indice == 40 else "alerta_abierta"
                cola.put_nowait((tipo, {"indice": indice}))
            bus.publicar("notificacion", {"camara_id": 1}, 1)
            await asyncio.sleep(0)
            eventos = []
            while not cola.empty():
                eventos.append(cola.get_nowait())
            return eventos
        finally:
            bus.desuscribir(cola)

    eventos = asyncio.run(escenario())
    assert len(eventos) == TAMANO_COLA
    assert eventos[0] == ("alerta_abierta", {"indice": 0})
    assert eventos[39] == ("alerta_abierta", {"indice": 39})
    assert eventos[40] == ("alerta_abierta", {"indice": 41})  # el kpis 40 se descartó
    assert eventos[-1] == ("notificacion", {"camara_id": 1})


def test_cola_llena_descarta_kpis_sin_pedir_reconexion():
    """`kpis` es una foto periódica, no un evento de estado."""
    bus = EventBus()

    async def escenario():
        cola = bus.suscribir(1)
        try:
            for indice in range(TAMANO_COLA):
                cola.put_nowait(("lectura", {"indice": indice}))
            bus.publicar("kpis", {"alertas_activas": 1}, 1)
            await asyncio.sleep(0)
            return cola.qsize(), cola.get_nowait()
        finally:
            bus.desuscribir(cola)

    tamano, primero = asyncio.run(escenario())
    assert tamano == TAMANO_COLA
    assert primero == ("lectura", {"indice": 0})


def test_cola_llena_sin_descartables_entrega_la_notificacion_y_reconecta():
    bus = EventBus()

    async def escenario():
        cola = bus.suscribir(1)
        try:
            for indice in range(TAMANO_COLA):
                cola.put_nowait(("alerta_abierta", {"id": indice}))
            bus.publicar("notificacion", {"camara_id": 1}, 1)
            await asyncio.sleep(0)
            eventos = []
            while not cola.empty():
                eventos.append(cola.get_nowait())
            return eventos
        finally:
            bus.desuscribir(cola)

    assert asyncio.run(escenario()) == [
        ("notificacion", {"camara_id": 1}),
        (EVENTO_CERRAR, {}),
    ]


def test_publicar_reparte_a_colas_de_loops_distintos():
    """Cada conexión puede vivir en su propio loop (TestClient, segundo loop)."""
    bus = EventBus()
    listos = threading.Barrier(3)  # dos conexiones y el hilo que publica
    recibidos: list[tuple[str, dict]] = []
    errores: list[BaseException] = []

    def escuchar() -> None:
        async def esperar():
            cola = bus.suscribir(1)
            try:
                listos.wait(timeout=2)  # ambos loops ya tienen su cola
                return await asyncio.wait_for(cola.get(), timeout=2)
            finally:
                bus.desuscribir(cola)

        try:
            recibidos.append(asyncio.run(esperar()))
        except BaseException as error:  # noqa: BLE001 - se reporta en el assert
            errores.append(error)

    hilos = [threading.Thread(target=escuchar) for _ in range(2)]
    for hilo in hilos:
        hilo.start()
    listos.wait(timeout=2)
    bus.publicar("alerta_abierta", {"id": 31}, 1)
    for hilo in hilos:
        hilo.join(timeout=3)

    assert errores == []
    assert recibidos == [("alerta_abierta", {"id": 31}), ("alerta_abierta", {"id": 31})]


def test_loop_cerrado_de_otra_conexion_no_tumba_el_reparto():
    """Una cola suscrita a un loop que se cerró no debe bloquear a las demás."""
    bus = EventBus()
    listo = threading.Event()
    resultado: list[tuple[str, dict]] = []

    def escuchar() -> None:
        async def esperar():
            cola = bus.suscribir(1)
            try:
                listo.set()
                return await asyncio.wait_for(cola.get(), timeout=3)
            finally:
                bus.desuscribir(cola)

        resultado.append(asyncio.run(esperar()))

    hilo = threading.Thread(target=escuchar)
    hilo.start()
    assert listo.wait(timeout=2)

    async def suscribir_y_morir():
        bus.suscribir(1)  # se deja registrada: su loop se cierra al salir

    asyncio.run(suscribir_y_morir())

    bus.publicar("lectura", {"camara_id": 3}, 1)
    hilo.join(timeout=4)

    assert resultado == [("lectura", {"camara_id": 3})]


def test_tarea_global_de_kpis_no_calcula_sin_suscriptores(monkeypatch):
    calculos: list[bool] = []
    monkeypatch.setattr(
        kpis_mod,
        "publicar_kpis_de_todos_los_tenants",
        lambda: calculos.append(True),
    )

    async def escenario():
        monkeypatch.setattr(kpis_mod, "bus", EventBus())
        tarea = asyncio.create_task(kpis_mod.publicar_kpis_periodicos(0.01))
        await asyncio.sleep(0.05)
        tarea.cancel()
        with suppress(asyncio.CancelledError):
            await tarea

    asyncio.run(escenario())
    assert calculos == []


def test_tarea_global_de_kpis_calcula_cuando_hay_suscriptores(monkeypatch):
    calculos: list[bool] = []
    monkeypatch.setattr(
        kpis_mod,
        "publicar_kpis_de_todos_los_tenants",
        lambda: calculos.append(True),
    )

    async def escenario():
        bus = EventBus()
        monkeypatch.setattr(kpis_mod, "bus", bus)
        cola = bus.suscribir(1)
        tarea = asyncio.create_task(kpis_mod.publicar_kpis_periodicos(0.01))
        try:
            await asyncio.sleep(0.05)
        finally:
            tarea.cancel()
            with suppress(asyncio.CancelledError):
                await tarea
            bus.desuscribir(cola)

    asyncio.run(escenario())
    assert calculos  # al menos un ciclo con suscriptores


class _SesionDeTenants:
    """Sesión mínima: devuelve los tenants con cámaras y cierra al salir."""

    def __init__(self, tenants: list[int]) -> None:
        self.tenants = tenants

    def __enter__(self):
        return self

    def __exit__(self, *_excepcion: object) -> None:
        pass

    def scalars(self, _sentencia: object) -> list[int]:
        return self.tenants


def test_publicar_kpis_calcula_una_vez_por_tenant_y_reparte(monkeypatch):
    calculos: list[int] = []
    monkeypatch.setattr(
        kpis_mod, "SessionLocal", lambda bind=None: _SesionDeTenants([1, 2])
    )
    monkeypatch.setattr(kpis_mod, "get_engine", lambda: None)
    monkeypatch.setattr(
        kpis_mod,
        "calcular_kpis",
        lambda _session, tenant: calculos.append(tenant) or {"tenant": tenant},
    )

    async def escenario():
        bus = EventBus()
        monkeypatch.setattr(kpis_mod, "bus", bus)
        cola1 = bus.suscribir(1)
        cola2 = bus.suscribir(2)
        try:
            kpis_mod.publicar_kpis_de_todos_los_tenants()
            await asyncio.sleep(0)
            return cola1.get_nowait(), cola2.get_nowait(), cola1.empty(), cola2.empty()
        finally:
            bus.desuscribir(cola1)
            bus.desuscribir(cola2)

    evento1, evento2, vacia1, vacia2 = asyncio.run(escenario())

    # Una sola computación por tenant, no una por conexión.
    assert calculos == [1, 2]
    assert evento1 == ("kpis", {"tenant": 1})
    assert evento2 == ("kpis", {"tenant": 2})
    assert vacia1 and vacia2


# --- Aislamiento del bus ----------------------------------------------------


def test_evento_de_otro_tenant_no_llega_a_la_cola():
    bus = EventBus()

    async def escenario():
        cola1 = bus.suscribir(1)
        cola2 = bus.suscribir(2)
        try:
            bus.publicar("alerta_abierta", {"camara_id": 6}, 2)
            await asyncio.sleep(0)
            return cola1.empty(), cola2.get_nowait()
        finally:
            bus.desuscribir(cola1)
            bus.desuscribir(cola2)

    vacia1, evento2 = asyncio.run(escenario())
    assert vacia1 is True
    assert evento2 == ("alerta_abierta", {"camara_id": 6})


def test_evento_sin_tenant_no_llega_a_nadie():
    bus = EventBus()

    async def escenario():
        cola1 = bus.suscribir(1)
        cola2 = bus.suscribir(2)
        try:
            bus.publicar("lectura", {"camara_id": 1}, None)
            await asyncio.sleep(0)
            return cola1.empty(), cola2.empty()
        finally:
            bus.desuscribir(cola1)
            bus.desuscribir(cola2)

    assert asyncio.run(escenario()) == (True, True)
