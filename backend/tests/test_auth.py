"""Pruebas del login JWT, las dependencias de usuario/rol y el stream autenticado."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings, limpiar_cache_settings
from app.core.auth import crear_token, decodificar_token, get_current_user
from app.core.security import hash_password
from app.db.models import Alerta, IpBloqueada, LogAcceso, Usuario
from app.db.session import get_db
from app.main import create_app
from app.middleware import acceso
from app.routers import stream as stream_mod

KPIS = {
    "pct_tiempo_en_rango_24h": 100.0,
    "alertas_activas": 1,
    "tiempo_respuesta_promedio_min": 0.0,
    "valor_en_riesgo_mxn": 0.0,
    "merma_hoy_mxn": 0.0,
    "merma_mes_mxn": 0.0,
}


@pytest.fixture(autouse=True)
def _sin_cache_settings():
    """Aísla cada prueba de la configuración cacheada."""
    limpiar_cache_settings()
    yield
    limpiar_cache_settings()


def _activar_auth(monkeypatch, activa: bool = True) -> None:
    monkeypatch.setenv("AUTH_REQUERIDA", "1" if activa else "0")
    limpiar_cache_settings()


def _token(
    *,
    sub: str = "jefe",
    rol: str = "jefe_cocina",
    expira: datetime | None = None,
    secreto: str | None = None,
) -> str:
    """Firma un JWT de prueba; por defecto dura 8 h como el de producción."""
    ahora = datetime.now(UTC)
    payload = {
        "sub": sub,
        "rol": rol,
        "iat": ahora,
        "exp": expira or ahora + timedelta(hours=8),
    }
    return jwt.encode(
        payload,
        secreto or get_settings().jwt_secret,
        algorithm="HS256",
    )


def _cabecera(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class ResultadoFalso:
    """Resultado mínimo de SQLAlchemy."""

    def __init__(self, filas: list[object] | None = None) -> None:
        self._filas = list(filas or [])

    def scalars(self) -> ResultadoFalso:
        return self

    def all(self) -> list[object]:
        return list(self._filas)


class SesionFalsa:
    """Sesión en memoria: resuelve el usuario del JWT y vacía las consultas."""

    def __init__(self, usuario: Usuario | None = None, alerta: Alerta | None = None) -> None:
        self.usuario = usuario
        self.alerta = alerta
        self.sentencias: list[object] = []
        self.obtenidos: list[object] = []
        self.commits = 0
        self.busquedas_usuario = 0

    def scalar(self, sentencia: object) -> object | None:
        self.sentencias.append(sentencia)
        if "FROM usuarios" in str(sentencia):
            self.busquedas_usuario += 1
            return self.usuario
        return None

    def scalars(self, sentencia: object) -> ResultadoFalso:
        self.sentencias.append(sentencia)
        return ResultadoFalso()

    def execute(self, sentencia: object) -> ResultadoFalso:
        self.sentencias.append(sentencia)
        return ResultadoFalso()

    def get(self, modelo: object, ident: int) -> object | None:
        self.obtenidos.append((modelo, ident))
        return self.alerta if modelo is Alerta else None

    def commit(self) -> None:
        self.commits += 1


def _cliente(sesion: SesionFalsa) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: sesion
    return TestClient(app)


def _usuario(id: int = 1, nombre: str = "jefe", rol: str = "jefe_cocina") -> Usuario:
    return Usuario(id=id, usuario=nombre, password_hash="hash", rol=rol)


def _alerta() -> Alerta:
    return Alerta(
        id=31,
        camara_id=1,
        tipo="temperatura",
        abierta_en=datetime(2026, 11, 12, 18, 5, tzinfo=UTC),
        cerrada_en=None,
        temperatura_max_c=None,
        atendida_por=None,
        atendida_en=None,
        nota=None,
        sms_enviados=0,
    )


# --- POST /api/auth/login ---------------------------------------------------


def test_login_correcto_entrega_jwt_de_ocho_horas(monkeypatch):
    _activar_auth(monkeypatch)
    sesion = SesionFalsa(
        usuario=Usuario(
            id=1,
            usuario="jefe",
            password_hash=hash_password("secreto"),
            rol="jefe_cocina",
        )
    )

    with _cliente(sesion) as cliente:
        respuesta = cliente.post(
            "/api/auth/login", json={"usuario": "jefe", "password": "secreto"}
        )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["token_type"] == "bearer"
    assert cuerpo["expira_en_segundos"] == 8 * 3600

    payload = decodificar_token(cuerpo["access_token"])
    assert payload["sub"] == "jefe"
    assert payload["rol"] == "jefe_cocina"
    assert payload["exp"] - payload["iat"] == 8 * 3600
    assert sesion.busquedas_usuario == 1


def test_login_sin_auth_requerida_sigue_existiendo(monkeypatch):
    _activar_auth(monkeypatch, activa=False)
    sesion = SesionFalsa(
        usuario=Usuario(
            id=2, usuario="gerente", password_hash=hash_password("secreto"), rol="gerente"
        )
    )

    with _cliente(sesion) as cliente:
        respuesta = cliente.post(
            "/api/auth/login", json={"usuario": "gerente", "password": "secreto"}
        )

    assert respuesta.status_code == 200
    assert decodificar_token(respuesta.json()["access_token"])["rol"] == "gerente"


def test_el_token_del_login_sirve_para_consultar(monkeypatch):
    """Flujo completo: login -> token -> ruta de consulta protegida."""
    _activar_auth(monkeypatch)
    sesion = SesionFalsa(
        usuario=Usuario(
            id=5, usuario="jefe", password_hash=hash_password("secreto"), rol="jefe_cocina"
        )
    )

    with _cliente(sesion) as cliente:
        login = cliente.post(
            "/api/auth/login", json={"usuario": "jefe", "password": "secreto"}
        )
        respuesta = cliente.get(
            "/api/camaras", headers=_cabecera(login.json()["access_token"])
        )

    assert login.status_code == 200
    assert respuesta.status_code == 200
    assert sesion.busquedas_usuario == 2


@pytest.mark.parametrize(
    "usuario_bd",
    [
        None,
        Usuario(id=1, usuario="jefe", password_hash=hash_password("otra"), rol="jefe_cocina"),
    ],
    ids=["usuario-inexistente", "password-incorrecta"],
)
def test_login_incorrecto_regresa_401_generico(usuario_bd):
    sesion = SesionFalsa(usuario=usuario_bd)

    with _cliente(sesion) as cliente:
        respuesta = cliente.post(
            "/api/auth/login", json={"usuario": "jefe", "password": "secreto"}
        )

    assert respuesta.status_code == 401
    assert respuesta.headers["www-authenticate"] == "Bearer"
    assert respuesta.json()["detail"] == "Usuario o contraseña incorrectos."


# --- Validación del JWT -----------------------------------------------------


def test_token_expirado_regresa_401(monkeypatch):
    _activar_auth(monkeypatch)
    token = _token(expira=datetime.now(UTC) - timedelta(seconds=1))

    with pytest.raises(jwt.ExpiredSignatureError):
        decodificar_token(token)

    with _cliente(SesionFalsa(usuario=_usuario())) as cliente:
        respuesta = cliente.get("/api/camaras", headers=_cabecera(token))

    assert respuesta.status_code == 401
    assert respuesta.headers["www-authenticate"] == "Bearer"
    assert "inválido o expirado" in respuesta.json()["detail"]


@pytest.mark.parametrize(
    "token",
    [
        "esto-no-es-un-jwt",
        _token(secreto="otro-secreto"),
        jwt.encode({"sub": "jefe"}, "secreto-de-prueba", algorithm="HS256"),
    ],
    ids=["basura", "firma-ajena", "sin-claims"],
)
def test_jwt_invalido_regresa_401(monkeypatch, token):
    _activar_auth(monkeypatch)

    with _cliente(SesionFalsa(usuario=_usuario())) as cliente:
        respuesta = cliente.get("/api/camaras", headers=_cabecera(token))

    assert respuesta.status_code == 401
    assert respuesta.headers["www-authenticate"] == "Bearer"


def test_token_de_usuario_inexistente_regresa_401(monkeypatch):
    _activar_auth(monkeypatch)
    token = _token(sub="fantasma")

    with _cliente(SesionFalsa(usuario=None)) as cliente:
        respuesta = cliente.get("/api/camaras", headers=_cabecera(token))

    assert respuesta.status_code == 401
    assert respuesta.json()["detail"] == "Token de usuario inválido o expirado."


def test_crear_token_usa_el_secreto_y_la_expiracion_configurados(monkeypatch):
    _activar_auth(monkeypatch)
    monkeypatch.setenv("JWT_EXPIRA_HORAS", "2")
    limpiar_cache_settings()

    payload = decodificar_token(crear_token("jefe", "jefe_cocina"))

    assert payload["sub"] == "jefe"
    assert payload["rol"] == "jefe_cocina"
    assert payload["exp"] - payload["iat"] == 2 * 3600
    assert jwt.decode(
        crear_token("jefe", "jefe_cocina"),
        get_settings().jwt_secret,
        algorithms=["HS256"],
    )["sub"] == "jefe"


# --- Rutas de consulta abiertas / protegidas --------------------------------

RUTAS_CONSULTA = ["/api/camaras", "/api/lotes", "/api/alertas", "/api/seguridad/alertas"]


@pytest.mark.parametrize("ruta", RUTAS_CONSULTA)
def test_auth_desactivada_deja_las_rutas_abiertas(monkeypatch, ruta):
    _activar_auth(monkeypatch, activa=False)

    with _cliente(SesionFalsa()) as cliente:
        respuesta = cliente.get(ruta)

    assert respuesta.status_code == 200


@pytest.mark.parametrize("ruta", RUTAS_CONSULTA)
def test_auth_activa_sin_token_regresa_401(monkeypatch, ruta):
    _activar_auth(monkeypatch)

    with _cliente(SesionFalsa()) as cliente:
        respuesta = cliente.get(ruta)

    assert respuesta.status_code == 401
    assert respuesta.headers["www-authenticate"] == "Bearer"
    assert "Bearer" in respuesta.json()["detail"]


@pytest.mark.parametrize("ruta", RUTAS_CONSULTA)
@pytest.mark.parametrize("rol", ["jefe_cocina", "gerente"])
def test_auth_activa_con_token_permite_leer(monkeypatch, ruta, rol):
    _activar_auth(monkeypatch)
    usuario = _usuario(nombre=f"usuario-{rol}", rol=rol)

    with _cliente(SesionFalsa(usuario=usuario)) as cliente:
        respuesta = cliente.get(ruta, headers=_cabecera(_token(sub=usuario.usuario, rol=rol)))

    assert respuesta.status_code == 200


# --- POST /api/alertas/{id}/atender ----------------------------------------


def test_atender_con_jwt_usa_el_usuario_autenticado(monkeypatch):
    _activar_auth(monkeypatch)
    alerta = _alerta()
    # El usuario del token NO es el primer jefe del seed: si la ruta usara el
    # respaldo, `atendida_por` sería 1 en vez de 42.
    usuario = _usuario(id=42, nombre="jefe-turno", rol="jefe_cocina")
    sesion = SesionFalsa(usuario=usuario, alerta=alerta)

    with _cliente(sesion) as cliente:
        respuesta = cliente.post(
            "/api/alertas/31/atender",
            json={"nota": "Se cerró la puerta"},
            headers=_cabecera(_token(sub="jefe-turno")),
        )

    assert respuesta.status_code == 200
    assert alerta.atendida_por == 42
    assert respuesta.json()["atendida_por"] == 42
    # Solo la búsqueda del usuario del JWT: no se buscó al "primer jefe".
    assert sesion.busquedas_usuario == 1
    assert sesion.commits == 1


def test_atender_con_rol_gerente_regresa_403(monkeypatch):
    _activar_auth(monkeypatch)
    sesion = SesionFalsa(usuario=_usuario(id=2, nombre="gerente", rol="gerente"), alerta=_alerta())

    with _cliente(sesion) as cliente:
        respuesta = cliente.post(
            "/api/alertas/31/atender",
            json={},
            headers=_cabecera(_token(sub="gerente", rol="gerente")),
        )

    assert respuesta.status_code == 403
    assert "jefe_cocina" in respuesta.json()["detail"]
    # El rol se rechaza antes de tocar la alerta.
    assert sesion.obtenidos == []
    assert sesion.commits == 0


def test_atender_sin_auth_sigue_usando_al_primer_jefe(monkeypatch):
    _activar_auth(monkeypatch, activa=False)
    alerta = _alerta()
    sesion = SesionFalsa(usuario=_usuario(id=1), alerta=alerta)

    with _cliente(sesion) as cliente:
        respuesta = cliente.post("/api/alertas/31/atender", json={})

    assert respuesta.status_code == 200
    assert alerta.atendida_por == 1
    assert sesion.busquedas_usuario == 1


# --- GET /api/stream?token=<jwt> -------------------------------------------


@pytest.fixture
def _stream_aislado(monkeypatch):
    """Evita Postgres y que el cupo de conexiones se arrastre entre pruebas."""
    monkeypatch.setattr(stream_mod, "calcular_kpis_actuales", lambda: KPIS)
    monkeypatch.setattr(
        stream_mod,
        "limite_conexiones",
        stream_mod.LimiteConexiones(stream_mod.MAX_CONEXIONES_STREAM),
    )


@pytest.mark.parametrize("params", [{}, {"token": "no-es-un-jwt"}], ids=["sin-token", "invalido"])
def test_stream_con_auth_activa_rechaza_token_ausente_o_invalido(
    monkeypatch, _stream_aislado, params
):
    _activar_auth(monkeypatch)

    with _cliente(SesionFalsa(usuario=_usuario())) as cliente:
        respuesta = cliente.get("/api/stream", params=params)

    assert respuesta.status_code == 401
    assert respuesta.headers["www-authenticate"] == "Bearer"


def test_stream_con_auth_activa_acepta_token_valido(monkeypatch, _stream_aislado):
    _activar_auth(monkeypatch)
    sesion = SesionFalsa(usuario=_usuario())

    with _cliente(sesion) as cliente:
        with cliente.stream("GET", "/api/stream", params={"token": _token()}) as respuesta:
            assert respuesta.status_code == 200
            assert respuesta.headers["content-type"].startswith("text/event-stream")
            trozos = respuesta.iter_text()
            primera = next(trozos)
            segunda = next(trozos)

    assert "retry: 3000" in primera
    assert segunda.startswith("event: kpis")
    assert sesion.busquedas_usuario == 1


# --- Logs de acceso ---------------------------------------------------------


class SesionDeLogs:
    """Sesión mínima del middleware: registra filas sin tocar Supabase."""

    def __init__(self) -> None:
        self.insertados: list[LogAcceso] = []
        self.commits = 0

    def get(self, modelo: object, ident: object) -> IpBloqueada | None:
        return None

    def add(self, fila: LogAcceso) -> None:
        self.insertados.append(fila)

    def commit(self) -> None:
        self.commits += 1

    def close(self) -> None:
        pass


def test_peticion_autenticada_registra_credencial_usuario_y_sujeto(
    monkeypatch, log_stdout
):
    _activar_auth(monkeypatch)
    monkeypatch.setenv("MIDDLEWARE_ACCESO_DB", "1")
    limpiar_cache_settings()

    sesion_logs = SesionDeLogs()
    monkeypatch.setattr(acceso, "SessionLocal", lambda bind=None: sesion_logs)
    monkeypatch.setattr(acceso, "get_engine", lambda: None)

    with _cliente(SesionFalsa(usuario=_usuario(nombre="jefe"))) as cliente:
        respuesta = cliente.get("/api/alertas", headers=_cabecera(_token(sub="jefe")))
        cliente.portal.call(acceso.esperar_registros)

    assert respuesta.status_code == 200
    assert len(sesion_logs.insertados) == 1
    fila = sesion_logs.insertados[0]
    assert fila.ruta == "/api/alertas"
    assert fila.status == 200
    assert fila.credencial == "usuario"
    assert fila.sujeto == "jefe"

    salida = json.loads(log_stdout.getvalue().splitlines()[-1])
    assert salida["credencial"] == "usuario"
    assert salida["sujeto"] == "jefe"


def test_get_current_user_anota_credencial_y_sujeto(monkeypatch):
    """La dependencia deja el usuario en `request.state` para el middleware."""
    _activar_auth(monkeypatch)
    request = SimpleNamespace(state=SimpleNamespace())
    sesion = SesionFalsa(usuario=_usuario(nombre="jefe"))

    usuario = get_current_user(
        request, sesion, authorization=f"Bearer {_token(sub='jefe')}"
    )

    assert usuario is not None
    assert usuario.usuario == "jefe"
    assert request.state.credencial == "usuario"
    assert request.state.sujeto == "jefe"
    assert sesion.busquedas_usuario == 1
