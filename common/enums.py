"""Shared enums used across the SDK, engine, and backend (DOC 2 §2, DOC 3 §1-2)."""

from __future__ import annotations

from enum import Enum


class AssetClass(str, Enum):
    CRYPTO = "crypto"
    FUTURES = "futures"
    OPTIONS = "options"
    FOREX = "forex"
    STOCKS = "stocks"
    PREDICTION_MARKETS = "prediction_markets"


class Timeframe(str, Enum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"
    EXIT_LONG = "exit_long"
    EXIT_SHORT = "exit_short"
    FLATTEN = "flatten"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class TimeInForce(str, Enum):
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"
    DAY = "day"


class OrderStatus(str, Enum):
    PENDING = "pending"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class ParameterType(str, Enum):
    FLOAT = "float"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    STRING = "string"
    ENUM = "enum"
    LIST_FLOAT = "list_float"
    LIST_STRING = "list_string"


class StrategyLifecycleState(str, Enum):
    UPLOADED = "uploaded"
    LOADING = "loading"
    READY = "ready"
    DISABLED = "disabled"
    RUNNING = "running"
    SWAPPING = "swapping"
    STOPPED = "stopped"
    ERROR = "error"


class DeploymentMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class LaunchPhase(str, Enum):
    PAPER = "paper"
    SMALL = "small"
    HALF = "half"
    FULL = "full"


class RiskEventType(str, Enum):
    DAILY_LOSS_BREAKER = "daily_loss_breaker"
    DRAWDOWN_CEILING = "drawdown_ceiling"
    DEAD_MAN_SWITCH = "dead_man_switch"
    MAX_LOSS_STOP = "max_loss_stop"
    CORRELATION_REJECTION = "correlation_rejection"
    EXPOSURE_REJECTION = "exposure_rejection"
    POSITION_LIMIT_REJECTION = "position_limit_rejection"
    SAFE_MODE_ACTIVATED = "safe_mode_activated"
    SAFE_MODE_EXPIRED = "safe_mode_expired"
    RECOVERY_STARTED = "recovery_started"
    RECOVERY_COMPLETED = "recovery_completed"
    DRAWDOWN_ALERT_1 = "drawdown_alert_1"
    DRAWDOWN_ALERT_2 = "drawdown_alert_2"
    DRAWDOWN_ALERT_3 = "drawdown_alert_3"
    PROP_FIRM_RULE_WARNING = "prop_firm_rule_warning"
    PROP_FIRM_RULE_VIOLATION = "prop_firm_rule_violation"
    MANUAL_FLATTEN = "manual_flatten"
    MANUAL_HALT = "manual_halt"
    KILL_SWITCH = "kill_switch"


class RiskEventSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    SERIOUS = "serious"
    CRITICAL = "critical"
