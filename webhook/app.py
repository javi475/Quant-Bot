"""TradingView webhook receiver (DOC 2 §4, :8080). A separate FastAPI process
from the Engine — it only ever writes to Redis's `engine:signal_queue`; the
Engine's SignalScheduler is what actually drains it (DOC 2 architecture:
"execution-control separation" applies here too — this receiver can be
restarted independently without affecting a running Engine).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from common.enums import Direction
from common.redis_keys import SIGNAL_QUEUE
from engine.strategy.serialization import encode_signal
from sdk.ate_smp.models.signal import Signal
from webhook.security import verify_signature

DEFAULT_SIGNATURE_HEADER = "X-TV-Signature"


def create_app(
    redis_client: Any, webhook_secret: str, signature_header: str = DEFAULT_SIGNATURE_HEADER
) -> FastAPI:
    app = FastAPI(title="ATE-SMP TradingView Webhook Receiver")

    @app.post("/webhook/tradingview")
    async def tradingview_webhook(request: Request):
        body = await request.body()
        signature = request.headers.get(signature_header, "")
        if not verify_signature(webhook_secret, body, signature):
            raise HTTPException(status_code=401, detail="invalid or missing signature")

        try:
            payload = json.loads(body)
            strategy_id = str(payload["strategy_id"])
            asset = str(payload["asset"])
            direction = Direction(payload["direction"])
            strength = float(payload.get("strength", 1.0))
            metadata = payload.get("metadata", {})
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=f"malformed alert payload: {exc}") from exc

        try:
            signal = Signal(
                timestamp=datetime.now(timezone.utc),
                asset=asset,
                direction=direction,
                strength=strength,
                metadata=metadata,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        envelope = json.dumps({"strategy_id": strategy_id, "signal": encode_signal(signal)})
        await redis_client.rpush(SIGNAL_QUEUE, envelope)

        return {"status": "queued", "strategy_id": strategy_id, "asset": asset, "direction": direction.value}

    @app.get("/webhook/tradingview/schema")
    async def schema():
        return {
            "strategy_id": "string, required — must match a strategy_id loaded in the Engine",
            "asset": "string, required — connector-native symbol format",
            "direction": [d.value for d in Direction],
            "strength": "float in [0.0, 1.0], optional (default 1.0)",
            "metadata": "object, optional",
        }

    return app
