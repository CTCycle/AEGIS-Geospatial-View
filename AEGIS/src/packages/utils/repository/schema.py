from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,    
)

from sqlalchemy.orm import declarative_base


Base = declarative_base()


###############################################################################
class GeonamesRecord(Base):
    __tablename__ = "GEONAMES"
    geonameid = Column(BigInteger, primary_key=True)
    name = Column(String(200))
    asciiname = Column(String(200))
    alternatenames = Column(Text)
    latitude = Column(Float)
    longitude = Column(Float)
    feature_class = Column(String(1))
    feature_code = Column(String(10))
    country_code = Column(String(2))
    cc2 = Column(String(200))
    admin1_code = Column(String(20))
    admin2_code = Column(String(80))
    admin3_code = Column(String(20))
    admin4_code = Column(String(20))
    population = Column(BigInteger)
    elevation = Column(Integer)
    dem = Column(Integer)
    timezone = Column(String(40))
    modification_date = Column(String(10))
    __table_args__ = (UniqueConstraint("geonameid"),)


###############################################################################
class GibsLayerRecord(Base):
    __tablename__ = "GIBS_LAYERS"
    layer_id = Column(String(256), primary_key=True)
    title = Column(String(512))
    abstract = Column(Text)
    projections = Column(Text)
    source_urls = Column(Text)
    __table_args__ = (UniqueConstraint("layer_id"),)
