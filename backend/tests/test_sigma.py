"""La regla SIEM no debe desincronizarse de los endpoints con token."""

from pathlib import Path

RUTA_REGLA = (
    Path(__file__).resolve().parents[2] / "security/siem/fuerza-bruta-tokens.yml"
)


def test_fuerza_bruta_cubre_ingesta_y_cron():
    regla = RUTA_REGLA.read_text(encoding="utf-8")
    deteccion = regla.split("detection:", 1)[1]

    assert "- /api/telemetria" in deteccion
    assert "- /api/simulador/tick" in deteccion
    assert "- 401" in deteccion
    assert "- 403" in deteccion
