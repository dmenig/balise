from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from balise_api.domain.enums import SourceKind, SpotKind
from balise_api.models.base import Base


class Source(Base):
    __tablename__ = "source"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    kind: Mapped[SourceKind]
    licence: Mapped[str] = mapped_column(Text, nullable=False)
    attribution: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    last_sync_at: Mapped[datetime | None]


class Harbour(Base):
    __tablename__ = "harbour"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    insee_code: Mapped[str | None] = mapped_column(Text)
    geom: Mapped[WKBElement] = mapped_column(Geometry("POINT", srid=4326), nullable=False)
    area: Mapped[WKBElement | None] = mapped_column(Geometry("MULTIPOLYGON", srid=4326))
    vhf_channel: Mapped[int | None] = mapped_column(SmallInteger)
    phone: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(Text)
    opening_hours: Mapped[str | None] = mapped_column(Text)
    services: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{}", default=list
    )
    source_id: Mapped[str] = mapped_column(ForeignKey("source.id"), nullable=False)
    external_ids: Mapped[dict[str, Any]] = mapped_column(
        nullable=False, server_default="{}", default=dict
    )
    attrs_provenance: Mapped[dict[str, Any]] = mapped_column(
        nullable=False, server_default="{}", default=dict
    )
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    fields: Mapped[list[Field]] = relationship(back_populates="harbour", cascade="all, delete")

    __table_args__ = (
        Index("ix_harbour_geom", "geom", postgresql_using="gist"),
        Index(
            "ix_harbour_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )


class Field(Base):
    """A homogeneous group of spots under one operator (a `panne`, a ZMEL, a visitor zone)."""

    __tablename__ = "field"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    harbour_id: Mapped[int | None] = mapped_column(
        ForeignKey("harbour.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[SpotKind]
    area: Mapped[WKBElement | None] = mapped_column(Geometry("MULTIPOLYGON", srid=4326))
    capacity: Mapped[int | None]
    visitor_capacity: Mapped[int | None]
    operator: Mapped[str | None] = mapped_column(Text)
    price_per_night_cents: Mapped[int | None]
    price_note: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[str] = mapped_column(ForeignKey("source.id"), nullable=False)
    external_ids: Mapped[dict[str, Any]] = mapped_column(
        nullable=False, server_default="{}", default=dict
    )
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    harbour: Mapped[Harbour | None] = relationship(back_populates="fields")
    spots: Mapped[list[Spot]] = relationship(back_populates="field")

    __table_args__ = (Index("ix_field_area", "area", postgresql_using="gist"),)


class Spot(Base):
    """The occupiable unit — this is what carries availability. Never merged with `nav_aid`."""

    __tablename__ = "spot"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    field_id: Mapped[int | None] = mapped_column(
        ForeignKey("field.id", ondelete="SET NULL"), index=True
    )
    harbour_id: Mapped[int | None] = mapped_column(ForeignKey("harbour.id", ondelete="SET NULL"))
    kind: Mapped[SpotKind]
    code: Mapped[str | None] = mapped_column(Text)
    geom: Mapped[WKBElement] = mapped_column(Geometry("POINT", srid=4326), nullable=False)
    area: Mapped[WKBElement | None] = mapped_column(Geometry("POLYGON", srid=4326))
    depth_m: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    max_loa_m: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    max_beam_m: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    max_draft_m: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    holding: Mapped[str | None] = mapped_column(Text)
    exposure: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{}", default=list
    )
    visitor: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    bookable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    source_id: Mapped[str] = mapped_column(ForeignKey("source.id"), nullable=False)
    external_ids: Mapped[dict[str, Any]] = mapped_column(
        nullable=False, server_default="{}", default=dict
    )
    attrs_provenance: Mapped[dict[str, Any]] = mapped_column(
        nullable=False, server_default="{}", default=dict
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true", default=True
    )
    missing_runs: Mapped[int] = mapped_column(nullable=False, server_default="0", default=0)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    field: Mapped[Field | None] = relationship(back_populates="spots")

    __table_args__ = (
        Index("ix_spot_geom", "geom", postgresql_using="gist"),
        Index("ix_spot_kind_active", "kind", postgresql_where=active),
        Index(
            "ix_spot_external_ids",
            "external_ids",
            postgresql_using="gin",
            postgresql_ops={"external_ids": "jsonb_path_ops"},
        ),
    )


class NavAid(Base):
    """Référentiel de balisage — read-only, authoritative, and it never has a status."""

    __tablename__ = "nav_aid"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    inspire_id: Mapped[str | None] = mapped_column(Text, unique=True)
    s57_class: Mapped[str] = mapped_column(String(16), nullable=False)
    geom: Mapped[WKBElement] = mapped_column(Geometry("POINT", srid=4326), nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    colour: Mapped[str | None] = mapped_column(Text)
    colour_pattern: Mapped[str | None] = mapped_column(Text)
    shape: Mapped[str | None] = mapped_column(Text)
    topmark: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    light: Mapped[dict[str, Any] | None] = mapped_column()
    height_m: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    source_id: Mapped[str] = mapped_column(ForeignKey("source.id"), nullable=False)
    raw: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true", default=True
    )
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_nav_aid_geom", "geom", postgresql_using="gist"),
        Index("ix_nav_aid_class", "s57_class"),
    )


class ConflationLog(Base):
    """Why did my buoy move — one row per merge decision (docs/10)."""

    __tablename__ = "conflation_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    target_table: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    left_source_id: Mapped[str] = mapped_column(Text, nullable=False)
    left_external_id: Mapped[str] = mapped_column(Text, nullable=False)
    right_source_id: Mapped[str | None] = mapped_column(Text)
    right_external_id: Mapped[str | None] = mapped_column(Text)
    distance_m: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    rule: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
