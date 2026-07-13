"""Tests for ingress detection and ingress-based auth bypass.

These cover the new ingress feature: header spoofing prevention,
admin auth bypass for HA sidebar, login disabled in add-on mode,
and logout sentinel safety.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.ingress
from app import database as db


# ---------------------------------------------------------------------------
# Security: header spoofing prevention
# ---------------------------------------------------------------------------

def test_ingress_header_ignored_without_supervisor_token():
    """Without SUPERVISOR_TOKEN, X-Ingress-Path is untrusted — blocks spoofing."""
    from unittest.mock import MagicMock
    req = MagicMock()
    req.headers = {"X-Ingress-Path": "/api/hassio_ingress/spoofed"}
    with patch.object(app.ingress, "_SUPERVISOR_TOKEN", None):
        assert app.ingress.get_ingress_path(req) == ""


# ---------------------------------------------------------------------------
# Guest link port — follows the Supervisor-mapped Network port
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_guest_port_cache():
    """Module-level cache must not bleed between tests."""
    app.ingress._guest_port_cache = None
    app.ingress._guest_port_cache_ts = 0.0
    yield
    app.ingress._guest_port_cache = None
    app.ingress._guest_port_cache_ts = 0.0


async def test_get_guest_port_returns_default_in_standalone_mode():
    """Without SUPERVISOR_TOKEN there's no Supervisor to ask — use the default."""
    with patch.object(app.ingress, "_SUPERVISOR_TOKEN", None):
        assert await app.ingress.get_guest_port() == 5880


async def test_get_guest_port_follows_supervisor_network_remap():
    """If the user remapped the Network port in Supervisor, follow it."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"data": {"network": {"5880/tcp": 8080}}}
    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch.object(app.ingress, "_SUPERVISOR_TOKEN", "fake-token"), \
         patch("app.ingress.httpx.AsyncClient", return_value=mock_client):
        assert await app.ingress.get_guest_port() == 8080

        # Cached — a second call within the TTL must not hit Supervisor again.
        assert await app.ingress.get_guest_port() == 8080
        assert mock_client.get.call_count == 1


async def test_get_guest_port_falls_back_on_supervisor_error():
    """A Supervisor API failure must not break guest link generation."""
    mock_client = AsyncMock()
    mock_client.get.side_effect = Exception("connection refused")
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch.object(app.ingress, "_SUPERVISOR_TOKEN", "fake-token"), \
         patch("app.ingress.httpx.AsyncClient", return_value=mock_client):
        assert await app.ingress.get_guest_port() == 5880


# ---------------------------------------------------------------------------
# Integration: ingress auth bypass
# ---------------------------------------------------------------------------

async def test_ingress_bypass_grants_admin_access(client, mock_ha_client, test_db):
    """Ingress requests skip session auth — admin endpoints accessible without cookie."""
    with patch("app.auth.is_ingress_request", return_value=True):
        resp = await client.get("/admin/tokens")
    assert resp.status_code == 200


async def test_login_returns_403_when_no_password(client, mock_ha_client, test_db):
    """In add-on mode (empty password), login endpoint returns 403."""
    from app.config import settings
    with patch.object(settings, "admin_password", ""):
        resp = await client.post(
            "/admin/login",
            json={"username": "testadmin", "password": "anything"},
        )
    assert resp.status_code == 403
    assert "Login disabled" in resp.json()["detail"]


async def test_ingress_logout_does_not_delete_real_sessions(client, mock_ha_client, test_db):
    """Ingress logout returns ok without accidentally wiping a real session."""
    session_id = await db.create_admin_session(ttl_seconds=86400)
    with patch("app.auth.is_ingress_request", return_value=True):
        resp = await client.post("/admin/logout")
    assert resp.status_code == 200
    row = await db.get_admin_session(session_id)
    assert row is not None
