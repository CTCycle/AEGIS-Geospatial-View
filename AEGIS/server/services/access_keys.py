from __future__ import annotations

from AEGIS.server.domain.access_keys import AccessKeyResponse
from AEGIS.server.repositories.serialization.access_keys import AccessKeySerializer


class AccessKeyValidationError(ValueError):
    pass


class AccessKeyNotFoundError(LookupError):
    pass


class AccessKeyServiceError(RuntimeError):
    pass


class AccessKeysService:
    def __init__(self, serializer: AccessKeySerializer | None = None) -> None:
        self._serializer = serializer or AccessKeySerializer()

    def _to_response(self, row: object) -> AccessKeyResponse:
        return AccessKeyResponse(
            id=row.id,
            provider=row.provider,
            is_active=row.is_active,
            fingerprint=row.fingerprint,
            created_at=row.created_at,
            updated_at=row.updated_at,
            last_used_at=row.last_used_at,
        )

    def list_keys(self, provider: str) -> list[AccessKeyResponse]:
        try:
            rows = self._serializer.list_keys(provider)
            return [self._to_response(row) for row in rows]
        except ValueError as exc:
            raise AccessKeyValidationError(str(exc)) from exc

    def create_key(self, provider: str, plaintext_key: str) -> AccessKeyResponse:
        try:
            row = self._serializer.create_key(provider, plaintext_key)
            return self._to_response(row)
        except ValueError as exc:
            raise AccessKeyValidationError(str(exc)) from exc
        except RuntimeError as exc:
            raise AccessKeyServiceError(str(exc)) from exc

    def activate_key(self, key_id: int, provider: str) -> AccessKeyResponse:
        try:
            row = self._serializer.activate_key(key_id, provider)
            return self._to_response(row)
        except ValueError as exc:
            raise AccessKeyValidationError(str(exc)) from exc
        except KeyError as exc:
            raise AccessKeyNotFoundError(str(exc)) from exc

    def delete_key(self, key_id: int, provider: str) -> None:
        try:
            self._serializer.delete_key(key_id, provider)
        except ValueError as exc:
            raise AccessKeyValidationError(str(exc)) from exc
        except KeyError as exc:
            raise AccessKeyNotFoundError(str(exc)) from exc