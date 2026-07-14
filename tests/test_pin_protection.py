"""Tests for PIN protection: encryption, PIN gate, access codes, rate limiting.

Ported from j0sh1b/ha-pass with two deliberate fixes over the upstream
implementation:
  1. _validate_token() (used by /state, /stream, /command) now enforces the
     PIN gate too — upstream only gated the HTML shell page, so anyone who
     knew the slug could skip the PIN entirely via direct API calls.
  2. PIN attempts are rate-limited and compared in constant time — upstream
     had neither.
"""
import time
from unittest.mock import patch

import pytest

from app import database as db
from app.encryption import decrypt_pin, encrypt_pin


# ---------------------------------------------------------------------------
# Encryption — round-trip and tamper detection
# ---------------------------------------------------------------------------

def test_encrypt_decrypt_round_trip():
    ciphertext = encrypt_pin("4821")
    assert ciphertext != "4821"
    assert decrypt_pin(ciphertext) == "4821"


def test_encrypt_produces_different_ciphertext_each_time():
    """Random nonce means the same PIN encrypts differently each call."""
    assert encrypt_pin("4821") != encrypt_pin("4821")


def test_decrypt_rejects_tampered_ciphertext():
    ciphertext = encrypt_pin("4821")
    tampered = ciphertext[:-4] + ("A" * 4)
    with pytest.raises(Exception):
        decrypt_pin(tampered)


# ---------------------------------------------------------------------------
# Database layer — pin storage/decryption, access codes, pin sessions
# ---------------------------------------------------------------------------

async def test_create_token_with_pin_round_trips(test_db):
    now = int(time.time())
    token = await db.create_token(
        label="PIN", slug="pin-db-test", entity_ids=["light.a"],
        expires_at=now + 3600, ip_allowlist=None, pin="4821",
    )
    assert token["pin"] == "4821"
    reloaded = await db.get_token_by_slug("pin-db-test")
    assert reloaded["pin"] == "4821"


async def test_create_token_without_pin_has_none(test_db):
    now = int(time.time())
    token = await db.create_token(
        label="No PIN", slug="no-pin-db-test", entity_ids=["light.a"],
        expires_at=now + 3600, ip_allowlist=None,
    )
    assert token["pin"] is None


async def test_update_token_pin_sets_and_clears(test_db):
    now = int(time.time())
    token = await db.create_token(
        label="Update PIN", slug="update-pin-test", entity_ids=["light.a"],
        expires_at=now + 3600, ip_allowlist=None,
    )
    await db.update_token_pin(token["id"], "1357")
    reloaded = await db.get_token_by_id(token["id"])
    assert reloaded["pin"] == "1357"

    await db.update_token_pin(token["id"], None)
    reloaded = await db.get_token_by_id(token["id"])
    assert reloaded["pin"] is None


async def test_access_code_lookup(test_db):
    now = int(time.time())
    token = await db.create_token(
        label="Code", slug="code-test", entity_ids=["light.a"],
        expires_at=now + 3600, ip_allowlist=None, pin="4821",
    )
    code = await db.set_token_access_code(token["id"])
    found = await db.get_token_by_access_code(code)
    assert found["id"] == token["id"]

    await db.clear_token_access_code(token["id"])
    assert await db.get_token_by_access_code(code) is None


async def test_guest_pin_session_create_and_lookup(test_db):
    now = int(time.time())
    token = await db.create_token(
        label="Session", slug="session-test", entity_ids=["light.a"],
        expires_at=now + 3600, ip_allowlist=None, pin="4821",
    )
    session_id = await db.create_guest_pin_session(token["id"])
    row = await db.get_guest_pin_session(session_id)
    assert row["token_id"] == token["id"]


async def test_guest_pin_session_expiry_purged_by_cleanup(test_db):
    now = int(time.time())
    token = await db.create_token(
        label="Expiring session", slug="expiring-session-test", entity_ids=["light.a"],
        expires_at=now + 3600, ip_allowlist=None, pin="4821",
    )
    session_id = await db.create_guest_pin_session(token["id"])
    conn = await db.get_db()
    await conn.execute(
        "UPDATE guest_pin_sessions SET expires_at = ? WHERE id = ?",
        (now - 1, session_id),
    )
    await conn.commit()
    await db.cleanup_old_data(retention_days=90)
    assert await db.get_guest_pin_session(session_id) is None


# ---------------------------------------------------------------------------
# Guest PWA shell — PIN gate rendering
# ---------------------------------------------------------------------------

async def test_pin_protected_token_shows_pin_entry_page(client, mock_ha_client, test_db):
    now = int(time.time())
    await db.create_token(
        label="Protected", slug="protected-page", entity_ids=["light.a"],
        expires_at=now + 3600, ip_allowlist=None, pin="4821",
    )
    resp = await client.get("/g/protected-page")
    assert resp.status_code == 200
    assert "Enter PIN" in resp.text
    mock_ha_client["fire_event"].assert_not_called()  # not counted as a real visit


async def test_unprotected_token_skips_pin_entry_page(client, sample_token, mock_ha_client):
    resp = await client.get(f"/g/{sample_token['slug']}")
    assert resp.status_code == 200
    assert "Enter PIN" not in resp.text


async def test_pending_token_with_pin_bypasses_pin_gate(client, mock_ha_client, test_db):
    """A PIN is meaningless before the token's window even opens."""
    now = int(time.time())
    await db.create_token(
        label="Pending+PIN", slug="pending-pin-test", entity_ids=["light.a"],
        expires_at=now + 7200, ip_allowlist=None, starts_at=now + 3600, pin="4821",
    )
    resp = await client.get("/g/pending-pin-test")
    assert resp.status_code == 200
    assert "Enter PIN" not in resp.text


# ---------------------------------------------------------------------------
# POST /{slug}/pin — submission, session cookie, rate limiting
# ---------------------------------------------------------------------------

async def test_correct_pin_creates_session_and_redirects(client, mock_ha_client, test_db):
    now = int(time.time())
    await db.create_token(
        label="Correct PIN", slug="correct-pin-test", entity_ids=["light.a"],
        expires_at=now + 3600, ip_allowlist=None, pin="4821",
    )
    resp = await client.post("/g/correct-pin-test/pin", data={"pin": "4821"})
    assert resp.status_code == 303
    assert resp.headers["location"].endswith("/g/correct-pin-test")
    assert any(c for c in resp.cookies)

    # The session cookie now lets the shell page through without the PIN wall
    page = await client.get("/g/correct-pin-test")
    assert "Enter PIN" not in page.text


async def test_wrong_pin_rejected_with_error(client, mock_ha_client, test_db):
    now = int(time.time())
    await db.create_token(
        label="Wrong PIN", slug="wrong-pin-test", entity_ids=["light.a"],
        expires_at=now + 3600, ip_allowlist=None, pin="4821",
    )
    resp = await client.post("/g/wrong-pin-test/pin", data={"pin": "0000"})
    assert resp.status_code == 401
    assert "Incorrect PIN" in resp.text


async def test_pin_attempts_are_rate_limited(client, mock_ha_client, test_db):
    """Brute-forcing the PIN gets cut off — the upstream repo had no
    rate limiting on this endpoint at all."""
    import app.routers.guest as guest_module

    now = int(time.time())
    await db.create_token(
        label="Bruteforce", slug="bruteforce-test", entity_ids=["light.a"],
        expires_at=now + 3600, ip_allowlist=None, pin="4821",
    )
    with patch.object(guest_module, "PIN_ATTEMPTS_PER_MINUTE", 3):
        for i in range(3):
            resp = await client.post("/g/bruteforce-test/pin", data={"pin": "0000"})
            assert resp.status_code == 401, f"attempt {i} should be a normal wrong-PIN rejection"

        resp = await client.post("/g/bruteforce-test/pin", data={"pin": "4821"})  # even the correct PIN
        assert resp.status_code == 429


async def test_pin_submit_on_token_without_pin_redirects_through(client, sample_token, mock_ha_client):
    resp = await client.post(f"/g/{sample_token['slug']}/pin", data={"pin": "anything"})
    assert resp.status_code == 303


# ---------------------------------------------------------------------------
# The bypass-hole fix — state/stream/command must also enforce the PIN gate
# ---------------------------------------------------------------------------

async def test_state_endpoint_blocked_without_pin_session(client, mock_ha_client, test_db):
    now = int(time.time())
    await db.create_token(
        label="Guarded", slug="guarded-state", entity_ids=["light.a"],
        expires_at=now + 3600, ip_allowlist=None, pin="4821",
    )
    resp = await client.get("/g/guarded-state/state")
    assert resp.status_code == 401


async def test_command_endpoint_blocked_without_pin_session(client, mock_ha_client, test_db):
    now = int(time.time())
    await db.create_token(
        label="Guarded", slug="guarded-command", entity_ids=["light.a"],
        expires_at=now + 3600, ip_allowlist=None, pin="4821",
    )
    resp = await client.post(
        "/g/guarded-command/command",
        json={"entity_id": "light.a", "service": "turn_on"},
    )
    assert resp.status_code == 401
    mock_ha_client["call_service"].assert_not_called()


async def test_stream_endpoint_blocked_without_pin_session(client, mock_ha_client, test_db):
    now = int(time.time())
    await db.create_token(
        label="Guarded", slug="guarded-stream", entity_ids=["light.a"],
        expires_at=now + 3600, ip_allowlist=None, pin="4821",
    )
    resp = await client.get("/g/guarded-stream/stream")
    assert resp.status_code == 401


async def test_command_endpoint_allowed_after_pin_session_established(client, mock_ha_client, test_db):
    now = int(time.time())
    await db.create_token(
        label="Unlocked", slug="unlocked-command", entity_ids=["light.a"],
        expires_at=now + 3600, ip_allowlist=None, pin="4821",
    )
    resp = await client.post("/g/unlocked-command/pin", data={"pin": "4821"})
    assert resp.status_code == 303

    resp = await client.post(
        "/g/unlocked-command/command",
        json={"entity_id": "light.a", "service": "turn_on"},
    )
    assert resp.status_code == 200
    mock_ha_client["call_service"].assert_called_once()


# ---------------------------------------------------------------------------
# Access codes — link-based PIN bypass
# ---------------------------------------------------------------------------

async def test_access_code_grants_session_via_query_param(client, mock_ha_client, test_db):
    now = int(time.time())
    token = await db.create_token(
        label="Coded", slug="coded-test", entity_ids=["light.a"],
        expires_at=now + 3600, ip_allowlist=None, pin="4821",
    )
    code = await db.set_token_access_code(token["id"])

    resp = await client.get(f"/g/coded-test?c={code}")
    assert resp.status_code == 302
    assert resp.headers["location"] == "/g/coded-test"  # clean URL, code stripped

    # Session cookie now covers the API endpoints too
    resp = await client.get("/g/coded-test/state")
    assert resp.status_code == 200


async def test_wrong_access_code_does_not_grant_session(client, mock_ha_client, test_db):
    now = int(time.time())
    token = await db.create_token(
        label="Coded", slug="coded-wrong-test", entity_ids=["light.a"],
        expires_at=now + 3600, ip_allowlist=None, pin="4821",
    )
    await db.set_token_access_code(token["id"])

    resp = await client.get("/g/coded-wrong-test?c=not-the-real-code")
    assert resp.status_code == 200
    assert "Enter PIN" in resp.text


async def test_access_code_directly_on_state_endpoint(client, mock_ha_client, test_db):
    """The API endpoints accept ?c= directly too, not just the shell page."""
    now = int(time.time())
    token = await db.create_token(
        label="Coded", slug="coded-state-test", entity_ids=["light.a"],
        expires_at=now + 3600, ip_allowlist=None, pin="4821",
    )
    code = await db.set_token_access_code(token["id"])
    resp = await client.get(f"/g/coded-state-test/state?c={code}")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Admin endpoints — set/clear PIN, generate/revoke access codes
# ---------------------------------------------------------------------------

async def test_admin_can_set_and_clear_pin(client, admin_session, sample_token, mock_ha_client):
    resp = await client.patch(
        f"/admin/tokens/{sample_token['id']}/pin",
        json={"pin": "9999"},
        cookies=admin_session,
    )
    assert resp.status_code == 200
    assert resp.json()["pin"] == "9999"

    resp = await client.patch(
        f"/admin/tokens/{sample_token['id']}/pin",
        json={"pin": None},
        cookies=admin_session,
    )
    assert resp.status_code == 200
    assert resp.json()["pin"] is None


async def test_clearing_pin_also_clears_access_code(client, admin_session, sample_token, mock_ha_client):
    await client.patch(f"/admin/tokens/{sample_token['id']}/pin", json={"pin": "9999"}, cookies=admin_session)
    r = await client.post(f"/admin/tokens/{sample_token['id']}/access-code", cookies=admin_session)
    assert r.status_code == 200
    assert r.json()["has_access_code"] is True

    r = await client.patch(f"/admin/tokens/{sample_token['id']}/pin", json={"pin": None}, cookies=admin_session)
    assert r.json()["has_access_code"] is False


async def test_access_code_requires_pin_first(client, admin_session, sample_token, mock_ha_client):
    resp = await client.post(f"/admin/tokens/{sample_token['id']}/access-code", cookies=admin_session)
    assert resp.status_code == 400


async def test_admin_can_revoke_access_code(client, admin_session, sample_token, mock_ha_client):
    await client.patch(f"/admin/tokens/{sample_token['id']}/pin", json={"pin": "9999"}, cookies=admin_session)
    await client.post(f"/admin/tokens/{sample_token['id']}/access-code", cookies=admin_session)

    resp = await client.delete(f"/admin/tokens/{sample_token['id']}/access-code", cookies=admin_session)
    assert resp.status_code == 200
    assert resp.json()["has_access_code"] is False


async def test_pin_requires_admin_auth(client, sample_token, mock_ha_client):
    resp = await client.patch(f"/admin/tokens/{sample_token['id']}/pin", json={"pin": "9999"})
    assert resp.status_code == 401


async def test_token_create_with_pin_via_admin_api(client, admin_session, mock_ha_client):
    resp = await client.post(
        "/admin/tokens",
        json={
            "label": "New with PIN",
            "entity_ids": ["light.a"],
            "expires_in_seconds": 3600,
            "pin": "2468",
        },
        cookies=admin_session,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["pin"] == "2468"

    # And the PIN gate is actually live for the new token
    resp = await client.get(f"/g/{body['slug']}/state")
    assert resp.status_code == 401
