"""Pydantic request/response models."""
from typing import Any
from pydantic import BaseModel, Field

NEVER_EXPIRES_SECONDS = 4102444800  # 2099-12-31T00:00:00Z

# Services guests are permitted to call, keyed by entity domain.
# Script/scene/automation domains are intentionally excluded —
# they execute arbitrary automations and bypass entity scoping.
ALLOWED_SERVICES: dict[str, set[str]] = {
    "light":         {"turn_on", "turn_off", "toggle"},
    "switch":        {"turn_on", "turn_off", "toggle"},
    "input_boolean": {"turn_on", "turn_off", "toggle"},
    "climate":       {"set_temperature", "set_hvac_mode", "turn_on", "turn_off"},
    "lock":          {"lock", "unlock", "open"},
    "media_player":  {"media_play", "media_pause", "media_stop", "volume_set",
                      "media_play_pause", "turn_on", "turn_off"},
    "cover":         {"open_cover", "close_cover", "stop_cover"},
    "fan":           {"turn_on", "turn_off", "toggle", "set_percentage"},
    "alarm_control_panel": {"alarm_arm_home", "alarm_arm_away", "alarm_arm_night", "alarm_disarm"},
    "button":        {"press"},
    "time":          {"set_value"},
    "datetime":      {"set_value"},
    # Helper domains (Settings → Devices & Services → Helpers)
    "input_number":  {"set_value"},
    "input_text":    {"set_value"},
    "input_select":  {"select_option"},
    "input_datetime": {"set_datetime"},
    "input_button":  {"press"},
    "counter":       {"increment", "decrement", "reset"},
    "timer":         {"start", "pause", "cancel"},
    "group":         {"turn_on", "turn_off", "toggle"},
}

READ_ONLY_DOMAINS: set[str] = {"sensor", "binary_sensor", "schedule"}
SUPPORTED_DOMAINS: set[str] = set(ALLOWED_SERVICES) | READ_ONLY_DOMAINS

# Keys that could bypass the entity allowlist if forwarded to HA
FORBIDDEN_DATA_KEYS = {"entity_id", "device_id", "area_id", "floor_id", "label_id"}


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class TokenCreateRequest(BaseModel):
    label: str = Field(..., min_length=1, max_length=200)
    slug: str | None = Field(default=None, pattern=r"^[a-z0-9_-]{1,64}$")
    entity_ids: list[str] = Field(..., min_length=1)
    starts_at: int | None = None          # NEW — epoch seconds, None = active now
    expires_in_seconds: int = Field(..., gt=0)
    ip_allowlist: list[str] | None = None
    pin: str | None = Field(default=None, min_length=4, max_length=20)
    remember_pin: bool = True
    # Entities within entity_ids that require the guest to be near the
    # property (per HA's home zone) before a command on them is allowed.
    # Not restricted to a fixed domain — e.g. a helper button wired to a
    # door relay can be gated the same way a native lock would be.
    proximity_entity_ids: list[str] = Field(default_factory=list)


class TokenUpdateEntitiesRequest(BaseModel):
    entity_ids: list[str] = Field(..., min_length=1)
    proximity_entity_ids: list[str] = Field(default_factory=list)


class TokenUpdateExpiryRequest(BaseModel):
    expires_in_seconds: int = Field(..., gt=0)


class TokenUpdatePinRequest(BaseModel):
    pin: str | None = Field(default=None, min_length=4, max_length=20)
    remember_pin: bool = True


class TemplateCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    entity_ids: list[str] = Field(..., min_length=1)


class TemplateResponse(BaseModel):
    id: str
    name: str
    entity_ids: list[str]
    created_at: int


class CommandRequest(BaseModel):
    entity_id: str
    service: str  # e.g. "light.turn_on"
    data: dict[str, Any] = Field(default_factory=dict)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class TokenResponse(BaseModel):
    id: str
    slug: str
    label: str
    created_at: int
    starts_at: int | None = None          # NEW
    expires_at: int
    revoked: bool
    last_accessed: int | None
    ip_allowlist: list[str] | None
    entity_count: int
    entity_ids: list[str] | None = None
    pin: str | None = None
    remember_pin: bool = True
    require_proximity: bool = False       # true if ANY entity below requires proximity
    proximity_entity_ids: list[str] | None = None
    has_access_code: bool = False
    access_code: str | None = None
