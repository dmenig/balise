from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Enum, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from balise_api.domain.enums import SourceKind, SpotKind, SpotState


def _pg_enum[E: StrEnum](enum: type[E], name: str) -> Enum:
    """Map to the enum *values* ('mooring_buoy'), which is what the Postgres type holds."""
    return Enum(
        enum,
        name=name,
        create_type=False,
        native_enum=True,
        values_callable=lambda members: [member.value for member in members],
    )


class Base(DeclarativeBase):
    type_annotation_map = {  # noqa: RUF012
        dict[str, Any]: JSONB,
        datetime: DateTime(timezone=True),
        SpotKind: _pg_enum(SpotKind, "spot_kind"),
        SpotState: _pg_enum(SpotState, "spot_state"),
        SourceKind: _pg_enum(SourceKind, "source_kind"),
    }


class Meta(Base):
    """Single-row-per-key metadata. Holds `ref_version`, which keys every tile ETag."""

    __tablename__ = "meta"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
