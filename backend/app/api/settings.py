"""DOC 2 §6 /api/settings: Telegram alert configuration endpoints.

Settings are stored in-memory on app.state — since the dashboard backend
does not currently use a database, this matches the same approach used by
other services (connector_registry, strategy_registry, etc.). A future
milestone could persist them to Redis or a config file.

The "test" endpoint sends a real test message via Telegram's Bot API so the
user can validate bot_token + chat_id before saving."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.app.auth.dependencies import get_current_subject

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(get_current_subject)])

DEFAULT_TELEGRAM_SETTINGS = {
    "bot_token": "",
    "chat_id": "",
    "alert_priority": "info",
}

DEFAULT_WEBHOOK_SETTINGS = {
    "webhook_secret": "",
    "webhook_url": "",
}


class TelegramSettingsRequest(BaseModel):
    bot_token: str = ""
    chat_id: str = ""
    alert_priority: str = "info"


def _get_telegram_settings(request: Request) -> dict:
    """Return current telegram settings, initialising with defaults if needed."""
    if not hasattr(request.app.state, "telegram_settings"):
        request.app.state.telegram_settings = dict(DEFAULT_TELEGRAM_SETTINGS)
    return request.app.state.telegram_settings


@router.get("/telegram")
async def get_telegram_settings(request: Request) -> dict:
    settings = _get_telegram_settings(request)
    # Never expose the full bot_token back to the client — only the
    # last 4 characters so the user can recognise which token is set.
    token = settings["bot_token"]
    masked = f"…{token[-4:]}" if len(token) > 4 else ""
    return {
        "bot_token_masked": masked,
        "bot_token_set": bool(token),
        "chat_id": settings["chat_id"],
        "alert_priority": settings["alert_priority"],
    }


@router.put("/telegram")
async def update_telegram_settings(req: TelegramSettingsRequest, request: Request) -> dict:
    if req.alert_priority not in ("info", "warning", "serious", "critical"):
        raise HTTPException(status_code=400, detail=f"invalid priority: {req.alert_priority}")

    request.app.state.telegram_settings = {
        "bot_token": req.bot_token,
        "chat_id": req.chat_id,
        "alert_priority": req.alert_priority,
    }

    token = req.bot_token
    masked = f"…{token[-4:]}" if len(token) > 4 else ""
    return {
        "bot_token_masked": masked,
        "bot_token_set": bool(req.bot_token),
        "chat_id": req.chat_id,
        "alert_priority": req.alert_priority,
    }


@router.post("/telegram/test")
async def test_telegram_settings(request: Request) -> dict:
    settings = _get_telegram_settings(request)
    bot_token = settings.get("bot_token", "")
    chat_id = settings.get("chat_id", "")

    if not bot_token or not chat_id:
        raise HTTPException(status_code=400, detail="bot_token and chat_id must be set before testing")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": "🔧 *ATE-SMP Dashboard* — Telegram alerts configured successfully!"},
                headers={"Content-Type": "application/json"},
            )
            if response.status_code == 401:
                raise HTTPException(status_code=400, detail="invalid bot_token — Telegram rejected the request")
            if response.status_code == 400:
                body = response.json()
                raise HTTPException(
                    status_code=400,
                    detail=f"invalid chat_id — Telegram says: {body.get('description', 'unknown error')}",
                )
            response.raise_for_status()
    except httpx.TimeoutException:
        raise HTTPException(status_code=502, detail="Telegram API timed out — check your network")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Telegram API error: {exc}")

    return {"status": "ok", "detail": "test message sent successfully"}


class WebhookSettingsRequest(BaseModel):
    webhook_secret: str = ""
    webhook_url: str = ""


def _get_webhook_settings(request: Request) -> dict:
    """Return current webhook settings, initialising with defaults if needed."""
    if not hasattr(request.app.state, "webhook_settings"):
        request.app.state.webhook_settings = dict(DEFAULT_WEBHOOK_SETTINGS)
    return request.app.state.webhook_settings


@router.get("/webhook")
async def get_webhook_settings(request: Request) -> dict:
    settings = _get_webhook_settings(request)
    secret = settings["webhook_secret"]
    masked = f"…{secret[-4:]}" if len(secret) > 4 else ""
    return {
        "webhook_secret_masked": masked,
        "webhook_secret_set": bool(secret),
        "webhook_url": settings["webhook_url"],
    }


@router.put("/webhook")
async def update_webhook_settings(req: WebhookSettingsRequest, request: Request) -> dict:
    request.app.state.webhook_settings = {
        "webhook_secret": req.webhook_secret,
        "webhook_url": req.webhook_url,
    }
    secret = req.webhook_secret
    masked = f"…{secret[-4:]}" if len(secret) > 4 else ""
    return {
        "webhook_secret_masked": masked,
        "webhook_secret_set": bool(req.webhook_secret),
        "webhook_url": req.webhook_url,
    }


@router.post("/webhook/test")
async def test_webhook_settings(request: Request) -> dict:
    settings = _get_webhook_settings(request)
    webhook_secret = settings.get("webhook_secret", "")
    webhook_url = settings.get("webhook_url", "")

    if not webhook_secret or not webhook_url:
        raise HTTPException(status_code=400, detail="webhook_secret and webhook_url must be set before testing")

    # Compute a valid signature for a test payload, then send it to the
    # webhook receiver to verify the full round-trip works.
    from webhook.security import compute_signature

    test_payload = b'{"strategy_id":"test","asset":"TEST/USD","direction":"flatten","strength":0.0}'
    signature = compute_signature(webhook_secret, test_payload)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                webhook_url.rstrip("/") + "/webhook/tradingview",
                content=test_payload,
                headers={"X-TV-Signature": signature, "Content-Type": "application/json"},
            )
            if response.status_code == 401:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "webhook receiver rejected the signature — make sure WEBHOOK_SECRET "
                        "matches what the webhook receiver process was started with"
                    ),
                )
            response.raise_for_status()
    except httpx.TimeoutException:
        raise HTTPException(status_code=502, detail="webhook receiver timed out — check the URL and that the service is running")
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"could not reach webhook receiver at {webhook_url}: {exc}"
        )

    return {"status": "ok", "detail": "test signal sent and accepted by webhook receiver"}
