"""Pruebas del bus en memoria que alimenta el stream SSE."""

import asyncio
import threading

from app.realtime.bus import TAMANO_COLA, EventBus


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


def test_desuscribir_deja_de_entregar_eventos():
    bus = EventBus()

    async def escenario():
        cola = bus.suscribir()
        bus.desuscribir(cola)
        bus.publicar("lectura", {"camara_id": 1})
        await asyncio.sleep(0)
        return cola.empty()

    assert asyncio.run(escenario()) is True


def test_cola_llena_descarta_el_evento_sin_bloquear():
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
