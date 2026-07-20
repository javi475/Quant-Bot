"""Structured JSON logging setup shared by engine, backend, webhook, watchdog
(DOC 2 §8: engine.log, strategy.log, connector.log, dashboard.log, watchdog.log,
hermes.log, and the immutable decision_audit.jsonl)."""

from __future__ import annotations

import logging
import os
import sys

import structlog

LOG_DIR = os.environ.get("LOG_DIR", "/var/log/ate-smp")


def configure_logging(service_name: str, level: int = logging.INFO) -> structlog.BoundLogger:
    """Configure structlog to emit JSON lines to stdout (captured by Docker/systemd)
    tagged with `service`. Call once per process at startup."""

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )
    return structlog.get_logger(service=service_name)


def decision_audit_path() -> str:
    """Path to the immutable, append-only trade-decision audit trail
    (7-year retention per DOC 2 §8)."""
    return os.path.join(LOG_DIR, "decision_audit.jsonl")
