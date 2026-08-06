"""Staging tables, physically partitioned by provenance (docs/04 §2).

OSM-derived rows never share a table with our own observations: that separation is what keeps
ODbL share-alike off Layer B.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import BigInteger, Index, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from balise_api.models.base import Base


class _StagedFeature(Base):
    __abstract__ = True

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    layer: Mapped[str] = mapped_column(Text, nullable=False)
    geom: Mapped[WKBElement | None] = mapped_column(Geometry(srid=4326))
    properties: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)
    snapshot_date: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class ShomFeature(_StagedFeature):
    __tablename__ = "shom_feature"
    __table_args__ = (
        UniqueConstraint("layer", "external_id", name="uq_shom_feature"),
        Index("ix_shom_feature_geom", "geom", postgresql_using="gist"),
    )


class OsmFeature(_StagedFeature):
    __tablename__ = "osm_feature"
    __table_args__ = (
        UniqueConstraint("layer", "external_id", name="uq_osm_feature"),
        Index("ix_osm_feature_geom", "geom", postgresql_using="gist"),
    )


class ZmelFeature(_StagedFeature):
    __tablename__ = "zmel_feature"
    __table_args__ = (
        UniqueConstraint("layer", "external_id", name="uq_zmel_feature"),
        Index("ix_zmel_feature_geom", "geom", postgresql_using="gist"),
    )
