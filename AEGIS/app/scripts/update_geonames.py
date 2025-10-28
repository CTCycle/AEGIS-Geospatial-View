from __future__ import annotations

from AEGIS.app.utils.repository.database import database
from AEGIS.app.utils.updater import GeonamesUpdater

###############################################################################
if __name__ == "__main__":
    database.initialize_database()
    updater = GeonamesUpdater()
    updater.update()
