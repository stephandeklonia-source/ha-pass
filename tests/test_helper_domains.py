"""Tests for Home Assistant helper domains: input_number, input_text,
input_select, input_datetime, input_button, counter, timer, group
(controllable) and schedule (read-only)."""
import time

from app import database as db
from app.models import ALLOWED_SERVICES, READ_ONLY_DOMAINS, SUPPORTED_DOMAINS


def test_helper_domains_are_registered():
    for domain in ["input_number", "input_text", "input_select", "input_datetime",
                    "input_button", "counter", "timer", "group"]:
        assert domain in ALLOWED_SERVICES
    assert "schedule" in READ_ONLY_DOMAINS
    for domain in ["input_number", "input_text", "input_select", "input_datetime",
                    "input_button", "counter", "timer", "group", "schedule"]:
        assert domain in SUPPORTED_DOMAINS


async def _make_token(slug, entity_id):
    now = int(time.time())
    return await db.create_token(
        label="Helper", slug=slug, entity_ids=[entity_id],
        expires_at=now + 3600, ip_allowlist=None,
    )


async def test_input_number_set_value_allowed(client, mock_ha_client, test_db):
    await _make_token("input-number-test", "input_number.volume")
    resp = await client.post(
        "/g/input-number-test/command",
        json={"entity_id": "input_number.volume", "service": "set_value", "data": {"value": 42}},
    )
    assert resp.status_code == 200
    args = mock_ha_client["call_service"].call_args[0]
    assert args[0] == "input_number"
    assert args[1] == "set_value"
    assert args[2]["value"] == 42


async def test_input_text_set_value_allowed(client, mock_ha_client, test_db):
    await _make_token("input-text-test", "input_text.note")
    resp = await client.post(
        "/g/input-text-test/command",
        json={"entity_id": "input_text.note", "service": "set_value", "data": {"value": "hello"}},
    )
    assert resp.status_code == 200
    args = mock_ha_client["call_service"].call_args[0]
    assert args[2]["value"] == "hello"


async def test_input_select_select_option_allowed(client, mock_ha_client, test_db):
    await _make_token("input-select-test", "input_select.mode")
    resp = await client.post(
        "/g/input-select-test/command",
        json={"entity_id": "input_select.mode", "service": "select_option", "data": {"option": "Away"}},
    )
    assert resp.status_code == 200
    args = mock_ha_client["call_service"].call_args[0]
    assert args[0] == "input_select"
    assert args[2]["option"] == "Away"


async def test_input_datetime_set_datetime_allowed(client, mock_ha_client, test_db):
    await _make_token("input-datetime-test", "input_datetime.trip")
    resp = await client.post(
        "/g/input-datetime-test/command",
        json={"entity_id": "input_datetime.trip", "service": "set_datetime", "data": {"date": "2026-08-01"}},
    )
    assert resp.status_code == 200
    args = mock_ha_client["call_service"].call_args[0]
    assert args[0] == "input_datetime"


async def test_input_button_press_allowed(client, mock_ha_client, test_db):
    await _make_token("input-button-test", "input_button.doorbell")
    resp = await client.post(
        "/g/input-button-test/command",
        json={"entity_id": "input_button.doorbell", "service": "press"},
    )
    assert resp.status_code == 200
    args = mock_ha_client["call_service"].call_args[0]
    assert args[0] == "input_button"
    assert args[1] == "press"


async def test_counter_increment_decrement_reset_allowed(client, mock_ha_client, test_db):
    await _make_token("counter-test", "counter.guests")
    for service in ("increment", "decrement", "reset"):
        resp = await client.post(
            "/g/counter-test/command",
            json={"entity_id": "counter.guests", "service": service},
        )
        assert resp.status_code == 200, f"{service} should be allowed"


async def test_timer_start_pause_cancel_allowed(client, mock_ha_client, test_db):
    await _make_token("timer-test", "timer.egg")
    for service in ("start", "pause", "cancel"):
        resp = await client.post(
            "/g/timer-test/command",
            json={"entity_id": "timer.egg", "service": service},
        )
        assert resp.status_code == 200, f"{service} should be allowed"


async def test_timer_finish_not_allowed(client, mock_ha_client, test_db):
    """Only start/pause/cancel are exposed — finish is not a normal guest action."""
    await _make_token("timer-finish-test", "timer.egg")
    resp = await client.post(
        "/g/timer-finish-test/command",
        json={"entity_id": "timer.egg", "service": "finish"},
    )
    assert resp.status_code == 403
    mock_ha_client["call_service"].assert_not_called()


async def test_group_toggle_allowed(client, mock_ha_client, test_db):
    await _make_token("group-test", "group.all_lights")
    resp = await client.post(
        "/g/group-test/command",
        json={"entity_id": "group.all_lights", "service": "toggle"},
    )
    assert resp.status_code == 200
    args = mock_ha_client["call_service"].call_args[0]
    assert args[0] == "group"


async def test_schedule_is_read_only(client, mock_ha_client, test_db):
    await _make_token("schedule-test", "schedule.weekdays")
    resp = await client.post(
        "/g/schedule-test/command",
        json={"entity_id": "schedule.weekdays", "service": "turn_on"},
    )
    assert resp.status_code == 403
    mock_ha_client["call_service"].assert_not_called()


async def test_schedule_appears_in_state_endpoint(client, mock_ha_client, test_db):
    token = await _make_token("schedule-state-test", "schedule.weekdays")
    mock_ha_client["get_states"].return_value = [
        {"entity_id": "schedule.weekdays", "state": "on", "attributes": {"friendly_name": "Weekdays"}},
    ]
    import app.routers.guest as guest_mod
    guest_mod._states_cache = None

    resp = await client.get("/g/schedule-state-test/state")
    assert resp.status_code == 200
    data = resp.json()
    assert data["states"]["schedule.weekdays"]["state"] == "on"


async def test_helper_domains_appear_in_admin_entity_list(client, admin_session, mock_ha_client):
    mock_ha_client["get_states"].return_value = [
        {"entity_id": "input_number.volume", "state": "5", "attributes": {}},
        {"entity_id": "counter.guests", "state": "0", "attributes": {}},
        {"entity_id": "script.not_supported", "state": "off", "attributes": {}},
    ]
    resp = await client.get("/admin/ha/entities", cookies=admin_session)
    assert resp.status_code == 200
    entity_ids = [e["entity_id"] for e in resp.json()]
    assert "input_number.volume" in entity_ids
    assert "counter.guests" in entity_ids
    assert "script.not_supported" not in entity_ids
