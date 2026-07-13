"""Ingress detection helpers.

Only trust X-Ingress-Path when SUPERVISOR_TOKEN exists (add-on mode).
This prevents header spoofing in standalone Docker deployments.
"""
import logging
import os
import time

import httpx
from fastapi import Request

logger = logging.getLogger(__name__)

_SUPERVISOR_TOKEN: str | None = os.environ.get("SUPERVISOR_TOKEN")
_SUPERVISOR_API = "http://supervisor"
_GUEST_LINK_CONTAINER_PORT = "5880/tcp"
_GUEST_PORT_CACHE_TTL = 300  # seconds

_guest_port_cache: int | None = None
_guest_port_cache_ts: float = 0.0


def get_ingress_path(request: Request) -> str:
    if not _SUPERVISOR_TOKEN:
        return ""
    return request.headers.get("X-Ingress-Path", "")


def is_ingress_request(request: Request) -> bool:
    return bool(get_ingress_path(request))


async def get_guest_port(default: int = 5880) -> int:
    """Return the host port Supervisor has mapped to our guest-link port.

    Users can remap the add-on's Network port in the Supervisor UI without
    touching the Guest URL option — in that case guest links must follow
    the port the user actually chose instead of staying on the built-in
    default. Falls back to `default` in standalone mode or if the
    Supervisor lookup fails.
    """
    global _guest_port_cache, _guest_port_cache_ts
    if not _SUPERVISOR_TOKEN:
        return default

    now = time.monotonic()
    if _guest_port_cache is not None and (now - _guest_port_cache_ts) < _GUEST_PORT_CACHE_TTL:
        return _guest_port_cache

    try:
        async with httpx.AsyncClient(base_url=_SUPERVISOR_API, timeout=5) as client:
            resp = await client.get(
                "/addons/self/info",
                headers={"Authorization": f"Bearer {_SUPERVISOR_TOKEN}"},
            )
            resp.raise_for_status()
            port = int(resp.json()["data"]["network"][_GUEST_LINK_CONTAINER_PORT])
    except Exception:
        logger.warning("Could not fetch mapped guest port from Supervisor — using cached/default value", exc_info=True)
        return _guest_port_cache if _guest_port_cache is not None else default

    _guest_port_cache = port
    _guest_port_cache_ts = now
    return port
