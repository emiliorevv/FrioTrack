"""Pruebas del bus en memoria y de la tarea global de KPIs que alimentan el SSE."""

import asyncio
import threading
from contextlib import suppress

from app.realtime import kpis as kpis_mod
from app.realtime.bus import EVENTO_CERRAR, TAMANO_COLA, EventBus


def test_suscribir_publicar_y_recibir():
    bus = EventBus()

    async def escenario():
        cola = bus.suscribir()
        try:
            bus.publicar("lectura", {"camara_id": 1})
            return await asyncio.wait_for(cola.get(), timeout=1)
        finally:
            bus.desuscribir(cola)

    assert asyncio.run(escenario()) == ("lectura", {"camara_id": 1})


def test_publicar_desde_otro_hilo_entrega_el_evento():
    """La ingesta corre en el threadpool: el bus debe cruzar de hilo."""
    bus = EventBus()

    async def escenario():
        cola = bus.suscribir()
        hilo = threading.Thread(target=bus.publicar, args=("lectura", {"camara_id": 7}))
        try:
            hilo.start()
            return await asyncio.wait_for(cola.get(), timeout=1)
        finally:
            hilo.join()
            bus.desuscribir(cola)

    assert asyncio.run(escenario()) == ("lectura", {"camara_id": 7})


def test_publicar_sin_suscriptores_no_falla():
    bus = EventBus()

    bus.publicar("lectura", {"camara_id": 1})


def test_hay_suscriptores_refleja_las_conexiones():
    bus = EventBus()

    async def escenario():
        antes = bus.hay_suscriptores()
        cola = bus.suscribir()
        durante = bus.hay_suscriptores()
        bus.desuscribir(cola)
        return antes, durante, bus.hay_suscriptores()

    assert asyncio.run(escenario()) == (False, True, False)


def test_desuscribir_deja_de_entregar_eventos():
    bus = EventBus()

    async def escenario():
        cola = bus.suscribir()
        bus.desuscribir(cola)
        bus.publicar("lectura", {"camara_id": 1})
        await asyncio.sleep(0)
        return cola.empty()

    assert asyncio.run(escenario()) is True


def test_cola_llena_descarta_la_lectura_sin_bloquear():
    bus = EventBus()

    async def escenario():
        cola = bus.suscribir()
        try:
            for indice in range(TAMANO_COLA):
                cola.put_nowait(("relleno", {"indice": indice}))
            bus.publicar("lectura", {"camara_id": 1})
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
        cola = bus.suscribir()
        try:
            for indice in range(TAMANO_COLA):
                cola.put_nowait(("relleno", {"indice": indice}))
            bus.publicar("alerta_abierta", {"id": 31})
            await asyncio.sleep(0)
            return cola.qsize(), cola.get_nowait()
        finally:
            bus.desuscribir(cola)

    tamano, evento = asyncio.run(escenario())
    assert tamano == 1
    assert evento == (EVENTO_CERRAR, {})


def test_publicar_reparte_a_colas_de_loops_distintos():
    """Cada conexión puede vivir en su propio loop (TestClient, segundo loop)."""
    bus = EventBus()
    listos = threading.Barrier(3)  # dos conexiones y el hilo que publica
    recibidos: list[tuple[str, dict]] = []
    errores: list[BaseException] = []

    def escuchar() -> None:
        async def esperar():
            cola = bus.suscribir()
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
    bus.publicar("alerta_abierta", {"id": 31})
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
            cola = bus.suscribir()
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
        bus.suscribir()  # se deja registrada: su loop se cierra al salir

    asyncio.run(suscribir_y_morir())

    bus.publicar("lectura", {"camara_id": 3})
    hilo.join(timeout=4)

    assert resultado == [("lectura", {"camara_id": 3})]


def test_tarea_global_de_kpis_no_calcula_sin_suscriptores(monkeypatch):
    calculos: list[bool] = []
    monkeypatch.setattr(
        kpis_mod, "calcular_kpis_actuales", lambda: calculos.append(True) or {}
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


def test_tarea_global_de_kpis_publica_cuando_hay_suscriptores(monkeypatch):
    monkeypatch.setattr(kpis_mod, "calcular_kpis_actuales", lambda: {"alertas_activas": 1})

    async def escenario():
        bus = EventBus()
        monkeypatch.setattr(kpis_mod, "bus", bus)
        cola = bus.suscribir()
        tarea = asyncio.create_task(kpis_mod.publicar_kpis_periodicos(0.01))
        try:
            return await asyncio.wait_for(cola.get(), timeout=1)
        finally:
            tarea.cancel()
            with suppress(asyncio.CancelledError):
                await tarea
            bus.desuscribir(cola)

    assert asyncio.run(escenario()) == ("kpis", {"alertas_activas": 1})
