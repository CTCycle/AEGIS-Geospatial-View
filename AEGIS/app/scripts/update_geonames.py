from __future__ import annotations

from AEGIS.app.logger import logger
from AEGIS.app.utils.repository.database import database
from AEGIS.app.utils.updater import GeonamesUpdater

logger = logger.getChild("update_geonames_script")

###############################################################################
def run() -> None:
    logger.info("Starting sanitized geonames update process")
    database.initialize_database()
    updater = GeonamesUpdater()
    updater.update()


###############################################################################
if __name__ == "__main__":
    run()
