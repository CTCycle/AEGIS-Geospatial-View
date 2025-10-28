from __future__ import annotations

from AEGIS.app.utils.updater import GeonamesUpdater


###############################################################################
class GeonamesUpdateScript:
    def __init__(self) -> None:
        self.updater = GeonamesUpdater()

    # -----------------------------------------------------------------------------
    def run(self) -> None:
        self.updater.update()


# -----------------------------------------------------------------------------
def main() -> None:
    script = GeonamesUpdateScript()
    script.run()


if __name__ == "__main__":
    main()
