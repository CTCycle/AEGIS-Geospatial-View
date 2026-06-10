from __future__ import annotations

from server.repositories.database import DatabaseBackend as exported_contract
from server.repositories.database.contracts import DatabaseBackend


###############################################################################
def test_database_backend_contract_is_reexported() -> None:
    assert exported_contract is DatabaseBackend
