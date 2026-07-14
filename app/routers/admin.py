"""Admin API router."""
import ipaddress
import json
import secrets
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from app import database as db
from app.auth import INGRESS_SENTINEL, SESSION_COOKIE, require_admin, verify_password
from app.config import settings
from app import ha_client
from app.models import (
    AdminLoginRequest,
    NEVER_EXPIRES_SECONDS,
    SUPPORTED_DOMAINS,
    TokenCreateRequest,
    TokenUpdateEntitiesRequest,
    TokenUpdateExpiryRequest,
    TokenUpdatePinRequest,
)
from app.rate_limiter import RateLimiter

router = APIRouter(prefix="/admin")

# Admin session lifetime — 24 hours, hardcoded like Uptime Kuma / Dockge.
ADMIN_SESSION_TTL = 86400

# CSRF: Admin routes are protected by SameSite=strict cookie. The slug-based
# guest auth acts as a bearer token — no additional CSRF token needed.

# M-24: Rate limiting on admin login (5 failed attempts/min/IP)
_login_limiter = RateLimiter()

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@router.post("/login")
async def login(body: AdminLoginRequest, request: Request, response: Response) -> dict:
    if not settings.admin_password:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Login disabled — use HA sidebar")

    # Rate limit login attempts by IP
    client_ip = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )
    allowed = await _login_limiter.check(f"login:{client_ip}", 5)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many login attempts")

    if body.username != settings.admin_username or not await verify_password(body.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    forwarded_proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip()
    is_https = (
        request.url.scheme == "https"
        or forwarded_proto == "https"
    )
    session_id = await db.create_admin_session(ttl_seconds=ADMIN_SESSION_TTL)
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        httponly=True,
        samesite="strict",
        secure=is_https,
        max_age=ADMIN_SESSION_TTL,
    )
    return {"ok": True}


@router.post("/logout")
async def logout(response: Response, session_id: str = Depends(require_admin)) -> dict:
    if session_id == INGRESS_SENTINEL:
        return {"ok": True}
    await db.delete_admin_session(session_id)
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Token management
# ---------------------------------------------------------------------------

def _row_to_response(row: Any, entity_ids: list[str] | None = None) -> dict:
    ip_raw = row["ip_allowlist"]
    ip_list = json.loads(ip_raw) if ip_raw else None
    if entity_ids is not None:
        count = len(entity_ids)
    elif "entity_count" in row.keys():
        count = row["entity_count"]
    else:
        count = 0
    access_code = row["access_code"] if "access_code" in row.keys() else None
    return {
        "id": row["id"],
        "slug": row["slug"],
        "label": row["label"],
        "created_at": row["created_at"],
        "starts_at": row["starts_at"],
        "expires_at": row["expires_at"],
        "revoked": bool(row["revoked"]),
        "last_accessed": row["last_accessed"],
        "ip_allowlist": ip_list,
        "entity_count": count,
        "entity_ids": entity_ids,
        "pin": row["pin"] if "pin" in row.keys() else None,
        "has_access_code": bool(access_code),
        "access_code": access_code,
    }


def _activity_row_to_response(row: Any) -> dict:
    return {
        "timestamp": row["timestamp"],
        "activity": row["event_type"],
        "token_label": row["token_label"],
        "target_entity_id": row["entity_id"],
        "service": row["service"],
        "ip_address": row["ip_address"],
    }


@router.get("/tokens")
async def list_tokens(_: str = Depends(require_admin)) -> list[dict]:
    rows = await db.list_tokens()
    return [_row_to_response(r) for r in rows]


@router.get("/activity")
async def list_activity(
    limit: int = Query(default=50, ge=1, le=200),
    _: str = Depends(require_admin),
) -> list[dict]:
    rows = await db.list_access_logs(limit=limit)
    return [_activity_row_to_response(r) for r in rows]


@router.post("/tokens", status_code=status.HTTP_201_CREATED)
async def create_token(
    body: TokenCreateRequest,
    request: Request,
    _: str = Depends(require_admin),
) -> dict:
    # Validate IP CIDR list if provided
    if body.ip_allowlist:
        for cidr in body.ip_allowlist:
            try:
                ipaddress.ip_network(cidr, strict=False)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"Invalid CIDR: {cidr}",
                )

    slug = body.slug or secrets.token_hex(16)
    if body.expires_in_seconds == NEVER_EXPIRES_SECONDS:
        expires_at = NEVER_EXPIRES_SECONDS
    else:
        anchor = body.starts_at if body.starts_at else int(time.time())   # NEW
        expires_at = anchor + body.expires_in_seconds                     # NEW
    
    # Sanity check: expiry must be after start (NEW)
    if body.starts_at and expires_at <= body.starts_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Expiry must be after the start time",
        )

    # Ensure slug uniqueness
    existing = await db.get_token_by_slug(slug)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Slug '{slug}' already exists",
        )

    row = await db.create_token(
        label=body.label,
        slug=slug,
        entity_ids=body.entity_ids,
        expires_at=expires_at,
        ip_allowlist=body.ip_allowlist,
        starts_at=body.starts_at,             # NEW
        pin=body.pin,
    )
    entity_ids = await db.get_token_entities(row["id"])
    return _row_to_response(row, entity_ids)


@router.get("/tokens/{token_id}")
async def get_token(token_id: str, _: str = Depends(require_admin)) -> dict:
    row = await db.get_token_by_id(token_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    entity_ids = await db.get_token_entities(token_id)
    return _row_to_response(row, entity_ids)


@router.patch("/tokens/{token_id}/entities")
async def update_token_entities(
    token_id: str,
    body: TokenUpdateEntitiesRequest,
    _: str = Depends(require_admin),
) -> dict:
    row = await db.get_token_by_id(token_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if row["revoked"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot edit entities on a revoked token",
        )
    await db.update_token_entities(token_id, body.entity_ids)
    await ha_client.invalidate_entity_cache(token_id)
    entity_ids = await db.get_token_entities(token_id)
    row = await db.get_token_by_id(token_id)
    return _row_to_response(row, entity_ids)


@router.patch("/tokens/{token_id}/expiry")
async def update_token_expiry(
    token_id: str,
    body: TokenUpdateExpiryRequest,
    _: str = Depends(require_admin),
) -> dict:
    row = await db.get_token_by_id(token_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if body.expires_in_seconds == NEVER_EXPIRES_SECONDS:
        new_expires = NEVER_EXPIRES_SECONDS
    else:
        new_expires = int(time.time()) + body.expires_in_seconds
    await db.update_token_expiry(token_id, new_expires)
    # Un-revoke if the token was revoked (admin is explicitly renewing it)
    if row["revoked"]:
        await db.unrevoke_token(token_id)
    row = await db.get_token_by_id(token_id)
    return _row_to_response(row)


@router.post("/tokens/{token_id}/activate")
async def activate_token(token_id: str, _: str = Depends(require_admin)) -> dict:
    row = await db.get_token_by_id(token_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if row["revoked"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot activate a revoked token",
        )
    if not row["starts_at"] or row["starts_at"] <= int(time.time()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token is not on a delayed start",
        )
    await db.activate_token_now(token_id)
    await ha_client.broadcast_token_activated(token_id)
    row = await db.get_token_by_id(token_id)
    return _row_to_response(row)


@router.patch("/tokens/{token_id}/pin")
async def update_token_pin(
    token_id: str,
    body: TokenUpdatePinRequest,
    _: str = Depends(require_admin),
) -> dict:
    row = await db.get_token_by_id(token_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await db.update_token_pin(token_id, body.pin)
    # Clearing the PIN makes any outstanding access code meaningless — and a
    # leftover code would silently keep granting access with no PIN to show
    # for it, so drop it too.
    if not body.pin:
        await db.clear_token_access_code(token_id)
    row = await db.get_token_by_id(token_id)
    return _row_to_response(row)


@router.post("/tokens/{token_id}/access-code")
async def create_access_code(token_id: str, _: str = Depends(require_admin)) -> dict:
    row = await db.get_token_by_id(token_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if not row["pin"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token has no PIN set — nothing for an access code to bypass",
        )
    await db.set_token_access_code(token_id)
    row = await db.get_token_by_id(token_id)
    return _row_to_response(row)


@router.delete("/tokens/{token_id}/access-code")
async def delete_access_code(token_id: str, _: str = Depends(require_admin)) -> dict:
    row = await db.get_token_by_id(token_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await db.clear_token_access_code(token_id)
    row = await db.get_token_by_id(token_id)
    return _row_to_response(row)


@router.post("/tokens/{token_id}/revoke")
async def revoke_token(token_id: str, _: str = Depends(require_admin)) -> dict:
    row = await db.get_token_by_id(token_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await db.revoke_token(token_id)
    # Notify connected SSE clients
    if not row["revoked"]:
        await ha_client.broadcast_token_expired(token_id)
    return {"ok": True}


@router.delete("/tokens/{token_id}")
async def delete_token(token_id: str, _: str = Depends(require_admin)) -> dict:
    row = await db.get_token_by_id(token_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await ha_client.broadcast_token_expired(token_id)
    await db.delete_token(token_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# HA entity list proxy
# ---------------------------------------------------------------------------

@router.get("/ha/entities")
async def ha_entities(_: str = Depends(require_admin)) -> list[dict]:
    try:
        states = await ha_client.get_states()
    except Exception:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Home Assistant unreachable")
    # Only return entities whose domain guests can either control or view.
    return [
        {
            "entity_id": s["entity_id"],
            "friendly_name": s.get("attributes", {}).get("friendly_name", s["entity_id"]),
            "domain": domain,
            "state": s["state"],
        }
        for s in states
        if (domain := s["entity_id"].split(".")[0]) in SUPPORTED_DOMAINS
    ]
