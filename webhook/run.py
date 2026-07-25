"""Production entry point for the TradingView webhook receiver (DOC 2 §4, :8080).

Reads WEBHOOK_SECRET from the dashboard backend's settings (or falls back to
an env-var default for standalone deployment), then starts uvicorn.

Usage:
    python -m webhook.run
    python -m webhook.run --reload
    python -m webhook.run --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import argparse
import os

import redis.asyncio as redis_asyncio
import uvicorn

from webhook.app import create_app

DEFAULT_REDIS_URL = "redis://localhost:6379/0"
DEFAULT_WEBHOOK_SECRET = "ate-smp-webhook-secret-change-in-production"


def build_app() -> "FastAPI":
    from fastapi import FastAPI

    webhook_secret = os.environ.get("WEBHOOK_SECRET", DEFAULT_WEBHOOK_SECRET)
    redis_url = os.environ.get("REDIS_URL", DEFAULT_REDIS_URL)

    redis_client = redis_asyncio.from_url(redis_url, decode_responses=True)
    app = create_app(redis_client, webhook_secret)

    @app.on_event("shutdown")
    async def shutdown():
        await redis_client.close()

    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ATE-SMP TradingView Webhook Receiver")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=8080, help="Bind port")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    uvicorn.run(
        "webhook.run:build_app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        factory=True,
    )
