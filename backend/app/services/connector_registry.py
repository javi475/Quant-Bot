"""Connector credential storage (DOC 6 §10: "connector credentials AES-256
(Fernet) encrypted at rest keyed off JWT_SECRET"). Credentials are never
returned decrypted through any listing/get API — only `decrypt_credentials`
does that, and only the Engine bootstrap path (constructing real connectors)
should ever call it.
"""

from __future__ import annotations

import base64
import hashlib
import itertools
import json
from dataclasses import dataclass, field
from typing import Any, Optional

from cryptography.fernet import Fernet, InvalidToken

from common.enums import AssetClass


class ConnectorRegistryError(Exception):
    pass


def derive_fernet_key(secret: str) -> bytes:
    """JWT_SECRET is an arbitrary-length string (e.g. `openssl rand -hex 32`),
    not a valid Fernet key on its own — Fernet needs exactly 32 url-safe
    base64-encoded bytes. Hash it down to a fixed-size key deterministically."""
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


@dataclass
class ConnectorRecord:
    id: str
    name: str
    connector_type: str
    asset_class: AssetClass
    encrypted_credentials: bytes
    config: dict = field(default_factory=dict)
    is_active: bool = True


class ConnectorRegistry:
    def __init__(self, encryption_key: bytes) -> None:
        self._fernet = Fernet(encryption_key)
        self._connectors: dict[str, ConnectorRecord] = {}
        self._id_counter = itertools.count(1)

    def create_connector(
        self,
        name: str,
        connector_type: str,
        asset_class: AssetClass,
        credentials: dict[str, Any],
        config: Optional[dict] = None,
    ) -> ConnectorRecord:
        if any(c.name == name for c in self._connectors.values()):
            raise ConnectorRegistryError(f"connector name '{name}' already exists")

        encrypted = self._fernet.encrypt(json.dumps(credentials).encode("utf-8"))
        connector_id = f"conn_{next(self._id_counter):03d}"
        record = ConnectorRecord(
            id=connector_id,
            name=name,
            connector_type=connector_type,
            asset_class=asset_class,
            encrypted_credentials=encrypted,
            config=config or {},
        )
        self._connectors[connector_id] = record
        return record

    def get_connector(self, connector_id: str) -> ConnectorRecord:
        record = self._connectors.get(connector_id)
        if record is None:
            raise ConnectorRegistryError(f"unknown connector_id '{connector_id}'")
        return record

    def list_connectors(self) -> list[ConnectorRecord]:
        return list(self._connectors.values())

    def decrypt_credentials(self, connector_id: str) -> dict[str, Any]:
        record = self.get_connector(connector_id)
        try:
            raw = self._fernet.decrypt(record.encrypted_credentials)
        except InvalidToken as exc:
            raise ConnectorRegistryError(
                f"could not decrypt credentials for '{connector_id}' — wrong key?"
            ) from exc
        return json.loads(raw)

    def deactivate(self, connector_id: str) -> None:
        self.get_connector(connector_id).is_active = False
