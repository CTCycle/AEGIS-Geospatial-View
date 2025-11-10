from __future__ import annotations

import os
from typing import Any

import pandas as pd
import sqlalchemy
from sqlalchemy import (
    BigInteger,
    Column,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import declarative_base, sessionmaker

from AEGIS.app.configurations import DATABASE_SETTINGS
from AEGIS.app.constants import DATA_PATH, DATABASE_FILENAME
from AEGIS.app.utils.singleton import singleton

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


# [DATABASE]
###############################################################################
@singleton
class AEGISDatabase:
    def __init__(self) -> None:
        self.db_path = os.path.join(DATA_PATH, DATABASE_FILENAME)
        self.engine = create_engine(
            f"sqlite:///{self.db_path}", echo=False, future=True
        )
        self.Session = sessionmaker(bind=self.engine, future=True)
        self.insert_batch_size = DATABASE_SETTINGS.insert_batch_size

    # -------------------------------------------------------------------------
    def initialize_database(self) -> None:
        Base.metadata.create_all(self.engine)

    # -------------------------------------------------------------------------
    def get_table_class(self, table_name: str) -> Any:
        for cls in Base.__subclasses__():
            if hasattr(cls, "__tablename__") and cls.__tablename__ == table_name:
                return cls
        raise ValueError(f"No table class found for name {table_name}")

    # -------------------------------------------------------------------------
    def upsert_dataframe(self, df: pd.DataFrame, table_cls) -> None:
        table = table_cls.__table__
        session = self.Session()
        try:
            unique_cols: list[str] = []
            for constraint in table.constraints:
                if isinstance(constraint, UniqueConstraint):
                    unique_cols = list(constraint.columns.keys())
                    break
            if not unique_cols:
                unique_cols = list(table.primary_key.columns.keys())
            if not unique_cols:
                raise ValueError(f"No unique columns found for {table_cls.__name__}")

            records = df.to_dict(orient="records")
            for i in range(0, len(records), self.insert_batch_size):
                batch = records[i : i + self.insert_batch_size]
                stmt = insert(table).values(batch)
                update_cols = {
                    column: getattr(stmt.excluded, column)  # type: ignore[attr-defined]
                    for column in batch[0]
                    if column not in unique_cols
                }
                stmt = stmt.on_conflict_do_update(
                    index_elements=unique_cols, set_=update_cols
                )
                session.execute(stmt)
            session.commit()
        finally:
            session.close()

    # -----------------------------------------------------------------------------
    def load_from_database(self, table_name: str) -> pd.DataFrame:
        query = f'SELECT * FROM "{table_name}"'
        with database.engine.connect() as connection:
            return pd.read_sql_query(query, connection)

    # -------------------------------------------------------------------------
    def save_into_database(self, df: pd.DataFrame, table_name: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(sqlalchemy.text(f'DELETE FROM "{table_name}"'))
            df.to_sql(table_name, conn, if_exists="append", index=False)

    # -------------------------------------------------------------------------
    def upsert_into_database(self, df: pd.DataFrame, table_name: str) -> None:
        table_cls = self.get_table_class(table_name)
        self.upsert_dataframe(df, table_cls)

    # -----------------------------------------------------------------------------
    def count_rows(self, table_name: str) -> int:
        with self.engine.connect() as conn:
            result = conn.execute(
                sqlalchemy.text(f'SELECT COUNT(*) FROM "{table_name}"')
            )
            value = result.scalar() or 0
        return int(value)


# -----------------------------------------------------------------------------
database = AEGISDatabase()
