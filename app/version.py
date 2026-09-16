"""
version.py — Which build is running, and whether a newer one exists.

Self-hosted instances are upgraded by their owners, on their own schedule, so a
distributed fleet drifts: someone is always running last quarter's release
without knowing it. Two small facts fix that — the running version, and an
honest answer to "is there something newer?" — so this module owns both.

The update check is deliberately optional and offline-friendly:

* It only runs when ``UPDATE_CHECK_ENABLED`` is true, and only ever talks to the
  public GitHub releases API.
* It sends no group data, no member data and no instance identifier — a plain
  anonymous GET whose headers are all GitHub's own.
* Every failure (no network, rate limit, malformed response) is swallowed and
  reported as "unknown", because a self-hosted bot must never depend on reaching
  a third party in order to start.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Used only when neither installed metadata nor pyproject.toml can be read.
_FALLBACK_VERSION = "0.1.0"

# Where releases live. Overridable for forks via UPDATE_CHECK_REPO.
DEFAULT_REPO = "mrsehajofficial/aegis"

_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def get_version() -> str:
    """Return the version of the running build.

    Resolution order:
      1. Installed distribution metadata (``pip install .``, Docker image).
      2. ``pyproject.toml`` next to the package — the source-checkout case,
         which is how most self-hosters run Aegis.
      3. A hard-coded fallback, so this never raises.
    """
    try:
        from importlib.metadata import version as _dist_version

        return _dist_version("aegis")
    except Exception:
        pass
    try:
        pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
        match = re.search(
            r'^version\s*=\s*"([^"]+)"', pyproject.read_text(encoding="utf-8"), re.M
        )
        if match:
            return match.group(1)
    except Exception as e:
        logger.debug(f"Could not read the version from pyproject.toml: {e}")
    return _FALLBACK_VERSION


def parse_version(text: str) -> Optional[Tuple[int, int, int]]:
    """Parse ``v1.2.3`` or ``1.2.3`` into a comparable tuple, else None.

    Tolerant on purpose: release tags arrive as ``v0.2.0``, ``0.2.0`` and
    occasionally ``0.2.0-rc1``, and all three should compare correctly.
    """
    if not text:
        return None
    match = _VERSION_RE.search(text)
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def is_newer(candidate: str, current: str) -> bool:
    """True when ``candidate`` is a strictly newer release than ``current``.

    Unparseable input compares as "not newer" — an update notice is a nudge, and
    a false alarm is worse than a missed one.
    """
    a = parse_version(candidate)
    b = parse_version(current)
    if a is None or b is None:
        return False
    return a > b


@dataclass
class UpdateInfo:
    """The outcome of an update check."""

    current: str
    latest: Optional[str] = None
    url: str = ""
    name: str = ""

    @property
    def update_available(self) -> bool:
        return bool(self.latest) and is_newer(self.latest, self.current)

    @property
    def known(self) -> bool:
        """False when the latest version could not be determined at all."""
        return self.latest is not None


async def check_for_update(
    repo: str = DEFAULT_REPO,
    timeout: float = 5.0,
) -> Optional[UpdateInfo]:
    """Ask GitHub for the latest release. Returns None when unreachable.

    Callers should treat None as "unknown", never as an error worth surfacing.
    """
    current = get_version()
    url = f"https://github.com/{repo}/releases"
    try:
        import httpx

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                f"https://api.github.com/repos/{repo}/releases/latest",
                headers={"Accept": "application/vnd.github+json"},
            )
        if response.status_code != 200:
            logger.debug(
                f"Update check returned HTTP {response.status_code} for {repo}"
            )
            return None
        payload = response.json()
        tag = payload.get("tag_name") or ""
        if not parse_version(tag):
            return None
        return UpdateInfo(
            current=current,
            latest=tag.lstrip("v"),
            url=payload.get("html_url") or url,
            name=payload.get("name") or "",
        )
    except Exception as e:
        logger.debug(f"Update check failed (offline is fine): {e}")
        return None


def build_version_text(info: Optional[UpdateInfo] = None, repo: str = DEFAULT_REPO) -> str:
    """Render the /version reply. Kept here so command and startup log agree."""
    current = get_version()
    lines = [f"<b>Aegis</b> <code>v{current}</code>"]
    if info is not None and info.latest:
        if info.update_available:
            lines.append(
                f"\n🔔 <b>Update available:</b> <code>v{info.latest}</code>\n"
                f"<a href=\"{info.url}\">Release notes</a>"
            )
        else:
            lines.append("\n✅ Up to date.")
    elif info is not None:
        lines.append("\n<i>Latest version unknown (could not reach GitHub).</i>")
    lines.append(f"\n<a href=\"https://github.com/{repo}\">github.com/{repo}</a>")
    return "\n".join(lines)
