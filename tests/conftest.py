import os
import sys

import pytest

_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _ROOT)
# `ate_smp` is distributed as a standalone SDK package rooted at sdk/ (DOC 3 §10);
# add it so `import ate_smp` resolves the same way it will for strategy authors.
sys.path.insert(0, os.path.join(_ROOT, "sdk"))


@pytest.fixture(autouse=True)
def _redirect_decision_audit(tmp_path, monkeypatch):
    """RiskManager.check_pre_trade unconditionally appends to the immutable
    decision audit trail (DOC 2 §8) at LOG_DIR/decision_audit.jsonl, which
    defaults to /var/log/ate-smp — a real path outside any test's sandbox.
    Redirect it everywhere so no test suite run leaves files behind on the
    real filesystem; tests that specifically exercise this path can still
    override it again locally (see tests/unit/test_risk_manager.py)."""
    target = tmp_path / "decision_audit.jsonl"
    monkeypatch.setattr("engine.risk.risk_manager.decision_audit_path", lambda: str(target))
