"""
API server for the Aegis Mini App dashboard.

Can run in two very different shapes:

* **Alongside the bot** - ``API_SERVER_ENABLED=true`` starts it on a background
  thread from ``app.main`` / ``wsgi.py``; one process, one .env.
* **On its own host or account** - ``python -m app.api.server`` behind a TLS
  proxy. It then needs the *same* ``BOT_TOKEN`` (to verify Mini App signatures)
  and the *same* ``DATABASE_URL`` (to read/write the groups the bot manages).

Routes:
    GET  /health        liveness probe (no auth)
    GET  /miniapp       the dashboard page
    GET  /              landing page (landing/dist/index.html, if it exists)
    GET  /assets/...    landing page static assets (if landing/dist/ exists)
    *    /api/v1/...    dashboard API (initData + group-admin auth required)
"""
import logging
import mimetypes
import threading
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

from app.api.auth import set_bot_token
from app.api.dashboard import app as dashboard_app
from app.config.settings import settings

logger = logging.getLogger(__name__)

# Absolute path: the API may be started from any working directory (systemd,
# Alembic, a second account's home dir), so never rely on the CWD.
MINIAPP_DIR = Path(__file__).resolve().parent.parent / "miniapp"
_MINAPP_INDEX = MINIAPP_DIR / "index.html"
_API_BASE_PLACEHOLDER = "__AEGIS_API_BASE__"

# Landing page (marketing site) lives in landing/dist/.  Serve it at / and its
# assets at /assets/ so the root domain shows the product site, not a blank page.
LANDING_DIR = Path(__file__).resolve().parent.parent / "landing" / "dist"
_LANDING_INDEX = LANDING_DIR / "index.html"


api_app = FastAPI(title="Aegis API Server", version="1.0.0")


# Only needed when the page and the API are on different origins.
if settings.API_CORS_ORIGINS:
    api_app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.API_CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Telegram-Init-Data", "Authorization"],
    )

set_bot_token(settings.BOT_TOKEN)
if not settings.BOT_TOKEN or settings.BOT_TOKEN in ("dummy_token", "123456:REPLACE_ME"):
    logger.warning(
        "BOT_TOKEN is a placeholder: Mini App requests cannot be verified and "
        "will be rejected. Set the real token or MINIAPP_AUTH_DISABLED=true "
        "for local development only."
    )


@api_app.get("/health")
async def health():
    """Liveness probe."""
    return {"status": "ok", "version": "1.0.0", "service": "aegis-api"}


def _render_miniapp() -> str:
    """Serve the dashboard page, telling it where the API lives."""
    html = _MINAPP_INDEX.read_text(encoding="utf-8")
    return html.replace(_API_BASE_PLACEHOLDER, settings.MINIAPP_API_BASE.rstrip("/"))


@api_app.get("/miniapp", response_class=HTMLResponse)
async def serve_miniapp():
    """Dashboard page (opened by /dashboard or BotFather's Mini App button)."""
    if not _MINAPP_INDEX.exists():
        return HTMLResponse("<h1>Mini App not found</h1>", status_code=404)
    return HTMLResponse(_render_miniapp())


@api_app.get("/miniapp/{asset_path:path}")
async def serve_miniapp_asset(asset_path: str):
    """Static assets next to index.html (css/js/icons), path-traversal safe."""
    target = (MINIAPP_DIR / asset_path).resolve()
    if MINIAPP_DIR.resolve() not in target.parents and target != MINIAPP_DIR.resolve():
        return HTMLResponse("Not found", status_code=404)
    if not target.is_file():
        return HTMLResponse("Not found", status_code=404)
    media_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    return FileResponse(target, media_type=media_type)


# ── Landing page routes (must be registered BEFORE the dashboard mount) ───────
# Starlette matches routes in registration order, so these must be defined
# before ``api_app.mount("/", dashboard_app)`` below, otherwise the mount's
# sub-app would intercept requests to ``/`` and ``/assets/...`` first.
if _LANDING_INDEX.exists():
    @api_app.get("/")
    async def serve_landing() -> HTMLResponse:
        """Serve the landing page (landing/dist/index.html) at the root path."""
        try:
            return HTMLResponse(_LANDING_INDEX.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Could not read landing page: {e}")
            return HTMLResponse(
                "<h1>Landing page unavailable</h1><p>Please try again later.</p>",
                status_code=503,
            )

    @api_app.get("/assets/{asset_path:path}")
    async def serve_landing_asset(asset_path: str) -> FileResponse | HTMLResponse:
        """Serve static assets from landing/dist/ (css/js/images/fonts/icons)."""
        if not asset_path or asset_path == "favicon.ico":
            return HTMLResponse("Not found", status_code=404)
        target = (LANDING_DIR / asset_path).resolve()
        # Prevent path-traversal escapes outside landing/dist/
        if LANDING_DIR.resolve() not in target.parents and target != LANDING_DIR.resolve():
            return HTMLResponse("Not found", status_code=404)
        if not target.is_file():
            return HTMLResponse("Not found", status_code=404)
        media_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        return FileResponse(target, media_type=media_type)

# Mounted last on purpose: Starlette matches routes in registration order, so
# /health, /miniapp, /assets/* and / above keep winning while /api/v1/* reaches
# the dashboard.  The root path ``/`` serves the landing page from
# ``landing/dist/index.html`` when it exists; otherwise the dashboard app's own
# routes handle it.
api_app.mount("/", dashboard_app)

_server = None


def run_api_server(host: Optional[str] = None, port: Optional[int] = None) -> None:
    """Blocking entry point (``python -m app.api.server``)."""
    import uvicorn

    uvicorn.run(
        api_app,
        host=host or settings.API_HOST,
        port=port or settings.API_PORT,
        log_level=settings.LOG_LEVEL.lower(),
    )


def start_api_server_thread(
    host: Optional[str] = None, port: Optional[int] = None
) -> threading.Thread:
    """Start the API on a daemon thread (single-process deployments)."""
    import uvicorn

    global _server
    _server = uvicorn.Server(
        uvicorn.Config(
            api_app,
            host=host or settings.API_HOST,
            port=port or settings.API_PORT,
            log_level=settings.LOG_LEVEL.lower(),
        )
    )
    thread = threading.Thread(target=_server.run, name="aegis-api", daemon=True)
    thread.start()
    logger.info(
        "API server listening on http://%s:%s (Mini App at /miniapp)",
        host or settings.API_HOST,
        port or settings.API_PORT,
    )
    return thread


def stop_api_server() -> None:
    """Ask a thread-started API server to shut down."""
    if _server is not None:
        _server.should_exit = True


if __name__ == "__main__":
    run_api_server()
