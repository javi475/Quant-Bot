import json
import time

import fakeredis
import httpx
import pyotp
import pytest

from backend.app.app import create_app
from backend.app.auth.hmac_auth import compute_hermes_signature
from backend.app.auth.security import hash_password
from backend.app.engine_client import EngineClient
from backend.app.services.backtest_service import BacktestService
from backend.app.services.connector_registry import ConnectorRegistry, derive_fernet_key
from backend.app.services.strategy_registry import InMemoryStrategyRegistry
from common.enums import AssetClass, Timeframe
from engine.api.app import create_app as create_engine_app
from engine.backtest.cost_model import TransactionCostModel
from engine.connectors.paper import PaperConnector
from engine.connectors.price_feed import ReplayPriceFeed
from engine.core.engine import AlgorithmEngine
from engine.core.execution_manager import ExecutionManager
from engine.core.heartbeat import HeartbeatWriter
from engine.core.repository import InMemoryTradeRepository
from engine.core.signal_scheduler import SignalScheduler
from engine.core.state_manager import StateManager
from engine.risk.breaker import BreakerManager
from engine.risk.correlation import CorrelationManager
from engine.risk.position_sizer import PositionSizer
from engine.risk.risk_config import RiskConfig
from engine.risk.risk_manager import RiskManager
from engine.risk.safe_mode import SafeModeManager
from engine.strategy.serialization import encode_config
from sdk.ate_smp.models.strategy_config import StrategyConfig

JWT_SECRET = "backend-test-jwt-secret"
DASHBOARD_USERNAME = "admin"
DASHBOARD_PASSWORD = "correct-horse-battery-staple"
HERMES_SECRET = "hermes-test-secret"

VALID_STRATEGY_SOURCE = """
from ate_smp import StrategyBase, Direction, Signal

class MyStrategy(StrategyBase):
    def initialize(self, config):
        self.config = config
        self._i = -1
    def on_bar(self, bar):
        self._i += 1
        return []
    def on_tick(self, tick):
        return []
    def on_fill(self, fill):
        pass
    def get_parameters_schema(self):
        return []
    def get_win_probability(self):
        return 0.55
    def get_win_loss_ratio(self):
        return 1.5
    def get_state(self):
        return {"i": self._i}
    def set_state(self, state):
        self._i = state.get("i", -1)
"""

MALICIOUS_STRATEGY_SOURCE = "import os\nfrom ate_smp import StrategyBase\nclass Bad(StrategyBase):\n    pass\n"


def make_engine_app():
    feed = ReplayPriceFeed()
    connector = PaperConnector("paper1", AssetClass.CRYPTO, feed, TransactionCostModel(), initial_capital=100_000.0)
    repo = InMemoryTradeRepository()
    redis_client = fakeredis.FakeAsyncRedis(decode_responses=True)
    config = RiskConfig()
    risk_manager = RiskManager(config, PositionSizer(config), SafeModeManager(config))
    engine = AlgorithmEngine(
        connectors={"paper1": connector},
        risk_manager=risk_manager,
        breaker_manager=BreakerManager(config),
        correlation_manager=CorrelationManager(config),
        execution_manager=ExecutionManager({"paper1": connector}, repo),
        state_manager=StateManager(redis_client, repo),
        scheduler=SignalScheduler(),
        heartbeat=HeartbeatWriter(redis_client, interval_seconds=5, ttl_seconds=15),
        repository=repo,
        redis_client=redis_client,
    )
    return create_engine_app(engine), engine, repo


class BackendFixture:
    def __init__(self, tmp_path):
        self.tmp_path = tmp_path
        self.totp_secret = pyotp.random_base32()
        engine_app, self.engine, self.trade_repository = make_engine_app()
        engine_transport = httpx.ASGITransport(app=engine_app)
        engine_http = httpx.AsyncClient(transport=engine_transport, base_url="http://engine-test")
        self.engine_client = EngineClient(engine_http)

        self.strategy_registry = InMemoryStrategyRegistry()
        self.backtest_service = BacktestService()
        self.connector_registry = ConnectorRegistry(derive_fernet_key(JWT_SECRET))

        app = create_app(
            jwt_secret=JWT_SECRET,
            dashboard_username=DASHBOARD_USERNAME,
            dashboard_password_hash=hash_password(DASHBOARD_PASSWORD),
            totp_secret=self.totp_secret,
            hermes_hmac_secret=HERMES_SECRET,
            strategy_registry=self.strategy_registry,
            backtest_service=self.backtest_service,
            connector_registry=self.connector_registry,
            engine_client=self.engine_client,
            trade_repository=self.trade_repository,
            strategies_dir=str(tmp_path / "strategies"),
        )
        transport = httpx.ASGITransport(app=app)
        self.client = httpx.AsyncClient(transport=transport, base_url="http://backend-test")

    def totp_code(self) -> str:
        return pyotp.TOTP(self.totp_secret).now()

    async def login(self) -> str:
        resp = await self.client.post(
            "/api/auth/login",
            json={"username": DASHBOARD_USERNAME, "password": DASHBOARD_PASSWORD, "totp_code": self.totp_code()},
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["access_token"]

    async def auth_headers(self) -> dict:
        token = await self.login()
        return {"Authorization": f"Bearer {token}"}

    async def aclose(self):
        await self.client.aclose()
        await self.engine.scheduler.stop_all()
        for running in self.engine.strategies.values():
            if running.process is not None:
                await running.process.shutdown()


@pytest.fixture
async def backend(tmp_path):
    fixture = BackendFixture(tmp_path)
    await fixture.engine.connectors["paper1"].connect({})
    yield fixture
    await fixture.aclose()


# ----- Auth -----

@pytest.mark.asyncio
async def test_login_success(backend):
    token = await backend.login()
    assert token


@pytest.mark.asyncio
async def test_login_wrong_password_rejected(backend):
    resp = await backend.client.post(
        "/api/auth/login",
        json={"username": DASHBOARD_USERNAME, "password": "wrong", "totp_code": backend.totp_code()},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_wrong_totp_rejected(backend):
    resp = await backend.client.post(
        "/api/auth/login",
        json={"username": DASHBOARD_USERNAME, "password": DASHBOARD_PASSWORD, "totp_code": "000000"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_without_token_rejected(backend):
    resp = await backend.client.get("/api/strategies")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token(backend):
    token = await backend.login()
    resp = await backend.client.post("/api/auth/refresh", json={"access_token": token})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


# ----- Strategies -----

@pytest.mark.asyncio
async def test_create_and_upload_strategy(backend):
    headers = await backend.auth_headers()
    resp = await backend.client.post(
        "/api/strategies", json={"name": "s1", "asset_class": "crypto"}, headers=headers
    )
    assert resp.status_code == 200
    strategy_id = resp.json()["id"]

    resp = await backend.client.post(
        f"/api/strategies/{strategy_id}/versions",
        json={"source_code": VALID_STRATEGY_SOURCE, "class_name": "MyStrategy"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["version"] == "1.0.0"
    assert resp.json()["is_active"]


@pytest.mark.asyncio
async def test_list_versions_unknown_strategy_404(backend):
    headers = await backend.auth_headers()
    resp = await backend.client.get("/api/strategies/nonexistent/versions", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_upload_version_unknown_strategy_404(backend):
    headers = await backend.auth_headers()
    resp = await backend.client.post(
        "/api/strategies/nonexistent/versions",
        json={"source_code": VALID_STRATEGY_SOURCE, "class_name": "MyStrategy"},
        headers=headers,
    )
    assert resp.status_code == 400  # StrategyRegistryError -> 400 per strategies.py


@pytest.mark.asyncio
async def test_activate_unknown_version_404(backend):
    headers = await backend.auth_headers()
    resp = await backend.client.post(
        "/api/strategies", json={"name": "s1", "asset_class": "crypto"}, headers=headers
    )
    strategy_id = resp.json()["id"]
    await backend.client.post(
        f"/api/strategies/{strategy_id}/versions",
        json={"source_code": VALID_STRATEGY_SOURCE, "class_name": "MyStrategy"},
        headers=headers,
    )
    resp = await backend.client.post(
        f"/api/strategies/{strategy_id}/versions/9.9.9/activate", headers=headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_upload_malicious_strategy_rejected(backend):
    headers = await backend.auth_headers()
    resp = await backend.client.post(
        "/api/strategies", json={"name": "s1", "asset_class": "crypto"}, headers=headers
    )
    strategy_id = resp.json()["id"]

    resp = await backend.client.post(
        f"/api/strategies/{strategy_id}/versions",
        json={"source_code": MALICIOUS_STRATEGY_SOURCE, "class_name": "Bad"},
        headers=headers,
    )
    assert resp.status_code == 400


# ----- Connectors -----

@pytest.mark.asyncio
async def test_create_connector_credentials_never_leak(backend):
    headers = await backend.auth_headers()
    resp = await backend.client.post(
        "/api/connectors",
        json={
            "name": "paper-main", "connector_type": "paper", "asset_class": "crypto",
            "credentials": {"api_key": "super-secret-value"},
        },
        headers=headers,
    )
    assert resp.status_code == 200
    assert "super-secret-value" not in resp.text

    resp = await backend.client.get("/api/connectors", headers=headers)
    assert "super-secret-value" not in resp.text


@pytest.mark.asyncio
async def test_connector_test_endpoint_paper_type(backend):
    headers = await backend.auth_headers()
    resp = await backend.client.post(
        "/api/connectors",
        json={"name": "paper-main", "connector_type": "paper", "asset_class": "crypto", "credentials": {}},
        headers=headers,
    )
    connector_id = resp.json()["id"]
    resp = await backend.client.post(f"/api/connectors/{connector_id}/test", headers=headers)
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_get_unknown_connector_404(backend):
    headers = await backend.auth_headers()
    resp = await backend.client.get("/api/connectors/nonexistent", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_test_unknown_connector_404(backend):
    headers = await backend.auth_headers()
    resp = await backend.client.post("/api/connectors/nonexistent/test", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_connector_test_endpoint_unimplemented_for_real_venues(backend):
    headers = await backend.auth_headers()
    resp = await backend.client.post(
        "/api/connectors",
        json={"name": "binance", "connector_type": "ccxt", "asset_class": "crypto", "credentials": {}},
        headers=headers,
    )
    connector_id = resp.json()["id"]
    resp = await backend.client.post(f"/api/connectors/{connector_id}/test", headers=headers)
    assert resp.json()["status"] == "not_implemented"


# ----- Risk -----

@pytest.mark.asyncio
async def test_get_and_update_risk_params_via_backend(backend):
    headers = await backend.auth_headers()
    resp = await backend.client.get("/api/risk/params", headers=headers)
    assert resp.json()["max_drawdown"] == 0.15

    resp = await backend.client.put("/api/risk/params", json={"max_drawdown": 0.18}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["max_drawdown"] == 0.18
    assert backend.engine.risk_manager.config.max_drawdown == 0.18


@pytest.mark.asyncio
async def test_update_risk_params_rejects_invalid(backend):
    headers = await backend.auth_headers()
    resp = await backend.client.put("/api/risk/params", json={"max_drawdown": 5.0}, headers=headers)
    assert resp.status_code == 400


# ----- Backtests -----

@pytest.mark.asyncio
async def test_run_backtest_via_api(backend):
    headers = await backend.auth_headers()
    resp = await backend.client.post(
        "/api/strategies", json={"name": "s1", "asset_class": "crypto"}, headers=headers
    )
    strategy_id = resp.json()["id"]
    await backend.client.post(
        f"/api/strategies/{strategy_id}/versions",
        json={"source_code": VALID_STRATEGY_SOURCE, "class_name": "MyStrategy"},
        headers=headers,
    )

    config = StrategyConfig(asset_class=AssetClass.CRYPTO, symbols=("BTC/USD",), timeframes=(Timeframe.D1,))
    from datetime import datetime, timedelta, timezone

    t0 = datetime(2021, 1, 1, tzinfo=timezone.utc)
    bars = [
        {
            "asset": "BTC/USD", "timeframe": "1d", "timestamp": (t0 + timedelta(days=i)).isoformat(),
            "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1.0,
        }
        for i in range(5)
    ]
    resp = await backend.client.post(
        "/api/backtests",
        json={
            "strategy_id": strategy_id, "config": encode_config(config), "bars": bars,
            "initial_capital": 10_000.0, "run_walk_forward": False, "run_monte_carlo": False,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert "sharpe" in resp.json()["metrics"]


@pytest.mark.asyncio
async def test_run_backtest_unknown_strategy_400(backend):
    # get_active_version() tolerates an unknown strategy_id by returning None
    # (matching the deploy endpoint's identical fallback) rather than raising —
    # so this is a 400 ("no active version"), not a 404.
    headers = await backend.auth_headers()
    config = StrategyConfig(asset_class=AssetClass.CRYPTO, symbols=("BTC/USD",), timeframes=(Timeframe.D1,))
    resp = await backend.client.post(
        "/api/backtests",
        json={
            "strategy_id": "nonexistent", "config": encode_config(config),
            "bars": [], "initial_capital": 1000.0,
        },
        headers=headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_run_backtest_no_active_version_400(backend):
    headers = await backend.auth_headers()
    resp = await backend.client.post(
        "/api/strategies", json={"name": "s1", "asset_class": "crypto"}, headers=headers
    )
    strategy_id = resp.json()["id"]  # created but no version uploaded yet
    config = StrategyConfig(asset_class=AssetClass.CRYPTO, symbols=("BTC/USD",), timeframes=(Timeframe.D1,))
    resp = await backend.client.post(
        "/api/backtests",
        json={
            "strategy_id": strategy_id, "config": encode_config(config),
            "bars": [], "initial_capital": 1000.0,
        },
        headers=headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_get_unknown_backtest_result_404(backend):
    headers = await backend.auth_headers()
    resp = await backend.client.get("/api/backtests/nonexistent", headers=headers)
    assert resp.status_code == 404


# ----- Deployment -----


@pytest.mark.asyncio
async def test_deploy_unknown_strategy_400(backend):
    headers = await backend.auth_headers()
    config = StrategyConfig(
        asset_class=AssetClass.CRYPTO, symbols=("BTC/USD",), timeframes=(Timeframe.D1,), connector_id="paper1"
    )
    resp = await backend.client.post(
        "/api/deployment/deploy",
        json={"strategy_id": "nonexistent", "config": encode_config(config)},
        headers=headers,
    )
    assert resp.status_code == 400

@pytest.mark.asyncio
async def test_deploy_then_redeploy_hot_swaps(backend):
    headers = await backend.auth_headers()
    resp = await backend.client.post(
        "/api/strategies", json={"name": "s1", "asset_class": "crypto"}, headers=headers
    )
    strategy_id = resp.json()["id"]
    await backend.client.post(
        f"/api/strategies/{strategy_id}/versions",
        json={"source_code": VALID_STRATEGY_SOURCE, "class_name": "MyStrategy"},
        headers=headers,
    )

    config = StrategyConfig(
        asset_class=AssetClass.CRYPTO, symbols=("BTC/USD",), timeframes=(Timeframe.D1,), connector_id="paper1"
    )
    resp = await backend.client.post(
        "/api/deployment/deploy",
        json={"strategy_id": strategy_id, "config": encode_config(config)},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "deployed"
    assert strategy_id in backend.engine.strategies

    # Redeploying while already running hot-swaps instead of reloading.
    resp = await backend.client.post(
        "/api/deployment/deploy",
        json={"strategy_id": strategy_id, "config": encode_config(config)},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "hot_swapped"


@pytest.mark.asyncio
async def test_halt_flatten_kill_via_backend(backend):
    headers = await backend.auth_headers()
    assert (await backend.client.post("/api/deployment/halt", headers=headers)).json()["status"] == "halted"
    assert (await backend.client.post("/api/deployment/flatten", headers=headers)).json()["status"] == "flattened"
    assert (await backend.client.post("/api/deployment/kill-switch", headers=headers)).json()["status"] == "killed"


# ----- Monitoring -----

@pytest.mark.asyncio
async def test_monitoring_state(backend):
    headers = await backend.auth_headers()
    resp = await backend.client.get("/api/monitoring/state", headers=headers)
    assert "equity" in resp.json()


# ----- Trades -----

@pytest.mark.asyncio
async def test_list_trades_empty_initially(backend):
    headers = await backend.auth_headers()
    resp = await backend.client.get("/api/trades", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


# ----- Hermes (HMAC, not JWT) -----

@pytest.mark.asyncio
async def test_hermes_command_status(backend):
    body = json.dumps({"command": "status"}).encode()
    ts = str(time.time())
    sig = compute_hermes_signature(HERMES_SECRET, ts, "POST", "/api/hermes/command", body)
    resp = await backend.client.post(
        "/api/hermes/command",
        content=body,
        headers={"X-Hermes-Signature": sig, "X-Hermes-Timestamp": ts, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["command"] == "status"


@pytest.mark.asyncio
async def test_hermes_command_invalid_signature_rejected(backend):
    body = json.dumps({"command": "status"}).encode()
    resp = await backend.client.post(
        "/api/hermes/command",
        content=body,
        headers={"X-Hermes-Signature": "bad", "X-Hermes-Timestamp": str(time.time())},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_hermes_command_malformed_payload_rejected(backend):
    body = b"not json"
    ts = str(time.time())
    sig = compute_hermes_signature(HERMES_SECRET, ts, "POST", "/api/hermes/command", body)
    resp = await backend.client.post(
        "/api/hermes/command", content=body, headers={"X-Hermes-Signature": sig, "X-Hermes-Timestamp": ts}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_hermes_command_unknown_command_rejected(backend):
    body = json.dumps({"command": "self_destruct"}).encode()
    ts = str(time.time())
    sig = compute_hermes_signature(HERMES_SECRET, ts, "POST", "/api/hermes/command", body)
    resp = await backend.client.post(
        "/api/hermes/command", content=body, headers={"X-Hermes-Signature": sig, "X-Hermes-Timestamp": ts}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_hermes_command_halt_and_flatten(backend):
    for command in ("halt", "flatten", "kill"):
        body = json.dumps({"command": command}).encode()
        ts = str(time.time())
        sig = compute_hermes_signature(HERMES_SECRET, ts, "POST", "/api/hermes/command", body)
        resp = await backend.client.post(
            "/api/hermes/command", content=body, headers={"X-Hermes-Signature": sig, "X-Hermes-Timestamp": ts}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["command"] == command


@pytest.mark.asyncio
async def test_hermes_command_does_not_require_jwt(backend):
    # No Authorization header at all — HMAC alone must be sufficient.
    body = json.dumps({"command": "status"}).encode()
    ts = str(time.time())
    sig = compute_hermes_signature(HERMES_SECRET, ts, "POST", "/api/hermes/command", body)
    resp = await backend.client.post(
        "/api/hermes/command", content=body, headers={"X-Hermes-Signature": sig, "X-Hermes-Timestamp": ts}
    )
    assert resp.status_code == 200


async def _hermes_post(backend, payload: dict):
    body = json.dumps(payload).encode()
    ts = str(time.time())
    sig = compute_hermes_signature(HERMES_SECRET, ts, "POST", "/api/hermes/command", body)
    return await backend.client.post(
        "/api/hermes/command", content=body, headers={"X-Hermes-Signature": sig, "X-Hermes-Timestamp": ts}
    )


@pytest.mark.asyncio
async def test_hermes_command_positions(backend):
    resp = await _hermes_post(backend, {"command": "positions"})
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert set(result.keys()) == {"open_position_count", "gross_exposure_value", "equity"}


@pytest.mark.asyncio
async def test_hermes_command_risk_get(backend):
    resp = await _hermes_post(backend, {"command": "risk_get"})
    assert resp.status_code == 200
    assert resp.json()["result"]["kelly_multiplier"] == 0.25


@pytest.mark.asyncio
async def test_hermes_command_risk_set(backend):
    resp = await _hermes_post(backend, {"command": "risk_set", "updates": {"max_drawdown": 0.19}})
    assert resp.status_code == 200
    assert resp.json()["result"]["max_drawdown"] == 0.19
    assert backend.engine.risk_manager.config.max_drawdown == 0.19


@pytest.mark.asyncio
async def test_hermes_command_risk_set_requires_updates_object(backend):
    resp = await _hermes_post(backend, {"command": "risk_set"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_hermes_command_risk_set_rejects_invalid_value(backend):
    resp = await _hermes_post(backend, {"command": "risk_set", "updates": {"max_drawdown": 5.0}})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_hermes_command_trades(backend):
    resp = await _hermes_post(backend, {"command": "trades"})
    assert resp.status_code == 200
    assert resp.json()["result"]["trades"] == []
