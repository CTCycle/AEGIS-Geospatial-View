from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


###############################################################################
class Base(DeclarativeBase):
    pass


###############################################################################
class GeonamesRecord(Base):
    __tablename__ = "GEONAMES"

    geonameid: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str | None] = mapped_column(String(200))
    asciiname: Mapped[str | None] = mapped_column(String(200))
    alternatenames: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    feature_class: Mapped[str | None] = mapped_column(String(1))
    feature_code: Mapped[str | None] = mapped_column(String(10))
    country_code: Mapped[str | None] = mapped_column(String(2))
    cc2: Mapped[str | None] = mapped_column(String(200))
    admin1_code: Mapped[str | None] = mapped_column(String(20))
    admin2_code: Mapped[str | None] = mapped_column(String(80))
    admin3_code: Mapped[str | None] = mapped_column(String(20))
    admin4_code: Mapped[str | None] = mapped_column(String(20))
    population: Mapped[int | None] = mapped_column(BigInteger)
    elevation: Mapped[int | None] = mapped_column(Integer)
    dem: Mapped[int | None] = mapped_column(Integer)
    timezone: Mapped[str | None] = mapped_column(String(40))
    modification_date: Mapped[str | None] = mapped_column(String(10))

    __table_args__ = (UniqueConstraint("geonameid"),)


###############################################################################
class GibsLayerRecord(Base):
    __tablename__ = "GIBS_LAYERS"

    layer_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    title: Mapped[str | None] = mapped_column(String(512))
    abstract: Mapped[str | None] = mapped_column(Text)
    projections: Mapped[str | None] = mapped_column(Text)
    source_urls: Mapped[str | None] = mapped_column(Text)
    tile_matrix_sets: Mapped[str | None] = mapped_column(Text)
    meters_per_pixel: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("layer_id"),)


###############################################################################
class SearchSessionRecord(Base):
    __tablename__ = "SEARCH_SESSIONS"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    user: Mapped[str | None] = mapped_column(String(200))
    country: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(String(400))
    coordinates: Mapped[str | None] = mapped_column(String(128))
    base_map: Mapped[str | None] = mapped_column(String(200))
    geospatial_layers: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str | None] = mapped_column(String(20))

    __table_args__ = (UniqueConstraint("id"),)
