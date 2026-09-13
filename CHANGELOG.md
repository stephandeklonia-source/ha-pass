# Changelog

All notable changes to HAPass are documented in this file, from the original
upstream project ([Rohithkadaveru/ha-pass](https://github.com/Rohithkadaveru/ha-pass))
through the latest state of this fork's `main` branch.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

Starting with this release, versions follow Home Assistant Core's
`YYYY.M.PATCH` scheme instead of semver.

## [2026.9.2] — fork release

Implements [Rohithkadaveru/ha-pass#6](https://github.com/Rohithkadaveru/ha-pass/issues/6).

### Added
- **Entity templates** — save the entity selection from the create-token
  picker as a named template, then load it back into the picker on any
  future token instead of re-searching for the same devices every time.
  Manage saved templates (view/delete) from a link in the create-token
  modal.
- **Rotate link** — new button on each token card that swaps in a fresh,
  unguessable slug while keeping the same entities, expiry, PIN, and
  access history. The old link is invalidated immediately. For handing
  the same access configuration to a new guest (e.g. the next booking in
  the same room) without rebuilding the token from scratch. Any existing
  bypass access-code is cleared as part of the rotation, since it was
  minted for the old link.
- **Helper entities are now assignable to guest tokens** — all of Home
  Assistant's Helpers (Settings → Devices & Services → Helpers) are now
  supported, each with its own guest control widget: Number (slider),
  Text, Dropdown (select), Date/Time, Button, Counter (+/− /reset), and
  Timer (start/pause/cancel). Groups are also supported, controlled the
  same way as a switch. Schedules are read-only (shown as active/inactive,
  matching how sensors already work) since there's no safe simple guest
  action for them.
- **Proximity requirement, per entity** — tap the location pin next to a
  selected entity in the picker to require the guest's browser to report
  a location inside Home Assistant's home zone before that entity's
  command is allowed. Works for any entity, not just locks/alarm — for
  example a helper button wired to a door relay
  (`input_button.open_door`) can be gated without affecting other
  buttons in the same token. Home location/radius is read automatically
  from HA's `zone.home`. Requires HTTPS on the guest link (browsers only
  expose geolocation on a secure context). Soft gate, not a hard
  guarantee — the guest's browser self-reports its coordinates, same
  caveat as the existing IP allowlist.

### Fixed
- **Stale-cached static assets after an update** — `dist.css`, the JS
  files, and the PWA manifest's icon URLs had no cache-busting, so a
  browser (or a caching reverse proxy in front of a custom guest URL)
  could keep serving an old cached copy after upgrading, making the guest
  page look completely unstyled with every normally-hidden section shown
  stacked on the page at once. Every static asset URL, including the
  ones inside `manifest.json`, now carries a `?v=<build>` query param
  that changes with each image build, so updates are always picked up.
- **Service worker cache missed on every request after the above fix** —
  the install-time precache keyed assets by their plain `/static/...`
  path, but pages now request them with a `?v=<build>` suffix, so the
  cache-first lookup never matched and fell through to network on every
  load. The lookup now ignores the query string when matching, so the
  precached copies are used as intended (release-to-release staleness is
  still handled by the service worker's own versioned cache name).
- **Docker build cache busted on every commit** — `GIT_SHA` was set as a
  runtime `ENV` before the `pip install` and app-copy layers, so its
  per-commit value invalidated the Docker/GHA layer cache for those
  layers on every release build. Moved to the end of the runtime stage
  so dependency installs and file copies can still be cached between
  releases.

## [2026.7.8] — fork release

### Added
- **Remember PIN** — a per-token option (default: on) controlling whether a
  guest's PIN entry is remembered across visits. On, the guest gets a
  long-lived cookie and won't be asked again. Off, the PIN session is
  scoped to the current browser visit only — the app still works normally
  during that visit, but the guest is asked for the PIN again the next
  time they open the link. Intended for tokens that never expire, where
  the admin wants the PIN enforced every time rather than just once.
  Toggle it when creating a token or later from its PIN settings.

## [2026.7.7] — fork release

Ported from [j0sh1b/ha-pass](https://github.com/j0sh1b/ha-pass), with two
security fixes over the original implementation (see below).

### Added
- **PIN protection for guest tokens** — an optional PIN can be set per
  token when creating it, or added/changed/removed later from the token
  card. Guests must enter the correct PIN before the guest page unlocks;
  PINs are stored AES-256-GCM encrypted, never in plaintext.
- **Bypass links (access codes)** — for a PIN-protected token, the admin
  can generate a one-off link (`?c=...`) that skips PIN entry entirely,
  for sharing a pre-authenticated link. The PIN itself never appears in
  the URL. Revocable independently of the PIN.
- The encryption key required for PIN storage is generated automatically
  on first start and persisted in the add-on's `/data` folder — no manual
  setup needed.

### Fixed (relative to the upstream implementation)
- **Closed a PIN bypass**: upstream only checked the PIN on the guest HTML
  page — the `/state`, `/stream`, and `/command` endpoints that actually
  control devices had no PIN check at all, so anyone who knew a token's
  slug could skip the PIN completely via direct API calls. All guest
  endpoints now enforce the same PIN gate.
- Added rate limiting on PIN submission attempts (upstream had none) and
  switched to a constant-time comparison to avoid timing side-channels.

## [2026.7.5] — fork release

Includes the color wheel work from `2026.7.1-devRGB` through
`2026.7.4-devRGB` above, now promoted out of dev status, plus:

### Added
- Four new supported entity domains, selectable when creating a guest
  token:
  - **Alarm** (`alarm_control_panel`) — arm Home/Away/Night and disarm,
    with a code entry prompt when the panel requires one
    (`code_format`). Arming modes shown are limited to what the panel's
    `supported_features` actually advertises. Remotely triggering the
    siren (`alarm_trigger`) is deliberately not exposed to guests, same
    reasoning as excluding scripts/automations.
  - **Button** (`button`) — a single Press action.
  - **Time** (`time`) and **Date & Time** (`datetime`) — native HA
    entity types (e.g. an integration's alarm-clock time), editable via
    a standard time/date-time picker.

## [2026.7.4-devRGB] — dev build

### Fixed
- The color wheel's thumb now follows the pointer immediately while
  dragging. It was reading a stale per-entity element ID left over from
  before the wheel moved into a popup sheet, so it silently never updated
  locally — the dot only appeared to "catch up" once Home Assistant's
  state-change echo came back over SSE, which felt choppy.

### Changed
- Live-drag color updates now send up to 3/sec (was 1/sec).
- Guest command rate limit is now two-tiered: 180/min burst allowance plus
  a 3600/hour sustained-use cap, so continuous play (e.g. a kid dragging
  the wheel) isn't cut off by the per-minute limit alone.

## [2026.7.3-devRGB] — dev build

### Changed
- The color wheel is no longer shown inline on the card (too large, made
  the card feel cluttered) — a small color swatch button now sits next to
  the brightness slider, and tapping it opens the wheel in a bottom sheet,
  matching the pattern used elsewhere in the app (e.g. lock confirmation).

## [1-devRGB] — dev build

Test build for the color wheel rate-limit/throttle tuning — not a numbered
release.

### Changed
- Raised the guest command rate limit from 30 to 60 requests/minute, and
  slowed the color wheel's live-drag throttle from ~8/sec to 1/sec, so a
  child (or anyone) dragging the wheel continuously can't exhaust the
  limit and lock themselves out of other commands.

## [2026.7.2] — fork release

### Changed
- Replaced the RGB color picker with a real color wheel, matching
  Lovelace's own light control. Dragging applies the color live (throttled
  to stay within the guest command rate limit), instead of only updating
  once you dismiss a native color-picker dialog.

## [2026.7.1] — fork release

### Added
- Guests can now change the color of RGB-capable lights, not just
  brightness — a color picker appears alongside the brightness slider for
  any light whose `supported_color_modes` includes an RGB/HS/XY mode.

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
