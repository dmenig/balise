from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, SmallInteger, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from balise_api.models.base import Base


class TidePrediction(Base):
    __tablename__ = "tide_prediction"

    harbour_id: Mapped[int] = mapped_column(
        ForeignKey("harbour.id", ondelete="CASCADE"), primary_key=True
    )
    at: Mapped[datetime] = mapped_column(primary_key=True)
    height_m: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False)
    kind: Mapped[str | None] = mapped_column(Text)
    coefficient: Mapped[int | None] = mapped_column(SmallInteger)
    fetched_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class WeatherForecast(Base):
    __tablename__ = "weather_forecast"

    harbour_id: Mapped[int] = mapped_column(
        ForeignKey("harbour.id", ondelete="CASCADE"), primary_key=True
    )
    at: Mapped[datetime] = mapped_column(primary_key=True)
    wind_kt: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    gust_kt: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    wind_dir_deg: Mapped[int | None] = mapped_column(SmallInteger)
    wave_m: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    fetched_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
