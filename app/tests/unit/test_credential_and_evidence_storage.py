from __future__ import annotations
import asyncio
import threading

import pytest

from server.configurations import DatabaseSettings
from server.repositories.agent_evidence import (
    AgentEvidenceRepository,
    create_evidence_async,
)
from server.repositories.conversations import ConversationRepository
from server.repositories.database.sqlite import SQLiteRepository
from server.repositories.schemas import Base
from server.services.cryptography import CredentialEncryptionService
from server.repositories.credentials import CredentialRepository
from fastapi.testclient import TestClient
from server.app import create_app
from server.services.geospatial.layer_auditor import audit_all_manifests
from server.services.catalog.loader import load_reference_catalog
from server.services.sanitization import LocationSanitizationService

# --- test_agent_evidence_repository.py ---


###############################################################################
def _database(tmp_path):  # noqa: ANN001
    database = SQLiteRepository(DatabaseSettings(database_path=str(tmp_path / "evidence.db")))
    Base.metadata.create_all(database.engine)
    return database

###############################################################################
def test_evidence_round_trip_checksum_and_parent_provenance(tmp_path) -> None:  # noqa: ANN001
    database = _database(tmp_path)
    conversation = ConversationRepository(database).create_conversation("Evidence")
    repository = AgentEvidenceRepository(database)

    parent = repository.create(
        conversation_id=conversation.id,
        run_id=None,
        kind="tabular",
        media_type="application/json",
        status="available",
        payload={
            "records": [{"id": "a", "value": 3}],
            "provider_metadata": {"access_token": "must-not-persist"},
        },
        summary={"record_count": 1, "api_key": "must-not-persist"},
        provenance={"provider": "test", "authorization": "redacted"},
    )
    child = repository.create(
        conversation_id=conversation.id,
        run_id=None,
        kind="derived",
        media_type="application/json",
        status="available",
        payload={"records": [{"id": "a"}]},
        summary={"record_count": 1},
        provenance={"operation": "field_projection"},
        parent_evidence_ids=[parent.evidence_id],
    )

    loaded = repository.get_payload(child.evidence_id)
    assert loaded is not None
    summary, raw = loaded
    assert summary.parent_evidence_ids == [parent.evidence_id]
    assert b'"id":"a"' in raw
    assert b"access_token" not in raw
    assert "api_key" not in parent.summary
    assert "authorization" not in parent.provenance

###############################################################################
def test_evidence_metadata_cascade_deletes_with_conversation(tmp_path) -> None:  # noqa: ANN001
    database = _database(tmp_path)
    conversation = ConversationRepository(database).create_conversation("Cascade")
    repository = AgentEvidenceRepository(database)
    item = repository.create(
        conversation_id=conversation.id,
        run_id=None,
        kind="diagnostic",
        media_type="application/json",
        status="failed",
        payload={"error": {"code": "provider_unavailable"}},
        summary={"status": "failed"},
    )
    assert repository.get_summary(item.evidence_id) is not None
    other = ConversationRepository(database).create_conversation("Other")
    assert repository.get_summary(item.evidence_id, conversation_id=other.id) is None
    assert repository.get_payload(item.evidence_id, conversation_id=other.id) is None
    with database.session() as session:
        record = session.get(type(conversation), conversation.id)
        session.delete(record)
        session.commit()
    assert repository.get_summary(item.evidence_id) is None

###############################################################################
class _SlowRepository:
    def __init__(self, release: threading.Event) -> None:
        self.release = release
        self.started = threading.Event()
        self.completed = 0

    def create(self, **fields):  # noqa: ANN003, ANN201
        self.started.set()
        self.release.wait(timeout=5)
        self.completed += 1
        return fields

###############################################################################
async def test_evidence_write_does_not_block_event_loop() -> None:
    release = threading.Event()
    repository = _SlowRepository(release)
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while not release.is_set():
            ticks += 1
            await asyncio.sleep(0.005)

    write = asyncio.create_task(create_evidence_async(repository, kind="x"))
    watcher = asyncio.create_task(ticker())
    await asyncio.sleep(0.1)
    release.set()
    assert (await write) == {"kind": "x"}
    await watcher
    assert ticks >= 5

###############################################################################
async def test_cancelled_evidence_write_returns_no_reference(tmp_path) -> None:  # noqa: ANN001
    database = _database(tmp_path)
    conversation = ConversationRepository(database).create_conversation("Cancel")
    real = AgentEvidenceRepository(database)
    release = threading.Event()
    slow = _SlowRepository(release)
    slow.create = lambda **fields: (  # type: ignore[method-assign]
        slow.started.set(), release.wait(timeout=5), real.create(**fields)
    )[-1]

    write = asyncio.create_task(
        create_evidence_async(
            slow,
            conversation_id=conversation.id,
            run_id=None,
            kind="tabular",
            media_type="application/json",
            status="available",
            payload={"records": [1]},
        )
    )
    await asyncio.sleep(0.05)
    write.cancel()
    with pytest.raises(asyncio.CancelledError):
        await write
    release.set()
    await asyncio.sleep(0.2)

    # The caller never received a ref; any record that landed is complete and valid.
    for summary in real.list_summaries(conversation.id):
        loaded = real.get_payload(summary.evidence_id)
        assert loaded is not None
        assert loaded[1] == b'{"records":[1]}'

# --- test_credential_crypto.py ---


###############################################################################
def test_credential_crypto_roundtrip() -> None:
    service = CredentialEncryptionService(
        master_key="unit-test-master-key", key_version="v1"
    )
    encrypted = service.encrypt("secret-value")
    assert encrypted.value
    assert encrypted.key_version == "v1"
    decrypted = service.decrypt(encrypted.value)
    assert decrypted == "secret-value"
    assert service.mask(encrypted.value) == "••••••••"

# --- test_credentials_repository.py ---


###############################################################################
def test_credentials_repository_upsert_and_lookup(sqlite_backend) -> None:
    repository = CredentialRepository(sqlite_backend)
    record = repository.upsert(
        provider="openai",
        label="api_key",
        encrypted_value="encrypted-token",
        key_version="v1",
    )
    assert record.provider == "openai"
    loaded = repository.get_active(provider="openai", label="api_key")
    assert loaded is not None
    assert loaded.encrypted_value == "encrypted-token"

# --- test_geospatial_api_credentials.py ---


###############################################################################
def create_started_client() -> TestClient:
    client = TestClient(create_app())
    client.__enter__()
    return client

###############################################################################
def test_credential_status_uses_saved_storage_and_does_not_return_secret_values(
    monkeypatch,
) -> None:
    monkeypatch.setenv("WINDY_WEBCAMS_API_KEY", "windy-secret")
    client = create_started_client()

    response = client.get("/api/geospatial/sources/windy_webcams/credential-status")

    assert response.status_code == 200
    assert response.json()["configured"] is False
    assert "windy-secret" not in response.text
    assert "environmentVariable" not in response.json()

# --- test_geospatial_manifest_secret_safety.py ---


###############################################################################
def test_geospatial_manifests_do_not_contain_secret_values() -> None:
    report = audit_all_manifests(strict=True)
    issues = [
        issue
        for issue in report.issues
        if issue.message == "Manifest appears to contain a secret-like value."
    ]

    assert not issues

# --- test_sanitization.py ---


###############################################################################
def test_country_canonical_names_and_aliases_normalize_through_reference_mapping() -> (
    None
):
    catalog = load_reference_catalog()
    alias_map = {
        entry.alias.strip().casefold(): entry.iso2 for entry in catalog.country_aliases
    }
    service = LocationSanitizationService(alias_map)

    assert service.normalize_country("United States") == "US"
    assert service.normalize_country("USA") == "US"
    assert service.normalize_country("Macau") == "MO"