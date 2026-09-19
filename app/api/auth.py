"""Telegram Mini App authentication.

A dashboard request has to clear two independent gates before it can read or
write group data:

1. **Signature** - Telegram signs ``initData`` with a key derived from the bot
   token, so only a Mini App launched from *this* bot can produce a valid blob.
   ``auth_date`` freshness is checked too, which stops a captured payload from
   being replayed later.
2. **Authorisation** - the signed user must really be an admin/owner of the
   group named in the URL path. That is verified live through the Bot API
   (cached briefly), because group roles change all the time.

The dashboard API mounts :func:`authorize_miniapp_request` as an app-wide
dependency, so every endpoint - including ones added later - is protected.
"""
import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict, Optional
from urllib.parse import parse_qs

import httpx
from fastapi import HTTPException, Request

from app.config.settings import settings

logger = logging.getLogger(__name__)

_TELEGRAM_API = "https://api.telegram.org"
_ADMIN_CACHE_TTL = 300  # seconds a getChatMember answer is trusted
_admin_cache: Dict[tuple, tuple] = {}

BOT_TOKEN: Optional[str] = None


class AuthError(HTTPException):
    """initData is missing, malformed, forged, stale - or the caller is not an admin."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(status_code=status_code, detail=detail)


def set_bot_token(token: str) -> None:
    """Hand the validator the same bot token the bot uses (needed for the HMAC)."""
    global BOT_TOKEN
    BOT_TOKEN = token or None


def reset_admin_cache() -> None:
    """Drop cached getChatMember answers (used by tests and role changes)."""
    _admin_cache.clear()


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _load_json(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def verify_init_data(init_data: str, max_age: Optional[int] = None) -> Dict[str, Any]:
    """
    Validate a Mini App ``initData`` query string and return the identity in it.

    Implements Telegram's documented Mini App algorithm::

        secret_key = HMAC_SHA256(key="WebAppData", msg=bot_token)
        hash       = HMAC_SHA256(key=secret_key, msg=data_check_string)

    Raises :class:`AuthError` for anything that does not verify.
    """
    if not init_data:
        raise AuthError(401, "Missing initData")
    if not BOT_TOKEN:
        raise AuthError(500, "Bot token not configured on the API server")

    # keep_blank_values matters: dropping empty fields changes the check string.
    parsed = parse_qs(init_data, keep_blank_values=True)
    fields = {k: v[0] for k, v in parsed.items()}

    signature = fields.get("hash", "")
    if not signature:
        raise AuthError(401, "initData has no hash")

    check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(fields.items()) if key != "hash"
    )
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise AuthError(401, "initData signature does not match")

    window = settings.MINIAPP_AUTH_MAX_AGE if max_age is None else max_age
    auth_date = _to_int(fields.get("auth_date"))
    if window and auth_date and (time.time() - auth_date) > window:
        raise AuthError(401, "initData has expired - reopen the dashboard")

    user = _load_json(fields.get("user"))
    chat = _load_json(fields.get("chat"))
    return {
        "user": {
            "id": _to_int(user.get("id")) or _to_int(fields.get("id")),
            "first_name": user.get("first_name") or fields.get("first_name", ""),
            "last_name": user.get("last_name", ""),
            "username": user.get("username") or fields.get("username", ""),
            "language_code": user.get("language_code") or fields.get("language_code", "en"),
        },
        "chat": {
            "id": _to_int(chat.get("id")),
            "title": chat.get("title", ""),
            "type": chat.get("type", ""),
            "username": chat.get("username", ""),
        },
        "auth_date": auth_date,
        "start_param": fields.get("start_param", ""),
        "query_id": fields.get("query_id", ""),
    }


async def is_chat_admin(chat_id: int, user_id: Optional[int]) -> bool:
    """True when ``user_id`` is an admin/owner of ``chat_id`` (Bot API, cached)."""
    if user_id is not None and user_id in (settings.SUPER_ADMIN_IDS or []):
        return True
    if not chat_id or user_id is None:
        return False

    key = (chat_id, user_id)
    now = time.time()
    cached = _admin_cache.get(key)
    if cached and cached[0] > now:
        return cached[1]

    if not BOT_TOKEN:
        raise AuthError(500, "Bot token not configured on the API server")

    url = f"{_TELEGRAM_API}/bot{BOT_TOKEN}/getChatMember"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                url, json={"chat_id": chat_id, "user_id": user_id}
            )
        payload = response.json()
    except Exception as exc:  # network hiccup, bad JSON, timeout
        logger.warning("getChatMember call failed for chat %s: %s", chat_id, exc)
        raise AuthError(503, "Could not verify group membership right now") from exc

    if not payload.get("ok"):
        # Unknown group, bot removed, or bad request - treat as "not an admin".
        logger.info(
            "getChatMember rejected chat %s: %s", chat_id, payload.get("description")
        )
        _admin_cache[key] = (now + _ADMIN_CACHE_TTL, False)
        return False

    status = (payload.get("result") or {}).get("status", "")
    allowed = status in ("creator", "administrator")
    _admin_cache[key] = (now + _ADMIN_CACHE_TTL, allowed)
    return allowed


def _init_data_from_request(request: Request) -> str:
    """Accept the Mini App header first, then a bearer token fallback."""
    header = request.headers.get("X-Telegram-Init-Data")
    if header:
        return header
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


async def authorize_miniapp_request(request: Request) -> Dict[str, Any]:
    """
    FastAPI dependency applied to every dashboard route.

    Verifies the initData signature and, when the path names a group, that the
    signed user is an admin of that group.
    """
    # Uptime probes must work without a Mini App session.
    if request.url.path.rstrip("/").endswith("/health"):
        return {}

    if settings.MINIAPP_AUTH_DISABLED:
        logger.warning(
            "MINIAPP_AUTH_DISABLED=true - dashboard API is unauthenticated (%s)",
            request.url.path,
        )
        return {"user": {"id": None}, "chat": {"id": None}, "auth_disabled": True}

    identity = verify_init_data(_init_data_from_request(request))

    chat_id = _to_int(request.path_params.get("telegram_id"))
    if chat_id:
        user_id = identity["user"]["id"]
        if not await is_chat_admin(chat_id, user_id):
            raise AuthError(403, "You are not an admin in this group")

    request.state.tg_identity = identity
    return identity
