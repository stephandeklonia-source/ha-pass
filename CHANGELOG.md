# Changelog

All notable changes to HAPass are documented in this file, from the original
upstream project ([Rohithkadaveru/ha-pass](https://github.com/Rohithkadaveru/ha-pass))
through the latest state of this fork's `main` branch.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.2.8] — fork release

### Fixed
- The connection badge no longer shows "Live" while a token is still on
  its delayed start — it's hidden during the pending preview instead,
  since nothing live is actually connected yet, and reappears normally
  once the guest's access window opens.

## [0.2.7] — fork release

### Changed
- Published container images to `ghcr.io/stephandeklonia-source/ha-pass`
  and pointed `config.yaml` at it, so Home Assistant pulls a prebuilt image
  on update instead of rebuilding from source on every install/update.
  Built and pushed by CI on every `v*.*.*` tag.

### Added
- Guests on a delayed start now see a live-looking preview of their device
  list (names, icons, greyed out) instead of a full-screen "not active yet"
  blocker — the pending state is now a compact bottom banner with the
  countdown, and the card list stays visible (dimmed, non-interactive)
  behind it.

### Fixed
- The preview never fetches or displays real Home Assistant state — cards
  are built from entity IDs alone with a neutral "off" placeholder per
  domain, and incoming SSE state updates are ignored until the token is
  actually active.
- Fixed a pre-existing bug where the guest page called `init()` twice on
  every load (once conditionally, once unconditionally at the bottom of the
  script) — harmless for active tokens beyond a wasted extra fetch and SSE
  connection, but for pending tokens it meant real device state was already
  being fetched in the background the whole time, just hidden behind the
  old full-screen overlay.

## [0.2.6] — fork release

### Fixed
- **Activate Now** no longer leaves an already-open guest tab stuck on its
  countdown: the admin action now pushes a `token_activated` event over the
  guest's SSE connection, so the pending screen unlocks immediately instead
  of only updating on the tab's own timer or a manual page reload.

## [0.2.5] — fork release

Changes made in this fork on top of upstream `v0.2.4`, not present upstream.

### Added
- Delayed / scheduled token start (`starts_at`): guest tokens can now be
  created with a future start time. Guests see a "Not Active Yet" countdown
  screen until the window opens, and the admin dashboard shows a
  **Scheduled** badge with the time remaining.
- Migration `003_add_starts_at.py` adding the `starts_at` column to `tokens`.
- `starts_at` support end-to-end: `TokenCreateRequest`/`TokenResponse`
  models, database layer, admin API, and guest PWA pending overlay.
- **Activate Now** button in the admin dashboard: skip a token's remaining
  delayed start and grant access immediately, via a new
  `POST /admin/tokens/{id}/activate` endpoint.

### Fixed
- Token expiry is now anchored to `starts_at` (when set) instead of token
  creation time, so a scheduled token's duration starts counting from its
  actual start time rather than from when the admin created it.
- Removed a hardcoded `image:` reference in `config.yaml` pointing at the
  upstream container registry, so this fork doesn't try to pull upstream's
  published image.

## [0.2.4] — 2026-04-27

### Added
- Guest activity logging: guest page loads and successful commands are
  emitted as events and Home Assistant Logbook entries.
- Recent activity feed on the admin dashboard with expandable history,
  including a fallback label for tokens that have since been deleted.
- IP allowlist enforcement for guest access.

### Changed
- Debounced page-load activity events to avoid noisy duplicate log entries.

## [0.2.3] — 2026-04-26

### Added
- Token duplicate action in the admin dashboard — clone an existing guest
  token's entities/settings into a new one.

## [0.2.2] — 2026-04-26

### Added
- Lock `open` service support (in addition to lock/unlock) for guest control.

### Changed
- Expired tokens are now retained in the database instead of being purged,
  so they can be renewed with the same slug and entity list.

## [0.2.1] — 2026-03-15

### Fixed
- QR codes are now reliably scannable on Android cameras (proper quiet zone
  per ISO 18004, sharp rendering at device pixel ratio, non-clipped finder
  patterns).

## [0.2.0] — 2026-03-15

### Added
- Home Assistant add-on support: `config.yaml`, `repository.yaml`, `DOCS.md`,
  translations, `run.sh`.
- Ingress-aware routing (base path prefix for templates/manifests) and
  ingress auth bypass for HA sidebar access without a separate login.
- Runtime theming via `BRAND_BG`/`BRAND_PRIMARY` env vars, with an
  auto-derived dark mode palette.
- CI: auto-sync add-on version from git tags.

### Changed
- Token revoke moved from `DELETE /tokens/{id}` to `POST /tokens/{id}/revoke`
  and made idempotent; hard delete moved to `DELETE /tokens/{id}`. Unified
  the 410 response detail message to prevent slug enumeration.

### Fixed
- Header spoofing prevention: `X-Ingress-Path` is only trusted when a valid
  `SUPERVISOR_TOKEN` is present.
- CSP adjusted to allow ingress iframe embedding (`frame-ancestors 'self'`).
- Theme-color meta tags now use the configured/derived background color
  instead of a hardcoded value, in both light and dark mode.
- Guest command security: closed a `label_id` bypass of the entity
  allowlist, stopped forwarding raw Home Assistant responses to guests, and
  genericized error details to avoid leaking backend/HA information.
- Fixed deprecated `HTTP_422_UNPROCESSABLE_ENTITY` and `TemplateResponse`
  usages.

## [0.1.0] — 2026-02-26

### Added
- Initial release: Home Assistant guest access proxy providing time-limited,
  scoped device control via shareable links — no HA accounts required.
- Admin dashboard for creating, extending, and revoking guest tokens.
- Guest PWA with real-time state updates over SSE.
