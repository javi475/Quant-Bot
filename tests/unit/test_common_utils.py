from common import redis_keys
from common.logging_config import configure_logging, decision_audit_path


def test_redis_key_templates():
    assert redis_keys.strategy_state_key("abc") == "strategy:abc:state"
    assert redis_keys.connector_status_key("xyz") == "connector:xyz:status"
    assert redis_keys.HEARTBEAT_TTL_SECONDS == 15
    assert redis_keys.SAFE_MODE_TTL_SECONDS == 48 * 3600


def test_decision_audit_path_uses_log_dir(monkeypatch):
    import importlib
    import os

    monkeypatch.setenv("LOG_DIR", "/tmp/ate-smp-logs")
    from common import logging_config as lc

    importlib.reload(lc)
    assert lc.decision_audit_path() == os.path.join("/tmp/ate-smp-logs", "decision_audit.jsonl")
    importlib.reload(lc)  # restore module state for other tests


def test_configure_logging_returns_bound_logger():
    logger = configure_logging("test-service")
    logger.info("smoke_test", key="value")
