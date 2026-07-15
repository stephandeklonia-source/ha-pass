"""SQLite database setup and CRUD operations.

Note: Uses a single aiosqlite connection for all operations. This serializes
all DB access (reads block writes and vice versa), which is acceptable at
homelab scale with low concurrent users. For higher concurrency, consider
connection pooling or switching to PostgreSQL.
"""
import asyncio
import json
import logging
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

import aiosqlite

from app.config import settings
from app.encryption import decrypt_pin, encrypt_pin

logger = logging.getLogger(__name__)

# Guest PIN session lifetime. The "don't remember" duration bounds a
# browser-session-only cookie as a defense-in-depth safety net; the
# "remembered" duration is what a persistent cookie actually lives for.
GUEST_PIN_SESSION_TTL = 86400              # 24 hours — remember_pin=False
GUEST_PIN_SESSION_TTL_REMEMBERED = 31536000  # 365 days — remember_pin=True

_db: aiosqlite.Connection | None = None
_lock = asyncio.Lock()


def run_migrations() -> None:
    """Run Alembic migrations synchronously (called before the async event loop)."""
    from alembic.config import Config
    from alembic import command

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{settings.db_path}")
    command.upgrade(cfg, "head")


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        async with _lock:
            if _db is None:
                _db = await aiosqlite.connect(settings.db_path)
                _db.row_factory = aiosqlite.Row
                await _db.execute("PRAGMA journal_mode=WAL")
                await _db.execute("PRAGMA foreign_keys=ON")
    return _db


async def close_db() -> None:
    global _db
    if _db is not None:
        try:
            await _db.close()
        except Exception as exc:
            logger.warning("Error closing database: %s", exc)
        _db = None


def _decrypt_pin_in_row(row: aiosqlite.Row) -> dict[str, Any]:
    """Convert a row to a dict and decrypt pin_encrypted into a plaintext pin."""
    row_dict = dict(row)
    pin_encrypted = row_dict.pop("pin_encrypted", None)
    if pin_encrypted:
        try:
            row_dict["pin"] = decrypt_pin(pin_encrypted)
        except Exception:
            logger.warning("Failed to decrypt pin for token %s", row_dict.get("id"))
            row_dict["pin"] = None
    else:
        row_dict["pin"] = None
    return row_dict


# ---------------------------------------------------------------------------
# Guest PIN sessions (POST-based PIN validation)
# ---------------------------------------------------------------------------

async def create_guest_pin_session(token_id: str, ttl_seconds: int = GUEST_PIN_SESSION_TTL) -> str:
    db = await get_db()
    session_id = uuid.uuid4().hex + uuid.uuid4().hex  # 64-char hex
    now = int(time.time())
    await db.execute(
        """INSERT INTO guest_pin_sessions (id, token_id, created_at, expires_at)
           VALUES (?, ?, ?, ?)""",
        (session_id, token_id, now, now + ttl_seconds),
    )
    await db.commit()
    return session_id


async def get_guest_pin_session(session_id: str) -> aiosqlite.Row | None:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM guest_pin_sessions WHERE id = ? AND expires_at > ?",
        (session_id, int(time.time())),
    ) as cur:
        return await cur.fetchone()


# ---------------------------------------------------------------------------
# Access codes (link-based PIN bypass)
# ---------------------------------------------------------------------------

async def set_token_access_code(token_id: str) -> str:
    """Generate and store a random access code, replacing any existing one."""
    code = secrets.token_hex(16)  # 32-char hex
    db = await get_db()
    await db.execute("UPDATE tokens SET access_code = ? WHERE id = ?", (code, token_id))
    await db.commit()
    return code


async def get_token_by_access_code(access_code: str) -> dict[str, Any] | None:
    db = await get_db()
    async with db.execute("SELECT * FROM tokens WHERE access_code = ?", (access_code,)) as cur:
        row = await cur.fetchone()
        return _decrypt_pin_in_row(row) if row else None


async def clear_token_access_code(token_id: str) -> None:
    db = await get_db()
    await db.execute("UPDATE tokens SET access_code = NULL WHERE id = ?", (token_id,))
    await db.commit()


# ---------------------------------------------------------------------------
# Admin sessions
# ---------------------------------------------------------------------------

async def create_admin_session(ttl_seconds: int) -> str:
    db = await get_db()
    session_id = uuid.uuid4().hex + uuid.uuid4().hex  # 64-char hex
    now = int(time.time())
    await db.execute(
        "INSERT INTO admin_sessions (id, created_at, expires_at) VALUES (?, ?, ?)",
        (session_id, now, now + ttl_seconds),
    )
    await db.commit()
    return session_id


async def get_admin_session(session_id: str) -> aiosqlite.Row | None:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM admin_sessions WHERE id = ? AND expires_at > ?",
        (session_id, int(time.time())),
    ) as cur:
        return await cur.fetchone()


async def delete_admin_session(session_id: str) -> None:
    db = await get_db()
    await db.execute("DELETE FROM admin_sessions WHERE id = ?", (session_id,))
    await db.commit()


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------

async def create_token(
    label: str,
    slug: str,
    entity_ids: list[str],
    expires_at: int,
    ip_allowlist: list[str] | None,
    starts_at: int | None = None,         # NEW
    pin: str | None = None,
    remember_pin: bool = True,
) -> dict[str, Any]:
    db = await get_db()
    token_id = str(uuid.uuid4())
    now = int(time.time())
    ip_json = json.dumps(ip_allowlist) if ip_allowlist else None
    pin_encrypted = encrypt_pin(pin) if pin else None

    # Deduplicate entity IDs
    entity_ids = list(dict.fromkeys(entity_ids))

    try:
        await db.execute("BEGIN IMMEDIATE")
        await db.execute(
            """INSERT INTO tokens
               (id, slug, label, created_at, starts_at, expires_at, ip_allowlist, pin_encrypted, remember_pin)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (token_id, slug, label, now, starts_at, expires_at, ip_json, pin_encrypted, int(remember_pin)),
        )
        if entity_ids:
            await db.executemany(
                "INSERT INTO token_entities (token_id, entity_id) VALUES (?, ?)",
                [(token_id, eid) for eid in entity_ids],
            )
        await db.execute("COMMIT")
    except Exception:
        await db.execute("ROLLBACK")
        raise
    return await get_token_by_id(token_id)  # type: ignore[return-value]


async def get_token_by_slug(slug: str) -> dict[str, Any] | None:
    db = await get_db()
    async with db.execute("SELECT * FROM tokens WHERE slug = ?", (slug,)) as cur:
        row = await cur.fetchone()
        return _decrypt_pin_in_row(row) if row else None


async def get_token_by_id(token_id: str) -> dict[str, Any] | None:
    db = await get_db()
    async with db.execute("SELECT * FROM tokens WHERE id = ?", (token_id,)) as cur:
        row = await cur.fetchone()
        return _decrypt_pin_in_row(row) if row else None


async def list_tokens() -> list[dict[str, Any]]:
    db = await get_db()
    async with db.execute(
        """SELECT t.*, COUNT(te.entity_id) AS entity_count
           FROM tokens t
           LEFT JOIN token_entities te ON te.token_id = t.id
           GROUP BY t.id
           ORDER BY t.created_at DESC"""
    ) as cur:
        rows = await cur.fetchall()
    return [_decrypt_pin_in_row(r) for r in rows]


async def get_token_entities(token_id: str) -> list[str]:
    db = await get_db()
    async with db.execute(
        "SELECT entity_id FROM token_entities WHERE token_id = ?", (token_id,)
    ) as cur:
        rows = await cur.fetchall()
    return [r["entity_id"] for r in rows]


async def update_token_entities(token_id: str, entity_ids: list[str]) -> None:
    db = await get_db()
    # Deduplicate entity IDs
    entity_ids = list(dict.fromkeys(entity_ids))
    try:
        await db.execute("BEGIN IMMEDIATE")
        await db.execute("DELETE FROM token_entities WHERE token_id = ?", (token_id,))
        await db.executemany(
            "INSERT INTO token_entities (token_id, entity_id) VALUES (?, ?)",
            [(token_id, eid) for eid in entity_ids],
        )
        await db.execute("COMMIT")
    except Exception:
        await db.execute("ROLLBACK")
        raise


async def update_token_expiry(token_id: str, expires_at: int) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE tokens SET expires_at = ? WHERE id = ?",
        (expires_at, token_id),
    )
    await db.commit()


async def activate_token_now(token_id: str) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE tokens SET starts_at = NULL WHERE id = ?",
        (token_id,),
    )
    await db.commit()


async def update_token_pin(token_id: str, pin: str | None, remember_pin: bool = True) -> None:
    db = await get_db()
    pin_encrypted = encrypt_pin(pin) if pin else None
    await db.execute(
        "UPDATE tokens SET pin_encrypted = ?, remember_pin = ? WHERE id = ?",
        (pin_encrypted, int(remember_pin), token_id),
    )
    await db.commit()


async def revoke_token(token_id: str) -> None:
    db = await get_db()
    await db.execute("UPDATE tokens SET revoked = 1 WHERE id = ?", (token_id,))
    await db.commit()


async def unrevoke_token(token_id: str) -> None:
    db = await get_db()
    await db.execute("UPDATE tokens SET revoked = 0 WHERE id = ?", (token_id,))
    await db.commit()


async def delete_token(token_id: str) -> None:
    db = await get_db()
    # Nullify access_log references before deleting to avoid FK constraint
    # failures on databases where the ON DELETE SET NULL clause is missing.
    await db.execute("UPDATE access_log SET token_id = NULL WHERE token_id = ?", (token_id,))
    await db.execute("DELETE FROM tokens WHERE id = ?", (token_id,))
    await db.commit()


async def touch_token(token_id: str) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE tokens SET last_accessed = ? WHERE id = ?",
        (int(time.time()), token_id),
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Access log
# ---------------------------------------------------------------------------

async def log_access(
    token_id: str,
    event_type: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
    entity_id: str | None = None,
    service: str | None = None,
) -> None:
    db = await get_db()
    await db.execute(
        """INSERT INTO access_log
           (token_id, timestamp, event_type, entity_id, service, ip_address, user_agent)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (token_id, int(time.time()), event_type, entity_id, service, ip_address, user_agent),
    )
    # Single-write commit is acceptable at homelab scale; batch for high throughput
    await db.commit()


async def list_access_logs(limit: int = 50) -> list[aiosqlite.Row]:
    db = await get_db()
    async with db.execute(
        """SELECT al.timestamp, al.event_type, al.entity_id, al.service,
                  al.ip_address, t.label AS token_label
           FROM access_log al
           LEFT JOIN tokens t ON t.id = al.token_id
           ORDER BY al.timestamp DESC, al.id DESC
           LIMIT ?""",
        (limit,),
    ) as cur:
        return await cur.fetchall()


async def cleanup_old_data(retention_days: int) -> None:
    """Delete old access_log rows, expired admin sessions, and expired guest PIN sessions.

    Guest tokens are intentionally retained until an admin deletes them so
    expired or revoked links can be renewed with the same entities and slug.
    """
    db = await get_db()
    now = int(time.time())
    cutoff = now - (retention_days * 86400)
    await db.execute("DELETE FROM access_log WHERE timestamp < ?", (cutoff,))
    await db.execute("DELETE FROM admin_sessions WHERE expires_at < ?", (now,))
    await db.execute("DELETE FROM guest_pin_sessions WHERE expires_at < ?", (now,))
    await db.commit()
