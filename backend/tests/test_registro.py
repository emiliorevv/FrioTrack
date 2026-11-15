"""Pruebas del sign-up de dueño + restaurante y del rol `dueno`."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.config import limpiar_cache_settings
from app.core.auth import crear_token, decodificar_token, sesion_si_auth
from app.core.security import hash_password, verify_password
from app.db.models import Alerta, Camara, Restaurante, Usuario
from app.db.session import get_db
from app.main import create_app
from app.routers import auth as auth_mod

DATOS = {
    "restaurante": "Taquería Norte",
    "usuario": "dueno@norte.mx",
    "password": "secreto123",
}


@pytest.fixture(autouse=True)
def _sin_cache_settings():
    """Aísla cada prueba de la configuración cacheada."""
    limpiar_cache_settings()
    yield
    limpiar_cache_settings()


@pytest.fixture(autouse=True)
def _limitadores_limpios():
    """Login y registro son globales; cada prueba empieza con la ventana vacía."""
    auth_mod.limitador_login.reiniciar()
    auth_mod.limitador_registro.reiniciar()
    yield
    auth_mod.limitador_login.reiniciar()
    auth_mod.limitador_registro.reiniciar()


def _activar_auth(monkeypatch, activa: bool = True) -> None:
    monkeypatch.setenv("AUTH_REQUERIDA", "1" if activa else "0")
    limpiar_cache_settings()


class ResultadoFalso:
    """Resultado mínimo de SQLAlchemy."""

    def __init__(self, filas: list[object] | None = None) -> None:
        self._filas = list(filas or [])

    def scalars(self) -> ResultadoFalso:
        return self

    def all(self) -> list[object]:
        return list(self._filas)

    def one(self) -> object:
        return self._filas[0]


class SesionRegistroFalsa:
    """Sesión en memoria para registro, login y consultas vacías.

    Guarda las filas agregadas, asigna ids en `flush`/`refresh` y resuelve
    `buscar_usuario` con `existente` o con el usuario dado de alta en la misma
    prueba. No toca SQLite ni ninguna base real.
    """

    def __init__(
        self,
        existente: Usuario | None = None,
        error_commit: Exception | None = None,
    ) -> None:
        self.existente = existente
        self.error_commit = error_commit
        self.agregados: list[object] = []
        self.restaurantes: list[Restaurante] = []
        self.usuarios: list[Usuario] = []
        self.sentencias: list[object] = []
        self.obtenidos: list[tuple[object, int]] = []
        self.flushes = 0
        self.commits = 0
        self.rollbacks = 0
        self.refreshes: list[object] = []
        self.siguiente_id = 2  # el restaurante demo ya ocupa el 1

    def _nuevo_id(self) -> int:
        ident = self.siguiente_id
        self.siguiente_id += 1
        return ident

    def scalar(self, sentencia: object) -> object | None:
        self.sentencias.append(sentencia)
        if self.existente is not None:
            return self.existente
        if "FROM usuarios" in str(sentencia):
            return self.usuarios[0] if self.usuarios else None
        return None

    def scalars(self, sentencia: object) -> ResultadoFalso:
        self.sentencias.append(sentencia)
        return ResultadoFalso()

    def execute(self, sentencia: object) -> ResultadoFalso:
        self.sentencias.append(sentencia)
        return ResultadoFalso()

    def add(self, fila: object) -> None:
        self.agregados.append(fila)
        if isinstance(fila, Restaurante):
            self.restaurantes.append(fila)
        elif isinstance(fila, Usuario):
            self.usuarios.append(fila)

    def flush(self) -> None:
        self.flushes += 1
        for fila in self.agregados:
            if isinstance(fila, Restaurante) and fila.id is None:
                fila.id = self._nuevo_id()

    def commit(self) -> None:
        if self.error_commit is not None:
            raise self.error_commit
        self.commits += 1
        for usuario in self.usuarios:
            if usuario.id is None:
                usuario.id = self._nuevo_id()

    def refresh(self, fila: object) -> None:
        self.refreshes.append(fila)
        if isinstance(fila, Usuario) and fila.id is None:
            fila.id = self._nuevo_id()

    def rollback(self) -> None:
        self.rollbacks += 1

    def get(self, modelo: object, ident: int) -> object | None:
        self.obtenidos.append((modelo, ident))
        if modelo is Usuario:
            for usuario in [*self.usuarios, self.existente]:
                if usuario is not None and usuario.id == ident:
                    return usuario
        return None


class SesionAtenderFalsa:
    """Sesión mínima para `POST /alertas/{id}/atender` con JWT."""

    def __init__(self, usuarios: list[Usuario], alerta: Alerta, camara: Camara) -> None:
        self.usuarios = usuarios
        self.alerta = alerta
        self.camara = camara
        self.commits = 0

    def get(self, modelo: object, ident: int) -> object | None:
        if modelo is Usuario:
            return next((usuario for usuario in self.usuarios if usuario.id == ident), None)
        if modelo is Camara:
            return self.camara if self.camara.id == ident else None
        if modelo is Alerta:
            return self.alerta if self.alerta.id == ident else None
        return None

    def commit(self) -> None:
        self.commits += 1


def _cliente(sesion: object) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: sesion
    app.dependency_overrides[sesion_si_auth] = lambda: sesion
    return TestClient(app)


def _alerta() -> Alerta:
    return Alerta(
        id=31,
        camara_id=1,
        tipo="temperatura",
        abierta_en=datetime(2026, 11, 14, 18, 5, tzinfo=UTC),
        cerrada_en=None,
        temperatura_max_c=None,
        atendida_por=None,
        atendida_en=None,
        nota=None,
        sms_enviados=0,
    )


def _camara(restaurante_id: int = 2) -> Camara:
    return Camara(
        id=1,
        restaurante_id=restaurante_id,
        nombre="Cámara nueva",
        rango_min_c=0,
        rango_max_c=4,
        min_para_riesgo=10,
        min_para_merma=60,
        estado="en_rango",
    )


# --- POST /api/auth/registro ------------------------------------------------


def test_registro_correcto_crea_restaurante_y_dueno(log_stdout):
    sesion = SesionRegistroFalsa()

    with _cliente(sesion) as cliente:
        respuesta = cliente.post(
            "/api/auth/registro",
            json={
                "restaurante": "  Taquería Norte  ",
                "usuario": "  dueno@norte.mx  ",
                "password": "secreto123",
            },
        )

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    # No se exponen el hash ni datos internos del usuario.
    assert set(cuerpo) == {"access_token", "token_type", "expira_en_segundos"}
    assert cuerpo["token_type"] == "bearer"
    assert cuerpo["expira_en_segundos"] == 8 * 3600

    assert len(sesion.restaurantes) == 1
    restaurante = sesion.restaurantes[0]
    assert restaurante.nombre == "Taquería Norte"
    assert restaurante.id == 2

    assert len(sesion.usuarios) == 1
    usuario = sesion.usuarios[0]
    assert usuario.usuario == "dueno@norte.mx"
    assert usuario.rol == "dueno"
    assert usuario.restaurante_id == restaurante.id
    assert usuario.password_hash != "secreto123"
    assert usuario.password_hash.startswith("pbkdf2_sha256$")
    assert verify_password("secreto123", usuario.password_hash)

    payload = decodificar_token(cuerpo["access_token"])
    assert payload["sub"] == "dueno@norte.mx"
    assert payload["rol"] == "dueno"
    assert payload["restaurante_id"] == 2
    assert payload["uid"] == usuario.id

    assert sesion.commits == 1
    assert sesion.refreshes == [usuario]

    # La credencial y el sujeto llegan al log de acceso del middleware.
    salida = json.loads(log_stdout.getvalue().splitlines()[-1])
    assert salida["credencial"] == "registro"
    assert salida["sujeto"] == "dueno@norte.mx"
    assert salida["status"] == 201


def test_registro_duplicado_regresa_409_sin_crear_restaurante():
    existente = Usuario(
        id=1,
        restaurante_id=1,
        usuario="dueno@norte.mx",
        password_hash=hash_password("otra"),
        rol="dueno",
    )
    sesion = SesionRegistroFalsa(existente=existente)

    with _cliente(sesion) as cliente:
        respuesta = cliente.post("/api/auth/registro", json=DATOS)

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == "Ese usuario ya está registrado."
    assert sesion.restaurantes == []
    assert sesion.agregados == []
    assert sesion.commits == 0


def test_registro_con_carrera_de_unicidad_regresa_409_y_hace_rollback():
    sesion = SesionRegistroFalsa(
        error_commit=IntegrityError("INSERT usuarios", {}, Exception("duplicate key"))
    )

    with _cliente(sesion) as cliente:
        respuesta = cliente.post("/api/auth/registro", json=DATOS)

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == "Ese usuario ya está registrado."
    assert sesion.rollbacks == 1
    assert sesion.commits == 0
    assert sesion.refreshes == []


@pytest.mark.parametrize(
    "cambios",
    [
        {"password": "corta"},
        {"usuario": "   "},
        {"restaurante": "  "},
        {"usuario": " ab "},
        {"restaurante": " a "},
    ],
    ids=["password-corta", "usuario-solo-espacios", "restaurante-solo-espacios",
         "usuario-corto-tras-recortar", "restaurante-corto-tras-recortar"],
)
def test_registro_con_datos_invalidos_regresa_422(cambios):
    sesion = SesionRegistroFalsa()

    with _cliente(sesion) as cliente:
        respuesta = cliente.post("/api/auth/registro", json={**DATOS, **cambios})

    assert respuesta.status_code == 422
    assert sesion.agregados == []
    assert sesion.sentencias == []


def test_registro_funciona_con_auth_requerida_encendida_y_apagada(monkeypatch):
    for activa in (False, True):
        _activar_auth(monkeypatch, activa=activa)
        sesion = SesionRegistroFalsa()

        with _cliente(sesion) as cliente:
            respuesta = cliente.post("/api/auth/registro", json=DATOS)

        assert respuesta.status_code == 201
        assert decodificar_token(respuesta.json()["access_token"])["rol"] == "dueno"


def test_registro_rate_limit_tras_cinco_intentos_regresa_429():
    existente = Usuario(
        id=1,
        restaurante_id=1,
        usuario="dueno@norte.mx",
        password_hash=hash_password("otra"),
        rol="dueno",
    )
    sesion = SesionRegistroFalsa(existente=existente)

    with _cliente(sesion) as cliente:
        respuestas = [cliente.post("/api/auth/registro", json=DATOS) for _ in range(5)]
        sexta = cliente.post("/api/auth/registro", json=DATOS)

    assert [respuesta.status_code for respuesta in respuestas] == [409] * 5
    assert sexta.status_code == 429
    assert 1 <= int(sexta.headers["retry-after"]) <= 3600
    assert "Demasiados registros" in sexta.json()["detail"]
    # El sexto ni siquiera consulta si el usuario existe.
    assert len(sesion.sentencias) == 5
    assert sesion.agregados == []


def test_flujo_registro_token_camaras_vacias_y_login():
    """Registro -> JWT -> /camaras del tenant nuevo -> login con esas credenciales."""
    sesion = SesionRegistroFalsa()

    with _cliente(sesion) as cliente:
        registro = cliente.post("/api/auth/registro", json=DATOS)
        token = registro.json()["access_token"]
        camaras = cliente.get("/api/camaras", headers={"Authorization": f"Bearer {token}"})
        login = cliente.post(
            "/api/auth/login",
            json={"usuario": DATOS["usuario"], "password": DATOS["password"]},
        )

    assert registro.status_code == 201
    # El restaurante nace sin cámaras: el dueño entra a un dashboard vacío.
    assert camaras.status_code == 200
    assert camaras.json() == []
    assert login.status_code == 200
    assert decodificar_token(login.json()["access_token"])["restaurante_id"] == 2


# --- Rol `dueno` al atender alertas ----------------------------------------


def _dueno(rol: str = "dueno") -> Usuario:
    return Usuario(
        id=42,
        restaurante_id=2,
        usuario=f"usuario-{rol}",
        password_hash=hash_password("secreto123"),
        rol=rol,
    )


def test_dueno_puede_atender_una_alerta(monkeypatch):
    _activar_auth(monkeypatch)
    dueno = _dueno()
    alerta = _alerta()
    sesion = SesionAtenderFalsa(usuarios=[dueno], alerta=alerta, camara=_camara())

    with _cliente(sesion) as cliente:
        respuesta = cliente.post(
            "/api/alertas/31/atender",
            json={"nota": "Revisado por el dueño"},
            headers={"Authorization": f"Bearer {crear_token(dueno)}"},
        )

    assert respuesta.status_code == 200
    assert respuesta.json()["atendida_por"] == 42
    assert alerta.atendida_por == 42
    assert alerta.nota == "Revisado por el dueño"
    assert sesion.commits == 1


def test_gerente_sigue_sin_poder_atender(monkeypatch):
    _activar_auth(monkeypatch)
    gerente = _dueno(rol="gerente")
    alerta = _alerta()
    sesion = SesionAtenderFalsa(usuarios=[gerente], alerta=alerta, camara=_camara())

    with _cliente(sesion) as cliente:
        respuesta = cliente.post(
            "/api/alertas/31/atender",
            json={},
            headers={"Authorization": f"Bearer {crear_token(gerente)}"},
        )

    assert respuesta.status_code == 403
    assert "jefe_cocina" in respuesta.json()["detail"]
    assert "dueno" in respuesta.json()["detail"]
    assert alerta.atendida_por is None
    assert sesion.commits == 0
