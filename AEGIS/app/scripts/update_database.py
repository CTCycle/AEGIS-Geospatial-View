from __future__ import annotations

from AEGIS.app.constants import SOURCES_PATH
from AEGIS.app.logger import logger
from AEGIS.app.utils.database.sqlite import database
from AEGIS.app.utils.updater.livertox import LiverToxUpdater

REDOWNLOAD = True

###############################################################################
if __name__ == "__main__":
    updater = LiverToxUpdater(
        SOURCES_PATH,
        redownload=REDOWNLOAD,
    )
    database.initialize_database()
    logger.info("Running LiverTox updater")
    result = updater.update_from_livertox()
    logger.info("LiverTox updater summary: %s", result)
    

