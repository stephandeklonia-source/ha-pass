"""Tests for proximity-gated lock/alarm commands.

The guest's browser reports its own coordinates — this is a soft gate
against casual misuse (same caveat as the IP allowlist), not a
cryptographic guarantee, since a client can lie about its location.
"""
import time

import pytest

from app import database as db
from app.routers.guest import _haversine_meters

HOME_LAT, HOME_LON = 52.0, 5.0
NEARBY_LAT, NEARBY_LON = 52.0, 5.0            # same point as the mocked home zone
FAR_LAT, FAR_LON = 52.01, 5.01                 # roughly 1.2km away — outside a 100m radius


# ---------------------------------------------------------------------------
# Haversine math
# ---------------------------------------------------------------------------

def test_haversine_same_point_is_zero():
    assert _haversine_meters(52.0, 5.0, 52.0, 5.0) == 0


def test_haversine_known_distance_is_reasonable():
    # ~0.01 degrees of latitude is roughly 1.1km
    distance = _haversine_meters(52.0, 5.0, 52.01, 5.0)
    assert 1000 < distance < 1200


# ---------------------------------------------------------------------------
# require_proximity=False (default) — no behavior change
# ---------------------------------------------------------------------------

async def test_lock_command_without_proximity_requirement_ignores_location(client, mock_ha_client, test_db):
    now = int(time.time())
    await db.create_token(
        label="No proximity", slug="no-proximity-test", entity_ids=["lock.front_door"],
        expires_at=now + 3600, ip_allowlist=None,
    )
    resp = await client.post(
        "/g/no-proximity-test/command",
        json={"entity_id": "lock.front_door", "service": "unlock"},
    )
    assert resp.status_code == 200
    mock_ha_client["call_service"].assert_called_once()
    mock_ha_client["get_home_zone"].assert_not_called()


async def test_require_proximity_defaults_false_on_create(client, admin_session, mock_ha_client):
    resp = await client.post(
        "/admin/tokens",
        json={"label": "Default proximity", "entity_ids": ["lock.a"], "expires_in_seconds": 3600},
        cookies=admin_session,
    )
    assert resp.status_code == 201
    assert resp.json()["require_proximity"] is False


# ---------------------------------------------------------------------------
# require_proximity=True — only lock/alarm_control_panel are gated
# ---------------------------------------------------------------------------

async def test_gated_lock_command_without_location_is_rejected(client, mock_ha_client, test_db):
    now = int(time.time())
    await db.create_token(
        label="Gated", slug="gated-no-location", entity_ids=["lock.front_door"],
        expires_at=now + 3600, ip_allowlist=None, require_proximity=True,
    )
    resp = await client.post(
        "/g/gated-no-location/command",
        json={"entity_id": "lock.front_door", "service": "unlock"},
    )
    assert resp.status_code == 400
    mock_ha_client["call_service"].assert_not_called()


async def test_gated_lock_command_nearby_is_allowed(client, mock_ha_client, test_db):
    now = int(time.time())
    await db.create_token(
        label="Gated", slug="gated-nearby", entity_ids=["lock.front_door"],
        expires_at=now + 3600, ip_allowlist=None, require_proximity=True,
    )
    resp = await client.post(
        "/g/gated-nearby/command",
        json={"entity_id": "lock.front_door", "service": "unlock", "latitude": NEARBY_LAT, "longitude": NEARBY_LON},
    )
    assert resp.status_code == 200
    mock_ha_client["call_service"].assert_called_once()


async def test_gated_lock_command_far_away_is_rejected(client, mock_ha_client, test_db):
    now = int(time.time())
    await db.create_token(
        label="Gated", slug="gated-far", entity_ids=["lock.front_door"],
        expires_at=now + 3600, ip_allowlist=None, require_proximity=True,
    )
    resp = await client.post(
        "/g/gated-far/command",
        json={"entity_id": "lock.front_door", "service": "unlock", "latitude": FAR_LAT, "longitude": FAR_LON},
    )
    assert resp.status_code == 403
    mock_ha_client["call_service"].assert_not_called()


async def test_gated_alarm_command_nearby_is_allowed(client, mock_ha_client, test_db):
    now = int(time.time())
    await db.create_token(
        label="Gated alarm", slug="gated-alarm-nearby", entity_ids=["alarm_control_panel.home"],
        expires_at=now + 3600, ip_allowlist=None, require_proximity=True,
    )
    resp = await client.post(
        "/g/gated-alarm-nearby/command",
        json={
            "entity_id": "alarm_control_panel.home", "service": "alarm_disarm",
            "latitude": NEARBY_LAT, "longitude": NEARBY_LON,
        },
    )
    assert resp.status_code == 200
    mock_ha_client["call_service"].assert_called_once()


async def test_gated_alarm_command_far_away_is_rejected(client, mock_ha_client, test_db):
    now = int(time.time())
    await db.create_token(
        label="Gated alarm", slug="gated-alarm-far", entity_ids=["alarm_control_panel.home"],
        expires_at=now + 3600, ip_allowlist=None, require_proximity=True,
    )
    resp = await client.post(
        "/g/gated-alarm-far/command",
        json={
            "entity_id": "alarm_control_panel.home", "service": "alarm_disarm",
            "latitude": FAR_LAT, "longitude": FAR_LON,
        },
    )
    assert resp.status_code == 403


async def test_non_gated_domain_ignores_proximity_requirement(client, mock_ha_client, test_db):
    """require_proximity only gates lock/alarm — lights etc. work from anywhere."""
    now = int(time.time())
    await db.create_token(
        label="Gated but light", slug="gated-light", entity_ids=["light.kitchen"],
        expires_at=now + 3600, ip_allowlist=None, require_proximity=True,
    )
    resp = await client.post(
        "/g/gated-light/command",
        json={"entity_id": "light.kitchen", "service": "turn_on"},
    )
    assert resp.status_code == 200
    mock_ha_client["get_home_zone"].assert_not_called()


async def test_gated_command_fails_closed_when_home_zone_unavailable(client, mock_ha_client, test_db):
    """If HA's home zone can't be fetched, the command is blocked, not allowed through."""
    mock_ha_client["get_home_zone"].return_value = None
    now = int(time.time())
    await db.create_token(
        label="Gated", slug="gated-zone-unavailable", entity_ids=["lock.front_door"],
        expires_at=now + 3600, ip_allowlist=None, require_proximity=True,
    )
    resp = await client.post(
        "/g/gated-zone-unavailable/command",
        json={"entity_id": "lock.front_door", "service": "unlock", "latitude": NEARBY_LAT, "longitude": NEARBY_LON},
    )
    assert resp.status_code == 503
    mock_ha_client["call_service"].assert_not_called()


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------

async def test_admin_can_toggle_require_proximity(client, admin_session, sample_token, mock_ha_client):
    resp = await client.patch(
        f"/admin/tokens/{sample_token['id']}/proximity",
        json={"require_proximity": True},
        cookies=admin_session,
    )
    assert resp.status_code == 200
    assert resp.json()["require_proximity"] is True

    resp = await client.patch(
        f"/admin/tokens/{sample_token['id']}/proximity",
        json={"require_proximity": False},
        cookies=admin_session,
    )
    assert resp.status_code == 200
    assert resp.json()["require_proximity"] is False


async def test_proximity_toggle_requires_admin_auth(client, sample_token, mock_ha_client):
    resp = await client.patch(
        f"/admin/tokens/{sample_token['id']}/proximity",
        json={"require_proximity": True},
    )
    assert resp.status_code == 401


async def test_create_token_with_require_proximity_via_admin_api(client, admin_session, mock_ha_client):
    resp = await client.post(
        "/admin/tokens",
        json={
            "label": "Gated on create", "entity_ids": ["lock.a"],
            "expires_in_seconds": 3600, "require_proximity": True,
        },
        cookies=admin_session,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["require_proximity"] is True

    resp = await client.post(
        f"/g/{body['slug']}/command",
        json={"entity_id": "lock.a", "service": "unlock"},
    )
    assert resp.status_code == 400
