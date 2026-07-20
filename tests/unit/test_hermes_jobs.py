from datetime import datetime, timezone

import fakeredis
import pytest

from hermes import jobs
from hermes.memory import PersistentMemory

NOW = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)


class FakeHermesClient:
    def __init__(self, status=None, positions=None, trades=None):
        self._status = status or {}
        self._positions = positions or {}
        self._trades = trades or {"trades": []}

    async def status(self):
        return self._status

    async def positions(self):
        return self._positions

    async def trades(self, strategy_id=None):
        return self._trades


class RecordingAlertSink:
    def __init__(self):
        self.sent = []

    async def send(self, message, priority="critical"):
        self.sent.append((message, priority))


@pytest.fixture
def memory():
    return PersistentMemory(fakeredis.FakeAsyncRedis(decode_responses=True))


@pytest.mark.asyncio
async def test_health_check_records_metrics_and_no_alert_when_running(memory):
    client = FakeHermesClient(status={"equity": 100_000.0, "halted": False, "safe_mode": {"active": False}})
    sink = RecordingAlertSink()

    await jobs.health_check(NOW, client, memory, sink)

    history = await memory.get_json("hermes:system_metrics_history")
    assert history[0]["equity"] == 100_000.0
    assert sink.sent == []


@pytest.mark.asyncio
async def test_health_check_alerts_when_halted(memory):
    client = FakeHermesClient(status={"equity": 100_000.0, "halted": True, "safe_mode": {"active": False}})
    sink = RecordingAlertSink()

    await jobs.health_check(NOW, client, memory, sink)

    assert len(sink.sent) == 1
    message, priority = sink.sent[0]
    assert "HALTED" in message
    assert priority == "warning"


@pytest.mark.asyncio
async def test_position_reconciliation_no_alert_on_first_run(memory):
    client = FakeHermesClient(positions={"equity": 100_000.0})
    sink = RecordingAlertSink()

    await jobs.position_reconciliation(NOW, client, memory, sink)

    assert sink.sent == []
    snapshot = await memory.get_json(jobs.LAST_EQUITY_SNAPSHOT_KEY)
    assert snapshot["equity"] == 100_000.0


@pytest.mark.asyncio
async def test_position_reconciliation_warns_on_moderate_swing(memory):
    await memory.set_json(jobs.LAST_EQUITY_SNAPSHOT_KEY, {"equity": 100_000.0, "timestamp": NOW.isoformat()})
    client = FakeHermesClient(positions={"equity": 94_000.0})  # -6%
    sink = RecordingAlertSink()

    await jobs.position_reconciliation(NOW, client, memory, sink)

    assert len(sink.sent) == 1
    message, priority = sink.sent[0]
    assert priority == "warning"
    assert "-6.0%" in message


@pytest.mark.asyncio
async def test_position_reconciliation_serious_on_large_swing(memory):
    await memory.set_json(jobs.LAST_EQUITY_SNAPSHOT_KEY, {"equity": 100_000.0, "timestamp": NOW.isoformat()})
    client = FakeHermesClient(positions={"equity": 85_000.0})  # -15%
    sink = RecordingAlertSink()

    await jobs.position_reconciliation(NOW, client, memory, sink)

    assert len(sink.sent) == 1
    _, priority = sink.sent[0]
    assert priority == "serious"


@pytest.mark.asyncio
async def test_position_reconciliation_no_alert_on_small_swing(memory):
    await memory.set_json(jobs.LAST_EQUITY_SNAPSHOT_KEY, {"equity": 100_000.0, "timestamp": NOW.isoformat()})
    client = FakeHermesClient(positions={"equity": 101_000.0})  # +1%
    sink = RecordingAlertSink()

    await jobs.position_reconciliation(NOW, client, memory, sink)

    assert sink.sent == []


@pytest.mark.asyncio
async def test_safe_mode_check_clears_alert_when_inactive(memory):
    await memory.mark_safe_mode_alerted("daily_loss_breaker", "entry_block")
    client = FakeHermesClient(status={"safe_mode": {"active": False}})
    sink = RecordingAlertSink()

    await jobs.safe_mode_check(NOW, client, memory, sink)

    assert sink.sent == []
    assert not await memory.has_alerted_safe_mode("daily_loss_breaker", "entry_block")


@pytest.mark.asyncio
async def test_safe_mode_check_alerts_once_per_episode(memory):
    client = FakeHermesClient(
        status={"safe_mode": {"active": True, "triggered_by": "daily_loss_breaker", "phase": "entry_block"}}
    )
    sink = RecordingAlertSink()

    await jobs.safe_mode_check(NOW, client, memory, sink)
    await jobs.safe_mode_check(NOW, client, memory, sink)

    assert len(sink.sent) == 1
    _, priority = sink.sent[0]
    assert priority == "serious"


@pytest.mark.asyncio
async def test_daily_report_summarizes_status_and_trades(memory):
    client = FakeHermesClient(
        status={"equity": 100_000.0, "open_position_count": 2, "safe_mode": {"active": False}, "halted": False},
        trades={"trades": [{"is_closed": True, "pnl": 150.0}, {"is_closed": False, "pnl": None}]},
    )
    sink = RecordingAlertSink()

    await jobs.daily_report(NOW, client, memory, sink)

    assert len(sink.sent) == 1
    message, priority = sink.sent[0]
    assert priority == "info"
    assert "Closed trades: 1, total P&L $150.00" in message


@pytest.mark.asyncio
async def test_midday_status_sends_summary(memory):
    client = FakeHermesClient(status={"equity": 50_000.0, "open_position_count": 1, "safe_mode": {"active": False}})
    sink = RecordingAlertSink()

    await jobs.midday_status(NOW, client, memory, sink)

    assert len(sink.sent) == 1
    _, priority = sink.sent[0]
    assert priority == "info"


@pytest.mark.parametrize(
    "stub_job",
    [
        jobs.weekly_backtest,
        jobs.self_improvement_proposal,
        jobs.phase_gate_check,
        jobs.monthly_report,
        jobs.log_rotation_check,
        jobs.daily_pnl_reset,
        jobs.weekly_backup_verify,
    ],
)
@pytest.mark.asyncio
async def test_stub_jobs_do_not_alert_and_do_not_raise(memory, stub_job):
    client = FakeHermesClient()
    sink = RecordingAlertSink()

    await stub_job(NOW, client, memory, sink)

    assert sink.sent == []


def test_build_default_jobs_registers_all_twelve():
    client = FakeHermesClient()
    memory = PersistentMemory(fakeredis.FakeAsyncRedis(decode_responses=True))
    sink = RecordingAlertSink()

    job_list = jobs.build_default_jobs(client, memory, sink)

    names = {job.name for job in job_list}
    assert names == {
        "health_check",
        "daily_report",
        "weekly_backtest",
        "self_improvement_proposal",
        "phase_gate_check",
        "monthly_report",
        "position_reconciliation",
        "log_rotation_check",
        "daily_pnl_reset",
        "midday_status",
        "weekly_backup_verify",
        "safe_mode_check",
    }
