import pytest

from backend.app.services.connector_registry import (
    ConnectorRegistry,
    ConnectorRegistryError,
    derive_fernet_key,
)
from common.enums import AssetClass


def make_registry(secret="jwt-secret"):
    return ConnectorRegistry(derive_fernet_key(secret))


def test_derive_fernet_key_is_deterministic():
    assert derive_fernet_key("same-secret") == derive_fernet_key("same-secret")
    assert derive_fernet_key("secret-a") != derive_fernet_key("secret-b")


def test_derive_fernet_key_is_valid_fernet_key():
    from cryptography.fernet import Fernet

    key = derive_fernet_key("anything")
    Fernet(key)  # raises if invalid


def test_create_and_decrypt_credentials_roundtrip():
    registry = make_registry()
    record = registry.create_connector(
        "binance-main", "ccxt", AssetClass.CRYPTO, {"api_key": "abc", "api_secret": "xyz"}
    )
    assert record.encrypted_credentials != b'{"api_key": "abc", "api_secret": "xyz"}'  # actually encrypted

    decrypted = registry.decrypt_credentials(record.id)
    assert decrypted == {"api_key": "abc", "api_secret": "xyz"}


def test_list_connectors_never_exposes_plaintext():
    registry = make_registry()
    registry.create_connector("binance-main", "ccxt", AssetClass.CRYPTO, {"api_key": "super-secret"})
    for record in registry.list_connectors():
        assert "super-secret" not in str(record.encrypted_credentials)


def test_duplicate_name_rejected():
    registry = make_registry()
    registry.create_connector("dup", "paper", AssetClass.CRYPTO, {})
    with pytest.raises(ConnectorRegistryError):
        registry.create_connector("dup", "paper", AssetClass.CRYPTO, {})


def test_get_unknown_connector_raises():
    registry = make_registry()
    with pytest.raises(ConnectorRegistryError):
        registry.get_connector("nonexistent")


def test_decrypt_with_wrong_key_fails():
    registry_a = make_registry("secret-a")
    record = registry_a.create_connector("conn1", "paper", AssetClass.CRYPTO, {"key": "value"})

    registry_b = make_registry("secret-b")
    registry_b._connectors[record.id] = record  # simulate cross-instance access with a different key
    with pytest.raises(ConnectorRegistryError):
        registry_b.decrypt_credentials(record.id)


def test_deactivate_connector():
    registry = make_registry()
    record = registry.create_connector("conn1", "paper", AssetClass.CRYPTO, {})
    assert record.is_active
    registry.deactivate(record.id)
    assert not registry.get_connector(record.id).is_active
