# Portal

## Project structure

```
src/born_portal/
  main.py          # App entry point, CLI subcommands, route registration
  core.py          # Env var config (ADMIN/VIEWER roles), Jinja2 env, render() helper
  auth/            # Authentication & authorization
    __init__.py    # Re-exports AuthMiddleware, register_routes, @auth wiring
    login.py       # Google OAuth routes (/login, /auth/google, /auth/callback, /logout)
    guard.py       # guardpost SessionAuthHandler, configure() @auth integration
  routes.py        # Root redirect (/ → /upcoming)
  upcoming/        # Upcoming event CRUD: import (parse from URL), edit, delete, SQLite store
    model.py       # UpcomingData dataclass (table: upcoming)
    store.py       # UpcomingStore — SQLite persistence
    biletto.py     # HTMLParser for billetto.se
    upcoming.py    # Generic event parser (uses openai SDK LLM for non-biletto URLs)
    routes.py      # Upcoming web routes
  past/            # Past event CRUD: import from Google Photos, artists, SQLite store
    model.py       # PastData + ArtistData (tables: past, artists, past_artists)
    store.py       # PastStore — SQLite persistence
    photos.py      # Google Photos album scraping
    routes.py      # Past web routes
  show/            # Video file management: ffmpeg conversion, streaming with Range support
    routes.py      # Shows web routes + video streaming
  podcast/         # Audio file management: yt-dlp download, delete, serve
    routes.py      # Podcast web routes + audio serving
  errors/          # Error log: capture exceptions + request context, admin browser
    model.py       # ErrorRecord (table: error_log)
    store.py       # ErrorStore — SQLite persistence
    report.py      # record_error(): capture, redact, truncate, persist
    routes.py      # Global exception handler + /errors admin pages
  notifications/   # Admin notifications: list/read/delete page + add API
    model.py       # Notification (table: notifications)
    store.py       # NotificationStore — SQLite persistence (dedupe by date+title)
    routes.py      # /notifications pages + JSON API; viewing the list marks shown items read
  push/            # Web Push (PWA notifications): subscriptions + delivery
    model.py       # PushSubscription (table: push_subscriptions)
    store.py       # PushSubscriptionStore — SQLite persistence (upsert by endpoint)
    keys.py        # VAPID key pair from env (or a read-only VAPID_KEY_FILE); never writes
    sender.py      # send_notification(): deliver + log failures, drop gone endpoints
    routes.py      # /sw.js service worker, /push/vapid, /push/subscribe, /push/unsubscribe
    sw.js          # Service worker: show push notifications, refresh open pages, handle clicks
  utils/
    date_range.py  # Date parsing (Swedish/English/ISO), handles ranges and timezone offsets
    fetch.py       # Safe public-page fetching (SSRF guard, tracking cleanup, headers, HTML→Markdown)
templates/         # Jinja2 templates (extends base.html)
tests/             # pytest tests
```

### Infrastructure

- **Database**: `portal.db` (SQLite, gitignored) — auto-created by the stores on first use. Its tables are `upcoming`, `past`, `past_artists`, `artists`, `sessions`, `error_log`, `notifications`, and `push_subscriptions`.
- **Directories**: `shows/` (video source files), `shows_cache/` (converted mp4 streams), `podcasts/` (downloaded audio) — all gitignored via `.gitignore`.
- **Config**: Env vars in `mise.local.toml` (copy from `mise.local.example`). Required: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `SECRET_KEY`. Optional: `ADMIN_USERS`, `MODEL`, `OPENROUTER_API_KEY`, `OPENROUTER_API_BASE`, `BASE_URL`, `SHOWS_DIR`, `SHOWS_CACHE_DIR`, `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`, `VAPID_KEY_FILE`.

## Architecture

### Application lifecycle

`main.py:main()` is the CLI entry point. It supports subcommands:
- `serve` (default) — starts uvicorn on port 8080
- `fetch <url>` — parse event URL, print JSON
- `notify <title> [text] [--date YYYY-MM-DD]` — add a notification to the database directly (`-` as text reads stdin; skips duplicates by date + title; pushes to subscribers, awaiting delivery and reporting how many were reached or why it was skipped)
- `vapid-keys [--regenerate] [--systemd]` — print (or create) the web-push VAPID key pair for `mise.local.toml` (`--systemd` prints systemd `Environment=` lines instead, with the PEM private key on a single line)
- `backup [output]` / `restore [date]` — dump/load the SQLite database; `backup` defaults to `backup-YYYY-MM-DD.sql` and `restore` defaults to the latest one

The `app` object (BlackSheep `Application`) is the ASGI app that uvicorn serves.

### Middleware chain (order matters)

1. **SessionMiddleware** — cookie-based sessions (signed with SECRET_KEY)
2. **AuthenticationMiddleware** (from `auth/guard.py` `use_authentication`) — builds a guardpost `Identity` from the session via `SessionAuthHandler`
3. **AuthorizationMiddleware** (from `app.use_authorization`) — enforces `@auth` decorators; anonymous → `UnauthorizedError` → redirect to `/login`
4. **AuthMiddleware** — outer session gate (redirects to `/login` if not authenticated, lets admins through everywhere, viewers to `/view` pages only)

Public paths: `/login`, `/auth/google`, `/auth/callback`, `/spotify/callback`, `/podcasts/audio/`, `/shows/video/`, plus `/manifest.json`, `/icon.svg`, `/icon-180.png`, `/sw.js` (PWA assets).

### Authorization via `@auth`

Handlers are annotated using BlackSheep's built-in authorization (see the [docs](https://www.neoteroi.dev/blacksheep/authorization/)). The default `authenticated` policy (auto-registered by `use_authorization()`) requires a logged-in user, and `roles=[...]` requires any listed role:

```python
from born_portal.auth import auth
from born_portal.core import ADMIN, VIEWER

@app.router.get("/upcoming")
@auth(roles=[ADMIN])
async def upcoming_list(request): ...

@app.router.get("/upcoming/view")
@auth(roles=[VIEWER])
async def view_upcoming_list(request): ...

@app.router.get("/podcasts/audio/{filename}")
@allow_anonymous
async def podcast_audio(request, filename): ...
```

- `@auth(roles=[ADMIN])` — admins only (admins also carry the `VIEWER` role so they can reach view pages).
- `@auth(roles=[VIEWER])` — viewers and admins.
- `@allow_anonymous()` — public (used for PWA assets, audio/video streaming). Must use the parentheses form.
- Anonymous calls to protected handlers raise `UnauthorizedError`, mapped to a redirect to `/login` in `auth/guard.py`.

### Route registration pattern

Each module exports a `register_routes(app)` function that adds route handlers. Routes are decorated functions defined inside this function. All modules register in `main.py`:

```python
auth.register_routes(app)
errors.register_routes(app, engine)
notifications.register_routes(app, engine)
push.register_routes(app, engine)
routes.register_routes(app)
upcoming.register_routes(app, engine)
past.register_routes(app, engine)
playlist.register_routes(app)
podcast.register_routes(app)
show.register_routes(app)
pwa.register_routes(app)
```

### Rendering

All templates use `core.render(template_name, **ctx)` which wraps Jinja2 rendering in a BlackSheep `html()` response. The `user()` helper (in `core.py`) extracts email from the session. Templates always receive `user=user(request)`.

### Templates & styles

Styling is centralized. `base.html` contains the whole shared design system in its `<style>` block; page templates extend it and should only add page-specific rules in `{% block extra_styles %}`, and JS in `{% block extra_scripts %}`.

- **Design tokens**: colors, radii, etc. are CSS custom properties in `:root` (`--bg`, `--surface`, `--surface-2`, `--surface-3`, `--surface-4`, `--border`, `--border-strong`, `--border-hover`, `--focus`, `--text`, `--text-soft`, `--text-dim`, `--text-link`, `--text-muted`, `--text-faint`, `--accent`, `--accent-hover`, `--accent-contrast`, `--green`, `--green-bright`, `--red`, `--red-hover`, `--red-bright`, `--info`, `--info-strong`, `--radius`, `--radius-sm`). Use these instead of hard-coded hex values. (A few third-party-ish accents such as Spotify green remain literal.)
- **Component classes** (reuse these before inventing new ones):
  - Layout: `.page-head` (title + inline actions), `.toolbar`, `.actions`, `.back-link`, `.sr-only`
  - Lists/cards: `.list` (`<ul>`) → `<li>` → `.card` with `.card-head` / `.card-title` / `.card-date` / `.card-meta` / `.card-price` / `.card-body` / `.card-actions`
  - Chips: `.chips` (`<ul>`) → `<li class="chip">`
  - Buttons: `.btn` plus `.btn-secondary`, `.btn-muted`, `.btn-info`, `.btn-danger`, `.btn-sm`
  - Badges: `.badge` plus `.badge-ready` / `.badge-warn` / `.badge-error` / `.badge-muted` / `.badge-new`
  - Forms: `.form`, `.form-group`, `.form-actions`, `.hint`, `.empty`; inputs/textareas styled globally
  - Messages: `.msg` plus `.msg-error` / `.msg-warn` / `.msg-success` / `.msg-info`
  - Metadata: `dl.meta` (grid of `dt`/`dd`), `pre`
- **Semantic markup**: use `<article>` + `<header>` for detail views and list items, `<time>` for dates, `<ul>`/`<li>` for lists (not `<div>` stacks), `<dl>` for label/value metadata, `<figure>`/`<figcaption>` for images and video, and `<nav>` only for actual navigation. `<main id="main">` wraps page content; the site bar is `<header><nav>`.
- **Gotcha — scope nav styles**: the site header nav is styled with `header nav { … }` (not bare `nav { … }`). A page-level `<nav>` (e.g. sort filters) must not inherit the header bar's flex/padding/background; keep new nav rules scoped or class-based.
- **Gotcha — single-row links**: for a list row that is entirely clickable, use one `<a>` wrapping the row content. When using CSS grid with `display: contents`, apply it to the wrapper(s) so the grid items remain the inner cells (see `upcoming.html` `.event-row`). Splitting one row into multiple sibling `<a>` tags drops inherited link colors and makes the row announce twice to screen readers.
- Standalone pages (`login.html`, `error.html`, `shows_player.html`) do **not** extend `base.html`; they keep their own small `<style>` block by design.


### Data flow

1. **Upcoming**: Import URL → `upcoming.parse(url)` → either Biletto HTMLParser or openai SDK LLM extraction → `UpcomingData` dataclass → preview/edit form → `UpcomingStore.save()` → SQLite
2. **Shows**: Video files in `shows/` → POST `/shows/convert` → ffprobe check codecs → ffmpeg remux/re-encode → cached mp4 in `shows_cache/` → streaming via Range headers
3. **Podcasts**: URL → yt-dlp extract audio → mp3 in `podcasts/` → serve via `aiofiles`

## Key conventions & gotchas

### Python

- **Python 3.13+** required (uses `from __future__ import annotations` in some files, `|` union types)
- **Stores require manual `close()`** — always use `try/finally` pattern (see `upcoming/routes.py` for examples)

### BlackSheep

- Route handlers are **async functions** that take `request: Request` as first arg
- Query params are `dict(request.query)` — values are lists (e.g., `params.get("code", [None])[0]`)
- Form data uses `await request.form()` — returns a dict-like object
- `request.session` is a dict-like object for cookie session data

### Security

- `auth/guard.py` maps the session user to guardpost roles (`ADMIN` from `ADMIN_USERS`, `VIEWER` from `VIEW_USERS`); `@auth(roles=...)` enforces them
- `AuthMiddleware` checks `request.session["user"]` against `ADMIN_USERS`/`VIEW_USERS`
- Podcast filenames are sanitized with `_safe_filename()` regex to prevent path traversal

### Error handling

The preferred way to handle an unexpected exception in a request handler is to **catch it, record it, and return a user-level message on the error page**:

```python
from born_portal.errors import record_error

try:
    result = await do_work(...)
except Exception as e:  # noqa: BLE001 - record, then show a friendly message
    await record_error(request, e, context={"url": url})
    return render("error.html", request, message="Something went wrong.")
```

- `record_error(request, exc, context=...)` persists the exception (type, message, full traceback) plus request context (method, path, redacted query string, redacted form/JSON body, user, user agent) into the `error_log` table. It **never raises** and never stores secrets: sensitive keys (`code`, `state`, `token`, `secret`, `password`, `cookie`, `session`, ...) and multipart file contents are masked. Input is truncated. Pass `request=None` for errors outside a request cycle (e.g. background tasks).
- Any exception a handler does **not** catch is caught by the global handler registered in `errors/routes.py`; it logs at ERROR level and returns `error.html` with `USER_ERROR_MESSAGE`. Recording still happens, but without handler-specific context.
- `/errors` (admin-only) lists recent errors and `/errors/{id}` shows the full traceback and input. `POST /errors/clear` empties the log.
- Note: registering a handler for `Exception` marks exceptions as "handled" to BlackSheep, so the global handler logs them itself instead of relying on BlackSheep's default logging.

## Testing

Tests are in `tests/` directory. Run with:

```bash
uv run python -m pytest tests/
```

## Editing notes

- **Formatting**: run `mise format` (Black for code layout, then `ruff check --fix` for imports and other fixes).
- **No Makefile, no CI config** — this is a personal project.
- **`mise`** is the tool manager (like `direnv` + `asdf`). It sets env vars from `mise.local.toml` and provides shell aliases.
