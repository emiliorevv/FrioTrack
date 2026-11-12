"""Modelos SQLAlchemy 2.0 de las tablas descritas en docs/modelo-datos.md."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    desc,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow

# En SQLite una PK BIGINT no autoincrementa; la variante conserva bigint en Postgres.
IdGrande = BigInteger().with_variant(Integer, "sqlite")


class Camara(Base):
    """Equipo de frío monitoreado y su configuración de tiempos."""

    __tablename__ = "camaras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(Text)
    rango_min_c: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    rango_max_c: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    min_para_riesgo: Mapped[int] = mapped_column(Integer)
    min_para_merma: Mapped[int] = mapped_column(Integer)
    estado: Mapped[str] = mapped_column(Text, default="en_rango")
    fuera_de_rango_desde: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    puerta_abierta_desde: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Sin ForeignKey a propósito: camaras -> lecturas y lecturas -> camaras forman un ciclo,
    # y SQLAlchemy no puede ordenar el alta de ambas tablas. La integridad la cuida la API.
    ultima_lectura_id: Mapped[int | None] = mapped_column(Integer)

    sensores: Mapped[list[Sensor]] = relationship(back_populates="camara")
    lotes: Mapped[list[Lote]] = relationship(back_populates="camara")
    lecturas: Mapped[list[Lectura]] = relationship(back_populates="camara")
    alertas: Mapped[list[Alerta]] = relationship(back_populates="camara")


class Sensor(Base):
    """Sensor (o gateway) autorizado a escribir telemetría de una cámara."""

    __tablename__ = "sensores"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    camara_id: Mapped[int] = mapped_column(ForeignKey("camaras.id"))
    token_hash: Mapped[str] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    camara: Mapped[Camara] = relationship(back_populates="sensores")


class Lectura(Base):
    """Una medición de temperatura, humedad y puerta."""

    __tablename__ = "lecturas"
    __table_args__ = (
        Index("ix_lecturas_camara_id_recibida_en", "camara_id", desc("recibida_en")),
    )

    id: Mapped[int] = mapped_column(IdGrande, primary_key=True)
    camara_id: Mapped[int] = mapped_column(ForeignKey("camaras.id"))
    # Sin ForeignKey a propósito: /simulador/tick manda "SIM-CRON", que no es una fila
    # de sensores; la API valida los demás sensor_id contra la tabla.
    sensor_id: Mapped[str] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recibida_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    temperatura_c: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    humedad_pct: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    puerta_abierta: Mapped[bool] = mapped_column(Boolean, default=False)
    sospechosa: Mapped[bool] = mapped_column(Boolean, default=False)

    camara: Mapped[Camara] = relationship(back_populates="lecturas")


class Lote(Base):
    """Inventario del restaurante asignado a una cámara."""

    __tablename__ = "lotes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    producto: Mapped[str] = mapped_column(Text)
    camara_id: Mapped[int] = mapped_column(ForeignKey("camaras.id"))
    cantidad: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    unidad: Mapped[str] = mapped_column(Text)
    costo_total_mxn: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    caducidad: Mapped[date] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(Text, default="ok")
    merma_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    camara: Mapped[Camara] = relationship(back_populates="lotes")


class Alerta(Base):
    """Alerta operativa abierta por temperatura o por puerta."""

    __tablename__ = "alertas"
    __table_args__ = (
        # Una sola alerta abierta por cámara y tipo; las cerradas no participan.
        Index(
            "uq_alertas_abierta_camara_tipo",
            "camara_id",
            "tipo",
            unique=True,
            sqlite_where=text("cerrada_en IS NULL"),
            postgresql_where=text("cerrada_en IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    camara_id: Mapped[int] = mapped_column(ForeignKey("camaras.id"))
    tipo: Mapped[str] = mapped_column(Text)
    abierta_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    cerrada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    temperatura_max_c: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    atendida_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    atendida_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    nota: Mapped[str | None] = mapped_column(Text)
    sms_enviados: Mapped[int] = mapped_column(Integer, default=1)

    camara: Mapped[Camara] = relationship(back_populates="alertas")
    atendida_por_usuario: Mapped[Usuario | None] = relationship(foreign_keys=[atendida_por])


class Usuario(Base):
    """Usuario del dashboard."""

    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario: Mapped[str] = mapped_column(Text, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    rol: Mapped[str] = mapped_column(Text)
    telefono: Mapped[str | None] = mapped_column(Text)


class LogAcceso(Base):
    """Una fila por petición HTTP, en el formato que consume el SIEM."""

    __tablename__ = "logs_acceso"
    __table_args__ = (
        Index("ix_logs_acceso_ruta_status_ts", "ruta", "status", desc("ts")),
        Index("ix_logs_acceso_ip_origen_ts", "ip_origen", desc("ts")),
    )

    id: Mapped[int] = mapped_column(IdGrande, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ip_origen: Mapped[str] = mapped_column(Text)
    metodo: Mapped[str] = mapped_column(Text)
    ruta: Mapped[str] = mapped_column(Text)
    status: Mapped[int] = mapped_column(Integer)
    credencial: Mapped[str] = mapped_column(Text)
    sujeto: Mapped[str | None] = mapped_column(Text)
    user_agent: Mapped[str] = mapped_column(Text)
    latencia_ms: Mapped[int] = mapped_column(Integer)


class AlertaSeguridad(Base):
    """Hallazgo del detector SIEM."""

    __tablename__ = "alertas_seguridad"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    regla_id: Mapped[str] = mapped_column(Text)
    regla: Mapped[str] = mapped_column(Text)
    severidad: Mapped[str] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ip_origen: Mapped[str | None] = mapped_column(Text)
    detalle: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    accion: Mapped[str] = mapped_column(Text)


class IpBloqueada(Base):
    """IP bloqueada temporalmente por el detector SIEM."""

    __tablename__ = "ips_bloqueadas"

    ip: Mapped[str] = mapped_column(Text, primary_key=True)
    hasta: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    motivo: Mapped[str] = mapped_column(Text)
