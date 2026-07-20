"""Redis key naming conventions (DOC 2 §2.8). Centralized so the Engine, Watchdog,
Backend, and Webhook receiver never drift on key names/TTLs.

Static keys are module-level constants; per-entity keys are template functions.
"""

from __future__ import annotations

# ----- Engine heartbeat / dead-man switch (DOC 4 §5) -----
HEARTBEAT_KEY = "engine:heartbeat"
HEARTBEAT_TTL_SECONDS = 15  # 3x the 5s write interval

# ----- Engine hot state (DOC 2 §2.8) -----
STATE_POSITIONS = "engine:state:positions"
STATE_PNL_DAILY = "engine:state:pnl:daily"
STATE_PNL_TOTAL = "engine:state:pnl:total"
STATE_EQUITY = "engine:state:equity"
STATE_DRAWDOWN = "engine:state:drawdown"
STATE_PEAK_EQUITY = "engine:state:peak_equity"
STATE_EXPOSURE_GROSS = "engine:state:exposure:gross"
STATE_SAFE_MODE = "engine:state:safe_mode"  # Hash, 48h TTL while active
SAFE_MODE_TTL_SECONDS = 48 * 3600

# ----- Queues (Lists) -----
SIGNAL_QUEUE = "engine:signal_queue"
ORDER_QUEUE = "engine:order_queue"
FILL_QUEUE = "engine:fill_queue"
PENDING_RISK_EVENTS = "engine:pending_risk_events"

# ----- Pub/Sub -----
WS_PUBSUB_CHANNEL = "engine:ws:pubsub"

# ----- Per-entity templates -----
STRATEGY_STATE_TTL_SECONDS = 3600


def strategy_state_key(strategy_id: str) -> str:
    return f"strategy:{strategy_id}:state"


CONNECTOR_STATUS_TTL_SECONDS = 30


def connector_status_key(connector_id: str) -> str:
    return f"connector:{connector_id}:status"
