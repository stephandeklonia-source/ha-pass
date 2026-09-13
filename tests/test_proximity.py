"""Tests for proximity-gated commands.

Gating is per-entity (an admin picks which entities in a token need it),
not tied to a fixed set of domains — a helper button wired to a door
relay can be gated the same way a native lock would be. The guest's
browser reports its own coordinates — this is a soft gate against casual
misuse (same caveat as the IP allowlist), not a cryptographic guarantee,
since a client can lie about its location.
"""
import time

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
# No entities gated (default) — no behavior change
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


async def test_proximity_entity_ids_empty_by_default_on_create(client, admin_session, mock_ha_client):
    resp = await client.post(
        "/admin/tokens",
        json={"label": "Default proximity", "entity_ids": ["lock.a"], "expires_in_seconds": 3600},
        cookies=admin_session,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["require_proximity"] is False
    assert body["proximity_entity_ids"] == []


# ---------------------------------------------------------------------------
# Gated entities — enforcement is per entity_id, not per domain
# ---------------------------------------------------------------------------

async def test_gated_lock_command_without_location_is_rejected(client, mock_ha_client, test_db):
    now = int(time.time())
    await db.create_token(
        label="Gated", slug="gated-no-location", entity_ids=["lock.front_door"],
        expires_at=now + 3600, ip_allowlist=None, proximity_entity_ids=["lock.front_door"],
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
        expires_at=now + 3600, ip_allowlist=None, proximity_entity_ids=["lock.front_door"],
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
        expires_at=now + 3600, ip_allowlist=None, proximity_entity_ids=["lock.front_door"],
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
        expires_at=now + 3600, ip_allowlist=None, proximity_entity_ids=["alarm_control_panel.home"],
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
        expires_at=now + 3600, ip_allowlist=None, proximity_entity_ids=["alarm_control_panel.home"],
    )
    resp = await client.post(
        "/g/gated-alarm-far/command",
        json={
            "entity_id": "alarm_control_panel.home", "service": "alarm_disarm",
            "latitude": FAR_LAT, "longitude": FAR_LON,
        },
    )
    assert resp.status_code == 403


async def test_gated_input_button_far_away_is_rejected(client, mock_ha_client, test_db):
    """The motivating case: a helper button wired to a door relay, gated
    individually rather than by blanket-gating the whole input_button
    domain (which is used for all sorts of unrelated buttons too)."""
    now = int(time.time())
    await db.create_token(
        label="Door relay", slug="door-relay-test",
        entity_ids=["input_button.open_door", "input_button.ring_bell"],
        expires_at=now + 3600, ip_allowlist=None, proximity_entity_ids=["input_button.open_door"],
    )
    resp = await client.post(
        "/g/door-relay-test/command",
        json={"entity_id": "input_button.open_door", "service": "press", "latitude": FAR_LAT, "longitude": FAR_LON},
    )
    assert resp.status_code == 403
    mock_ha_client["call_service"].assert_not_called()


async def test_ungated_sibling_entity_in_same_token_is_unaffected(client, mock_ha_client, test_db):
    """Gating one input_button must not gate every input_button in the token."""
    now = int(time.time())
    await db.create_token(
        label="Door relay", slug="door-relay-sibling-test",
        entity_ids=["input_button.open_door", "input_button.ring_bell"],
        expires_at=now + 3600, ip_allowlist=None, proximity_entity_ids=["input_button.open_door"],
    )
    resp = await client.post(
        "/g/door-relay-sibling-test/command",
        json={"entity_id": "input_button.ring_bell", "service": "press"},
    )
    assert resp.status_code == 200
    mock_ha_client["call_service"].assert_called_once()


async def test_lock_without_being_gated_ignores_location(client, mock_ha_client, test_db):
    """Even a lock domain entity isn't gated unless explicitly selected —
    gating is opt-in per entity, no implicit domain default."""
    now = int(time.time())
    await db.create_token(
        label="Ungated lock", slug="ungated-lock-test", entity_ids=["lock.shed", "lock.front_door"],
        expires_at=now + 3600, ip_allowlist=None, proximity_entity_ids=["lock.front_door"],
    )
    resp = await client.post(
        "/g/ungated-lock-test/command",
        json={"entity_id": "lock.shed", "service": "unlock"},
    )
    assert resp.status_code == 200
    mock_ha_client["get_home_zone"].assert_not_called()


async def test_gated_command_fails_closed_when_home_zone_unavailable(client, mock_ha_client, test_db):
    """If HA's home zone can't be fetched, the command is blocked, not allowed through."""
    mock_ha_client["get_home_zone"].return_value = None
    now = int(time.time())
    await db.create_token(
        label="Gated", slug="gated-zone-unavailable", entity_ids=["lock.front_door"],
        expires_at=now + 3600, ip_allowlist=None, proximity_entity_ids=["lock.front_door"],
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

async def test_admin_can_set_proximity_entity_ids_via_edit_entities(client, admin_session, mock_ha_client, test_db):
    now = int(time.time())
    token = await db.create_token(
        label="Editable", slug="editable-proximity-test", entity_ids=["lock.a", "light.b"],
        expires_at=now + 3600, ip_allowlist=None,
    )
    resp = await client.patch(
        f"/admin/tokens/{token['id']}/entities",
        json={"entity_ids": ["lock.a", "light.b"], "proximity_entity_ids": ["lock.a"]},
        cookies=admin_session,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["require_proximity"] is True
    assert body["proximity_entity_ids"] == ["lock.a"]

    # Clearing it again drops the badge
    resp = await client.patch(
        f"/admin/tokens/{token['id']}/entities",
        json={"entity_ids": ["lock.a", "light.b"], "proximity_entity_ids": []},
        cookies=admin_session,
    )
    assert resp.status_code == 200
    assert resp.json()["require_proximity"] is False


async def test_proximity_entity_ids_must_be_subset_of_entity_ids(client, admin_session, sample_token, mock_ha_client):
    resp = await client.patch(
        f"/admin/tokens/{sample_token['id']}/entities",
        json={"entity_ids": ["light.living_room"], "proximity_entity_ids": ["lock.not_in_token"]},
        cookies=admin_session,
    )
    assert resp.status_code == 422


async def test_entities_edit_requires_admin_auth(client, sample_token, mock_ha_client):
    resp = await client.patch(
        f"/admin/tokens/{sample_token['id']}/entities",
        json={"entity_ids": ["light.living_room"], "proximity_entity_ids": []},
    )
    assert resp.status_code == 401


async def test_create_token_with_proximity_entity_ids_via_admin_api(client, admin_session, mock_ha_client):
    resp = await client.post(
        "/admin/tokens",
        json={
            "label": "Gated on create", "entity_ids": ["lock.a", "input_button.open_door"],
            "expires_in_seconds": 3600, "proximity_entity_ids": ["input_button.open_door"],
        },
        cookies=admin_session,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["require_proximity"] is True
    assert body["proximity_entity_ids"] == ["input_button.open_door"]

    # The gated entity is blocked without a location...
    resp = await client.post(
        f"/g/{body['slug']}/command",
        json={"entity_id": "input_button.open_door", "service": "press"},
    )
    assert resp.status_code == 400
    # ...but the ungated one works normally
    resp = await client.post(
        f"/g/{body['slug']}/command",
        json={"entity_id": "lock.a", "service": "unlock"},
    )
    assert resp.status_code == 200


async def test_create_token_rejects_proximity_entity_ids_outside_entity_ids(client, admin_session, mock_ha_client):
    resp = await client.post(
        "/admin/tokens",
        json={
            "label": "Bad request", "entity_ids": ["lock.a"],
            "expires_in_seconds": 3600, "proximity_entity_ids": ["lock.not_selected"],
        },
        cookies=admin_session,
    )
    assert resp.status_code == 422


async def test_token_list_shows_require_proximity_badge(client, admin_session, mock_ha_client, test_db):
    now = int(time.time())
    await db.create_token(
        label="Listed", slug="listed-proximity-test", entity_ids=["lock.a"],
        expires_at=now + 3600, ip_allowlist=None, proximity_entity_ids=["lock.a"],
    )
    resp = await client.get("/admin/tokens", cookies=admin_session)
    assert resp.status_code == 200
    listed = next(t for t in resp.json() if t["slug"] == "listed-proximity-test")
    assert listed["require_proximity"] is True
