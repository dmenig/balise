from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    Text,
    desc,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from balise_api.domain.enums import SourceKind, SpotState
from balise_api.models.base import Base


class Feed(Base):
    """A partner-operated source of observations (MBFS, ADR-0004)."""

    __tablename__ = "feed"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    harbour_id: Mapped[int] = mapped_column(ForeignKey("harbour.id"), nullable=False)
    kind: Mapped[SourceKind]
    contact_email: Mapped[str] = mapped_column(Text, nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    pull_url: Mapped[str | None] = mapped_column(Text)
    poll_seconds: Mapped[int | None]
    ttl_seconds: Mapped[int] = mapped_column(nullable=False, server_default="60", default=60)
    trust: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), nullable=False, server_default="0.95", default=Decimal("0.95")
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true", default=True
    )
    last_seen_at: Mapped[datetime | None]
    accepted_24h: Mapped[int] = mapped_column(nullable=False, server_default="0", default=0)
    rejected_24h: Mapped[int] = mapped_column(nullable=False, server_default="0", default=0)


class Observation(Base):
    """Append-only, immutable except for `suppressed` (ADR-0003)."""

    __tablename__ = "observation"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    spot_id: Mapped[int | None] = mapped_column(ForeignKey("spot.id", ondelete="CASCADE"))
    field_id: Mapped[int | None] = mapped_column(ForeignKey("field.id", ondelete="CASCADE"))
    state: Mapped[SpotState]
    free_count: Mapped[int | None]
    source_kind: Mapped[SourceKind]
    source_ref: Mapped[str | None] = mapped_column(Text)
    contributor_id: Mapped[int | None] = mapped_column(
        ForeignKey("contributor.id", ondelete="SET NULL")
    )
    observed_at: Mapped[datetime] = mapped_column(nullable=False)
    received_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        nullable=False, server_default="{}", default=dict
    )
    suppressed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    idempotency_key: Mapped[str | None] = mapped_column(Text, unique=True)

    __table_args__ = (
        CheckConstraint(
            "spot_id IS NOT NULL OR field_id IS NOT NULL", name="ck_observation_target"
        ),
        Index("ix_observation_spot", "spot_id", desc("observed_at")),
        Index("ix_observation_field", "field_id", desc("observed_at")),
        Index("ix_observation_received", desc("received_at")),
        Index("ix_observation_contributor", "contributor_id"),
    )


class SpotStatus(Base):
    """Derived projection of `observation` — a cache, never a source of truth."""

    __tablename__ = "spot_status"

    spot_id: Mapped[int] = mapped_column(
        ForeignKey("spot.id", ondelete="CASCADE"), primary_key=True
    )
    state: Mapped[SpotState]
    confidence: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False)
    as_of: Mapped[datetime] = mapped_column(nullable=False)
    source_kind: Mapped[SourceKind]
    observation_id: Mapped[int | None] = mapped_column(
        ForeignKey("observation.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_spot_status_state", "state", desc("confidence")),
        Index("ix_spot_status_updated", desc("updated_at")),
    )


class FieldStatus(Base):
    __tablename__ = "field_status"

    field_id: Mapped[int] = mapped_column(
        ForeignKey("field.id", ondelete="CASCADE"), primary_key=True
    )
    free_count: Mapped[int | None]
    capacity: Mapped[int | None]
    confidence: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False)
    as_of: Mapped[datetime] = mapped_column(nullable=False)
    source_kind: Mapped[SourceKind]
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "capacity IS NULL OR free_count IS NULL OR free_count <= capacity",
            name="ck_field_status_capacity",
        ),
        Index("ix_field_status_updated", desc("updated_at")),
    )
