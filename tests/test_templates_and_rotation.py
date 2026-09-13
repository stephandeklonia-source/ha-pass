"""Tests for entity templates and guest-link slug rotation.

Ported from upstream feature request:
https://github.com/Rohithkadaveru/ha-pass/issues/6
"""
import time

from app import database as db


# ---------------------------------------------------------------------------
# Entity templates
# ---------------------------------------------------------------------------

async def test_create_and_list_template(client, admin_session, mock_ha_client):
    resp = await client.post(
        "/admin/templates",
        json={"name": "Cleaner", "entity_ids": ["light.kitchen", "lock.front_door"]},
        cookies=admin_session,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Cleaner"
    assert set(body["entity_ids"]) == {"light.kitchen", "lock.front_door"}

    resp = await client.get("/admin/templates", cookies=admin_session)
    assert resp.status_code == 200
    names = [t["name"] for t in resp.json()]
    assert "Cleaner" in names


async def test_duplicate_template_name_rejected(client, admin_session, mock_ha_client):
    await client.post(
        "/admin/templates",
        json={"name": "Guest Basics", "entity_ids": ["light.a"]},
        cookies=admin_session,
    )
    resp = await client.post(
        "/admin/templates",
        json={"name": "Guest Basics", "entity_ids": ["light.b"]},
        cookies=admin_session,
    )
    assert resp.status_code == 409


async def test_delete_template(client, admin_session, mock_ha_client):
    resp = await client.post(
        "/admin/templates",
        json={"name": "Temp", "entity_ids": ["light.a"]},
        cookies=admin_session,
    )
    template_id = resp.json()["id"]

    resp = await client.delete(f"/admin/templates/{template_id}", cookies=admin_session)
    assert resp.status_code == 200

    resp = await client.get("/admin/templates", cookies=admin_session)
    assert all(t["id"] != template_id for t in resp.json())


async def test_delete_nonexistent_template_404s(client, admin_session, mock_ha_client):
    resp = await client.delete("/admin/templates/does-not-exist", cookies=admin_session)
    assert resp.status_code == 404


async def test_templates_require_admin_auth(client, mock_ha_client):
    resp = await client.get("/admin/templates")
    assert resp.status_code == 401
    resp = await client.post("/admin/templates", json={"name": "X", "entity_ids": ["light.a"]})
    assert resp.status_code == 401


async def test_template_entity_ids_deduplicated(client, admin_session, mock_ha_client):
    resp = await client.post(
        "/admin/templates",
        json={"name": "Dupes", "entity_ids": ["light.a", "light.a", "light.b"]},
        cookies=admin_session,
    )
    assert resp.status_code == 201
    assert sorted(resp.json()["entity_ids"]) == ["light.a", "light.b"]


# ---------------------------------------------------------------------------
# Slug rotation
# ---------------------------------------------------------------------------

async def test_rotate_slug_changes_the_link(client, admin_session, sample_token, mock_ha_client):
    old_slug = sample_token["slug"]
    resp = await client.post(f"/admin/tokens/{sample_token['id']}/rotate-slug", cookies=admin_session)
    assert resp.status_code == 200
    new_slug = resp.json()["slug"]
    assert new_slug != old_slug


async def test_old_slug_stops_working_after_rotation(client, admin_session, sample_token, mock_ha_client):
    old_slug = sample_token["slug"]
    await client.post(f"/admin/tokens/{sample_token['id']}/rotate-slug", cookies=admin_session)

    resp = await client.get(f"/g/{old_slug}")
    assert resp.status_code == 410


async def test_new_slug_works_after_rotation(client, admin_session, sample_token, mock_ha_client):
    resp = await client.post(f"/admin/tokens/{sample_token['id']}/rotate-slug", cookies=admin_session)
    new_slug = resp.json()["slug"]

    resp = await client.get(f"/g/{new_slug}")
    assert resp.status_code == 200


async def test_rotation_preserves_entities_and_settings(client, admin_session, mock_ha_client, test_db):
    now = int(time.time())
    token = await db.create_token(
        label="Reusable", slug="reusable-config", entity_ids=["lock.front_door"],
        expires_at=now + 3600, ip_allowlist=["10.0.0.0/8"], pin="4821", proximity_entity_ids=["lock.front_door"],
    )
    resp = await client.post(f"/admin/tokens/{token['id']}/rotate-slug", cookies=admin_session)
    assert resp.status_code == 200
    body = resp.json()
    assert body["entity_ids"] == ["lock.front_door"]
    assert body["ip_allowlist"] == ["10.0.0.0/8"]
    assert body["pin"] == "4821"
    assert body["require_proximity"] is True
    assert body["proximity_entity_ids"] == ["lock.front_door"]


async def test_rotation_clears_access_code(client, admin_session, mock_ha_client, test_db):
    now = int(time.time())
    token = await db.create_token(
        label="Coded", slug="coded-rotate-test", entity_ids=["light.a"],
        expires_at=now + 3600, ip_allowlist=None, pin="4821",
    )
    await db.set_token_access_code(token["id"])

    resp = await client.post(f"/admin/tokens/{token['id']}/rotate-slug", cookies=admin_session)
    assert resp.status_code == 200
    assert resp.json()["has_access_code"] is False


async def test_rotation_preserves_access_log_history(client, admin_session, sample_token, mock_ha_client):
    await client.get(f"/g/{sample_token['slug']}")  # generates a page_load log entry
    conn = await db.get_db()
    async with conn.execute(
        "SELECT COUNT(*) as cnt FROM access_log WHERE token_id = ?", (sample_token["id"],)
    ) as cur:
        before = (await cur.fetchone())["cnt"]
    assert before > 0

    await client.post(f"/admin/tokens/{sample_token['id']}/rotate-slug", cookies=admin_session)

    async with conn.execute(
        "SELECT COUNT(*) as cnt FROM access_log WHERE token_id = ?", (sample_token["id"],)
    ) as cur:
        after = (await cur.fetchone())["cnt"]
    assert after == before


async def test_rotate_slug_requires_admin_auth(client, sample_token, mock_ha_client):
    resp = await client.post(f"/admin/tokens/{sample_token['id']}/rotate-slug")
    assert resp.status_code == 401


async def test_rotate_slug_nonexistent_token_404s(client, admin_session, mock_ha_client):
    resp = await client.post("/admin/tokens/does-not-exist/rotate-slug", cookies=admin_session)
    assert resp.status_code == 404
