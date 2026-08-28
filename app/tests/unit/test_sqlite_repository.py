from __future__ import annotations

from pathlib import Path

from server.configurations import DatabaseSettings
from server.repositories.database.sqlite import SQLiteRepository
from server.repositories.schemas import Base, ReferenceCountryRecord

###############################################################################
def test_repository_creates_parent_directory_for_database_path(tmp_path: Path) -> None:
    database_path = tmp_path / "nested" / "data" / "database.db"

    repository = SQLiteRepository(DatabaseSettings(database_path=str(database_path)))

    assert database_path.parent.is_dir()
    repository.engine.dispose()

###############################################################################
def test_repository_counts_records_using_short_lived_sessions(tmp_path: Path) -> None:
    repository = SQLiteRepository(
        DatabaseSettings(database_path=str(tmp_path / "database.db"))
    )
    Base.metadata.create_all(repository.engine)

    with repository.session() as session:
        session.add(ReferenceCountryRecord(iso2="IT", name="Italy", name_key="italy"))
        session.commit()

    assert repository.count_records(ReferenceCountryRecord) == 1
    repository.engine.dispose()
