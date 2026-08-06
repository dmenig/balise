from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Numeric,
    SmallInteger,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from balise_api.models.base import Base


class Contributor(Base):
    __tablename__ = "contributor"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    device_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(Text, unique=True)
    reputation: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), nullable=False, server_default="1.0", default=Decimal("1.0")
    )
    banned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class Comment(Base):
    __tablename__ = "comment"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    spot_id: Mapped[int | None] = mapped_column(ForeignKey("spot.id", ondelete="CASCADE"))
    harbour_id: Mapped[int | None] = mapped_column(ForeignKey("harbour.id", ondelete="CASCADE"))
    contributor_id: Mapped[int] = mapped_column(ForeignKey("contributor.id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    rating: Mapped[int | None] = mapped_column(SmallInteger)
    photo_keys: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{}", default=list
    )
    moderated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("rating IS NULL OR rating BETWEEN 1 AND 5", name="ck_comment_rating"),
    )


class Issue(Base):
    """Bad-data report → moderation queue (docs/08 `POST /issues`)."""

    __tablename__ = "issue"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    spot_id: Mapped[int | None] = mapped_column(ForeignKey("spot.id", ondelete="CASCADE"))
    harbour_id: Mapped[int | None] = mapped_column(ForeignKey("harbour.id", ondelete="CASCADE"))
    nav_aid_id: Mapped[int | None] = mapped_column(ForeignKey("nav_aid.id", ondelete="CASCADE"))
    contributor_id: Mapped[int | None] = mapped_column(ForeignKey("contributor.id"))
    category: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        nullable=False, server_default="{}", default=dict
    )
    resolved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
