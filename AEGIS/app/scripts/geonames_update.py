from __future__ import annotations

from AEGIS.app.utils.repository.database import database
from AEGIS.app.utils.updater import GeonamesUpdater


# -----------------------------------------------------------------------------
def main() -> None:
    database.initialize_database()
    updater = GeonamesUpdater()
    updater.update()


if __name__ == "__main__":
    main()
