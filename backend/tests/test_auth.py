"""Pruebas del login JWT, las dependencias de usuario/rol y el stream autenticado."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings, limpiar_cache_settings
from app.core import auth as auth_core
from app.core.auth import (
    crear_token,
    decodificar_token,
    get_current_user,
    get_restaurante_id,
    huella_password,
    sesion_si_auth,
    token_bearer,
)
from app.core.rate_limit import LimitadorIntentos
from app.core.security import hash_password, verify_password
from app.db.models import RESTAURANTE_DEMO_ID, Alerta, Camara, IpBloqueada, LogAcceso, Usuario
from app.db.session import get_db
from app.main import create_app
from app.middleware import acceso
from app.routers import auth as auth_mod
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


@pytest.fixture(autouse=True)
def _limitador_limpio():
    """Los limitadores son globales; cada prueba empieza con la ventana vacía."""
    auth_mod.limitador_login.reiniciar()
    auth_mod.limitador_registro.reiniciar()
    yield
    auth_mod.limitador_login.reiniciar()
    auth_mod.limitador_registro.reiniciar()


def _activar_auth(monkeypatch, activa: bool = True) -> None:
    monkeypatch.setenv("AUTH_REQUERIDA", "1" if activa else "0")
    limpiar_cache_settings()


def _token(
    usuario: Usuario | None = None,
    *,
    expira: datetime | None = None,
    secreto: str | None = None,
    restaurante_id: int | None = None,
) -> str:
    """Firma un JWT de prueba; por defecto dura 8 h como el de producción."""
    usuario = usuario or _usuario()
    ahora = datetime.now(UTC)
    payload = {
        "sub": usuario.usuario,
        "uid": usuario.id,
        "rol": usuario.rol,
        "pwd": huella_password(usuario.password_hash),
        "restaurante_id": (
            usuario.restaurante_id if restaurante_id is None else restaurante_id
        ),
        "iat": ahora,
        "exp": expira or ahora + timedelta(hours=8),
    }
    return jwt.encode(
        payload,
        secreto or get_settings().jwt_secret,
        algorithm="HS256",
    )


def _cabecera(token: str, esquema: str = "Bearer") -> dict[str, str]:
    return {"Authorization": f"{esquema} {token}"}


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
        self.obtenidos: list[tuple[object, int]] = []
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
        if modelo is Usuario:
            return self.usuario if self.usuario is not None and self.usuario.id == ident else None
        if modelo is Camara:
            return Camara(id=ident, restaurante_id=1, nombre="Cámara de prueba")
        return self.alerta if modelo is Alerta else None

    def commit(self) -> None:
        self.commits += 1


def _cliente(sesion: SesionFalsa) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: sesion
    app.dependency_overrides[sesion_si_auth] = lambda: sesion
    return TestClient(app)


class SesionCortaFalsa:
    """Context manager que comprueba que el stream cierre su sesión al validar."""

    def __init__(self, sesion: SesionFalsa) -> None:
        self.sesion = sesion
        self.cerrada = False

    def __enter__(self) -> SesionFalsa:
        return self.sesion

    def __exit__(self, *_excepcion: object) -> None:
        self.cerrada = True


def _parchear_sesion_corta(monkeypatch, sesion: SesionFalsa) -> SesionCortaFalsa:
    contexto = SesionCortaFalsa(sesion)
    monkeypatch.setattr(auth_core, "SessionLocal", lambda bind=None: contexto)
    monkeypatch.setattr(auth_core, "get_engine", lambda: None)
    return contexto


def _usuario(
    id: int = 1,
    nombre: str = "jefe",
    rol: str = "jefe_cocina",
    restaurante_id: int = 1,
) -> Usuario:
    return Usuario(
        id=id,
        restaurante_id=restaurante_id,
        usuario=nombre,
        password_hash="hash",
        rol=rol,
    )


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
    usuario = Usuario(
        id=1,
        restaurante_id=1,
        usuario="jefe",
        password_hash=hash_password("secreto"),
        rol="jefe_cocina",
    )

    with _cliente(SesionFalsa(usuario=usuario)) as cliente:
        respuesta = cliente.post(
            "/api/auth/login", json={"usuario": "jefe", "password": "secreto"}
        )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["token_type"] == "bearer"
    assert cuerpo["expira_en_segundos"] == 8 * 3600

    payload = decodificar_token(cuerpo["access_token"])
    assert payload["sub"] == "jefe"
    assert payload["uid"] == 1
    assert payload["rol"] == "jefe_cocina"
    assert payload["pwd"] == huella_password(usuario.password_hash)
    assert payload["restaurante_id"] == 1
    assert payload["es_demo"] is True
    assert payload["exp"] - payload["iat"] == 8 * 3600


def test_login_sin_auth_requerida_sigue_existiendo(monkeypatch):
    _activar_auth(monkeypatch, activa=False)
    usuario = Usuario(
        id=2,
        restaurante_id=1,
        usuario="gerente",
        password_hash=hash_password("secreto"),
        rol="gerente",
    )

    with _cliente(SesionFalsa(usuario=usuario)) as cliente:
        respuesta = cliente.post(
            "/api/auth/login", json={"usuario": "gerente", "password": "secreto"}
        )

    assert respuesta.status_code == 200
    assert decodificar_token(respuesta.json()["access_token"])["rol"] == "gerente"


def test_el_token_del_login_sirve_para_consultar(monkeypatch):
    """Flujo completo: login -> token -> ruta de consulta protegida."""
    _activar_auth(monkeypatch)
    usuario = Usuario(
        id=5,
        restaurante_id=3,
        usuario="jefe",
        password_hash=hash_password("secreto"),
        rol="jefe_cocina",
    )

    with _cliente(SesionFalsa(usuario=usuario)) as cliente:
        login = cliente.post(
            "/api/auth/login", json={"usuario": "jefe", "password": "secreto"}
        )
        respuesta = cliente.get(
            "/api/camaras", headers=_cabecera(login.json()["access_token"])
        )

    assert login.status_code == 200
    assert respuesta.status_code == 200


@pytest.mark.parametrize(
    "usuario_bd",
    [
        None,
        Usuario(
            id=1,
            restaurante_id=1,
            usuario="jefe",
            password_hash=hash_password("otra"),
            rol="jefe_cocina",
        ),
    ],
    ids=["usuario-inexistente", "password-incorrecta"],
)
def test_login_incorrecto_regresa_401_generico(usuario_bd):
    with _cliente(SesionFalsa(usuario=usuario_bd)) as cliente:
        respuesta = cliente.post(
            "/api/auth/login", json={"usuario": "jefe", "password": "secreto"}
        )

    assert respuesta.status_code == 401
    assert respuesta.headers["www-authenticate"] == "Bearer"
    assert respuesta.json()["detail"] == "Usuario o contraseña incorrectos."


def test_hash_dummy_precomputado_verifica_la_contrasena_dummy():
    assert verify_password("friotrack-dummy-sin-usuario", auth_mod.HASH_SIN_USUARIO)


def test_login_rechaza_usuario_gigante_sin_escribirlo_en_logs(log_stdout):
    gigante = "x" * 65

    with _cliente(SesionFalsa()) as cliente:
        respuesta = cliente.post(
            "/api/auth/login", json={"usuario": gigante, "password": "secreto"}
        )

    assert respuesta.status_code == 422
    salida = json.loads(log_stdout.getvalue().splitlines()[-1])
    assert salida["credencial"] == "ninguna"
    assert salida["sujeto"] is None
    assert gigante not in log_stdout.getvalue()


def test_login_rechaza_password_demasiado_largo():
    with _cliente(SesionFalsa()) as cliente:
        respuesta = cliente.post(
            "/api/auth/login", json={"usuario": "jefe", "password": "x" * 129}
        )

    assert respuesta.status_code == 422


# --- Rate limit del login ---------------------------------------------------


def test_limitador_bloquea_y_calcula_retry_after():
    ahora = [0.0]
    limitador = LimitadorIntentos(maximo=2, ventana_seg=300, reloj=lambda: ahora[0])

    assert limitador.permitir("ip") == 0
    assert limitador.permitir("ip") == 0
    assert limitador.permitir("ip") == 300

    ahora[0] = 299
    assert limitador.permitir("ip") == 1
    ahora[0] = 300
    assert limitador.permitir("ip") == 0


def test_limitador_purga_las_claves_vencidas():
    ahora = [0.0]
    limitador = LimitadorIntentos(maximo=2, ventana_seg=300, reloj=lambda: ahora[0])

    limitador.permitir("a")
    ahora[0] = 301
    limitador.permitir("b")

    assert "a" not in limitador._intentos
    assert "b" in limitador._intentos


def test_limitador_limpiar_olvida_una_clave():
    limitador = LimitadorIntentos(maximo=1, ventana_seg=300, reloj=lambda: 0.0)

    assert limitador.permitir("ip") == 0
    assert limitador.permitir("ip") == 300
    limitador.limpiar("ip")
    assert limitador.permitir("ip") == 0


def test_login_rate_limit_regresa_429_con_retry_after(monkeypatch):
    limitador = LimitadorIntentos(maximo=1, ventana_seg=300, reloj=lambda: 0.0)
    monkeypatch.setattr(auth_mod, "limitador_login", limitador)

    with _cliente(SesionFalsa(usuario=None)) as cliente:
        primera = cliente.post(
            "/api/auth/login", json={"usuario": "jefe", "password": "mala"}
        )
        segunda = cliente.post(
            "/api/auth/login", json={"usuario": "jefe", "password": "mala"}
        )

    assert primera.status_code == 401
    assert segunda.status_code == 429
    assert segunda.headers["retry-after"] == "300"
    assert "Demasiados intentos" in segunda.json()["detail"]


def test_login_exitoso_limpia_el_limite(monkeypatch):
    usuario = Usuario(
        id=1,
        restaurante_id=1,
        usuario="jefe",
        password_hash=hash_password("secreto"),
        rol="jefe_cocina",
    )
    limitador = LimitadorIntentos(maximo=2, ventana_seg=300, reloj=lambda: 0.0)
    monkeypatch.setattr(auth_mod, "limitador_login", limitador)

    with _cliente(SesionFalsa(usuario=usuario)) as cliente:
        fallo = cliente.post("/api/auth/login", json={"usuario": "jefe", "password": "mala"})
        bueno = cliente.post(
            "/api/auth/login", json={"usuario": "jefe", "password": "secreto"}
        )
        otro_fallo = cliente.post(
            "/api/auth/login", json={"usuario": "jefe", "password": "mala"}
        )

    assert fallo.status_code == 401
    assert bueno.status_code == 200
    # El login exitoso reinició el contador: el siguiente fallo no es 429.
    assert otro_fallo.status_code == 401


# --- Validación del JWT -----------------------------------------------------


def test_token_expirado_regresa_401(monkeypatch):
    _activar_auth(monkeypatch)
    usuario = _usuario()
    token = _token(usuario, expira=datetime.now(UTC) - timedelta(seconds=1))

    with pytest.raises(jwt.ExpiredSignatureError):
        decodificar_token(token)

    with _cliente(SesionFalsa(usuario=usuario)) as cliente:
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

    with _cliente(SesionFalsa(usuario=None)) as cliente:
        respuesta = cliente.get("/api/camaras", headers=_cabecera(_token()))

    assert respuesta.status_code == 401
    assert respuesta.json()["detail"] == "Token de usuario inválido o expirado."


def test_token_se_invalida_si_cambia_la_contrasena(monkeypatch):
    _activar_auth(monkeypatch)
    usuario = _usuario(id=7, nombre="jefe")
    token = _token(usuario)
    usuario.password_hash = hash_password("nueva")

    with _cliente(SesionFalsa(usuario=usuario)) as cliente:
        respuesta = cliente.get("/api/camaras", headers=_cabecera(token))

    assert respuesta.status_code == 401


def test_token_se_invalida_si_el_usuario_recreado_cambia_de_nombre(monkeypatch):
    _activar_auth(monkeypatch)
    token = _token(_usuario(id=7, nombre="jefe"))
    reemplazo = _usuario(id=7, nombre="otro")

    with _cliente(SesionFalsa(usuario=reemplazo)) as cliente:
        respuesta = cliente.get("/api/camaras", headers=_cabecera(token))

    assert respuesta.status_code == 401


def test_token_sin_claim_de_restaurante_regresa_401(monkeypatch):
    _activar_auth(monkeypatch)
    usuario = _usuario()
    ahora = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": usuario.usuario,
            "uid": usuario.id,
            "rol": usuario.rol,
            "pwd": huella_password(usuario.password_hash),
            "iat": ahora,
            "exp": ahora + timedelta(hours=8),
        },
        get_settings().jwt_secret,
        algorithm="HS256",
    )

    with pytest.raises(jwt.MissingRequiredClaimError):
        decodificar_token(token)

    with _cliente(SesionFalsa(usuario=usuario)) as cliente:
        respuesta = cliente.get("/api/camaras", headers=_cabecera(token))

    assert respuesta.status_code == 401
    assert respuesta.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "restaurante_id",
    [2, 0, -1, True],
    ids=["otro", "cero", "negativo", "bool"],
)
def test_token_con_restaurante_id_invalido_regresa_401(monkeypatch, restaurante_id):
    _activar_auth(monkeypatch)
    usuario = _usuario(restaurante_id=1)
    token = _token(usuario, restaurante_id=restaurante_id)

    with _cliente(SesionFalsa(usuario=usuario)) as cliente:
        respuesta = cliente.get("/api/camaras", headers=_cabecera(token))

    assert respuesta.status_code == 401
    assert respuesta.json()["detail"] == "Token de usuario inválido o expirado."


def test_get_restaurante_id_usa_el_del_usuario(monkeypatch):
    _activar_auth(monkeypatch)

    assert get_restaurante_id(_usuario(restaurante_id=4)) == 4


def test_get_restaurante_id_sin_auth_regresa_el_demo(monkeypatch):
    _activar_auth(monkeypatch, activa=False)

    assert get_restaurante_id(None) == RESTAURANTE_DEMO_ID


def test_crear_token_usa_el_secreto_y_la_expiracion_configurados(monkeypatch):
    _activar_auth(monkeypatch)
    monkeypatch.setenv("JWT_EXPIRA_HORAS", "2")
    limpiar_cache_settings()
    usuario = _usuario()

    payload = decodificar_token(crear_token(usuario))

    assert payload["sub"] == "jefe"
    assert payload["uid"] == usuario.id
    assert payload["rol"] == "jefe_cocina"
    assert payload["pwd"] == huella_password("hash")
    assert payload["exp"] - payload["iat"] == 2 * 3600


def test_crear_token_marca_es_demo_solo_para_el_tenant_demo(monkeypatch):
    _activar_auth(monkeypatch)

    demo = decodificar_token(crear_token(_usuario(restaurante_id=1)))
    ajeno = decodificar_token(crear_token(_usuario(restaurante_id=2)))

    assert demo["es_demo"] is True
    assert ajeno["es_demo"] is False


@pytest.mark.parametrize(
    ("header", "esperado"),
    [
        (None, ""),
        ("Token raro", ""),
        ("Bearer abc", "abc"),
        ("bearer abc", "abc"),
        ("BEARER   abc  ", "abc"),
        ("Bearer", ""),
    ],
)
def test_token_bearer_acepta_cualquier_capitalizacion(header, esperado):
    assert token_bearer(header) == esperado


def test_endpoint_acepta_esquema_bearer_en_minusculas(monkeypatch):
    _activar_auth(monkeypatch)
    usuario = _usuario()

    with _cliente(SesionFalsa(usuario=usuario)) as cliente:
        respuesta = cliente.get(
            "/api/alertas", headers=_cabecera(_token(usuario), esquema="bearer")
        )

    assert respuesta.status_code == 200


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
        respuesta = cliente.get(ruta, headers=_cabecera(_token(usuario)))

    assert respuesta.status_code == 200


def test_sesion_si_auth_no_toca_la_base_con_auth_apagada(monkeypatch):
    _activar_auth(monkeypatch, activa=False)

    def explotar():
        raise AssertionError("con AUTH_REQUERIDA=0 no debe crear el engine")

    monkeypatch.setattr(auth_core, "get_engine", explotar)
    generador = sesion_si_auth()

    assert next(generador) is None
    with pytest.raises(StopIteration):
        next(generador)


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
            headers=_cabecera(_token(usuario)),
        )

    assert respuesta.status_code == 200
    assert alerta.atendida_por == 42
    assert respuesta.json()["atendida_por"] == 42
    # El usuario salió del JWT por id: no se buscó al "primer jefe".
    assert (Usuario, 42) in sesion.obtenidos
    assert sesion.busquedas_usuario == 0
    assert sesion.commits == 1


def test_atender_con_rol_gerente_regresa_403(monkeypatch):
    _activar_auth(monkeypatch)
    usuario = _usuario(id=2, nombre="gerente", rol="gerente")
    sesion = SesionFalsa(usuario=usuario, alerta=_alerta())

    with _cliente(sesion) as cliente:
        respuesta = cliente.post(
            "/api/alertas/31/atender", json={}, headers=_cabecera(_token(usuario))
        )

    assert respuesta.status_code == 403
    assert "jefe_cocina" in respuesta.json()["detail"]
    # El rol se rechaza antes de tocar la alerta.
    assert all(modelo is not Alerta for modelo, _ in sesion.obtenidos)
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
    monkeypatch.setattr(stream_mod, "calcular_kpis_actuales", lambda _rid: KPIS)
    monkeypatch.setattr(
        stream_mod,
        "limite_conexiones",
        stream_mod.LimiteConexiones(stream_mod.MAX_CONEXIONES_STREAM),
    )


def _leer_primeros_eventos(cliente: TestClient, params: dict[str, str]) -> tuple[str, str]:
    with cliente.stream("GET", "/api/stream", params=params) as respuesta:
        assert respuesta.status_code == 200
        assert respuesta.headers["content-type"].startswith("text/event-stream")
        trozos = respuesta.iter_text()
        return next(trozos), next(trozos)


def test_stream_con_auth_apagada_no_toca_la_base(monkeypatch, _stream_aislado):
    _activar_auth(monkeypatch, activa=False)

    def explotar():
        raise AssertionError("con AUTH_REQUERIDA=0 el stream no debe abrir sesión")

    monkeypatch.setattr(auth_core, "get_engine", explotar)

    with TestClient(create_app()) as cliente:
        primera, segunda = _leer_primeros_eventos(cliente, {"token": "jwt-ignorado"})

    assert "retry: 3000" in primera
    assert segunda.startswith("event: kpis")


@pytest.mark.parametrize("params", [{}, {"token": "no-es-un-jwt"}], ids=["sin-token", "invalido"])
def test_stream_con_auth_activa_rechaza_token_ausente_o_invalido(
    monkeypatch, _stream_aislado, params
):
    _activar_auth(monkeypatch)
    _parchear_sesion_corta(monkeypatch, SesionFalsa(usuario=_usuario()))

    with TestClient(create_app()) as cliente:
        respuesta = cliente.get("/api/stream", params=params)

    assert respuesta.status_code == 401
    assert respuesta.headers["www-authenticate"] == "Bearer"


def test_stream_con_auth_activa_cierra_la_sesion_antes_de_emitir(
    monkeypatch, _stream_aislado
):
    _activar_auth(monkeypatch)
    sesion = SesionFalsa(usuario=_usuario())
    contexto = _parchear_sesion_corta(monkeypatch, sesion)

    with TestClient(create_app()) as cliente:
        with cliente.stream("GET", "/api/stream", params={"token": _token()}) as respuesta:
            assert respuesta.status_code == 200
            # La dependencia ya validó y cerró la sesión antes de devolver el SSE.
            assert contexto.cerrada is True
            trozos = respuesta.iter_text()
            primera = next(trozos)
            segunda = next(trozos)

    assert "retry: 3000" in primera
    assert segunda.startswith("event: kpis")
    assert sesion.obtenidos == [(Usuario, 1)]


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
    usuario = _usuario(nombre="jefe")

    sesion_logs = SesionDeLogs()
    monkeypatch.setattr(acceso, "SessionLocal", lambda bind=None: sesion_logs)
    monkeypatch.setattr(acceso, "get_engine", lambda: None)

    with _cliente(SesionFalsa(usuario=usuario)) as cliente:
        respuesta = cliente.get("/api/alertas", headers=_cabecera(_token(usuario)))
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
    usuario = _usuario(nombre="jefe")

    autenticado = get_current_user(
        request,
        SesionFalsa(usuario=usuario),
        authorization=_cabecera(_token(usuario))["Authorization"],
    )

    assert autenticado is not None
    assert autenticado.usuario == "jefe"
    assert request.state.credencial == "usuario"
    assert request.state.sujeto == "jefe"
