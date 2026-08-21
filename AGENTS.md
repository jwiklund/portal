# Born Portal

## Project structure

```
src/born_portal/
  main.py          # App entry point, CLI subcommands, route registration
  core.py          # Env var config, Jinja2 environment, render() helper
  auth.py          # AuthMiddleware + Google OAuth routes (/login, /auth/google, /auth/callback, /logout)
  routes.py        # Root redirect (/ → /events)
  event/           # Event CRUD: import (parse from URL), edit, delete, SQLite store
    model.py       # EventData dataclass
    store.py       # EventStore — SQLite persistence
    biletto.py     # HTMLParser for billetto.se
    event.py       # Generic event parser (uses litellm LLM for non-biletto URLs)
    routes.py      # Event web routes
  show/            # Video file management: ffmpeg conversion, streaming with Range support
    routes.py      # Shows web routes + video streaming
  podcast/         # Audio file management: yt-dlp download, delete, serve
    routes.py      # Podcast web routes + audio serving
  utils/
    date_range.py  # Date parsing (Swedish/English/ISO), handles ranges and timezone offsets
templates/         # Jinja2 templates (extends base.html)
tests/             # pytest tests
```

### Infrastructure

- **Database**: `events.db` (SQLite, gitignored) — auto-created by EventStore on first use.
- **Directories**: `shows/` (video source files), `shows_cache/` (converted mp4 streams), `podcasts/` (downloaded audio) — all gitignored via `.gitignore`.
- **Config**: Env vars in `mise.local.toml` (copy from `mise.local.example`). Required: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `SECRET_KEY`. Optional: `ADMIN_USERS`, `MODEL`, `API_BASE`, `BASE_URL`, `SHOWS_DIR`, `SHOWS_CACHE_DIR`.

## Architecture

### Application lifecycle

`main.py:main()` is the CLI entry point. It supports subcommands:
- `serve` (default) — starts uvicorn on port 8080
- `fetch <url>` — parse event URL, print JSON
- `parse` — parse local `biletto.html` for debugging

The `app` object (BlackSheep `Application`) is the ASGI app that uvicorn serves.

### Middleware chain (order matters)

1. **SessionMiddleware** — cookie-based sessions (signed with SECRET_KEY)
2. **AuthMiddleware** — Google OAuth check (redirects to /login if not authenticated)

**Public paths** (no auth required): `/login`, `/auth/google`, `/auth/callback`, `/podcasts/audio/`, `/shows/video/`. The trailing-slash paths use prefix matching — any path starting with those prefixes is public.

### Route registration pattern

Each module exports a `register_routes(app)` function that adds route handlers. Routes are decorated functions defined inside this function. All modules register in `main.py`:

```python
auth.register_routes(app)
routes.register_routes(app)
event.register_routes(app)
podcast.register_routes(app)
show.register_routes(app)
```

### Rendering

All templates use `core.render(template_name, **ctx)` which wraps Jinja2 rendering in a BlackSheep `html()` response. The `user()` helper (in `core.py`) extracts email from the session. Templates always receive `user=user(request)`.

### Data flow

1. **Events**: Import URL → `event.parse(url)` → either Biletto HTMLParser or litellm LLM extraction → `EventData` dataclass → preview/edit form → `EventStore.save()` → SQLite
2. **Shows**: Video files in `shows/` → POST `/shows/convert` → ffprobe check codecs → ffmpeg remux/re-encode → cached mp4 in `shows_cache/` → streaming via Range headers
3. **Podcasts**: URL → yt-dlp extract audio → mp3 in `podcasts/` → serve via `aiofiles`

## Key conventions & gotchas

### Python

- **Python 3.13+** required (uses `from __future__ import annotations` in some files, `|` union types)
- **EventStore requires manual `close()`** — always use `try/finally` pattern (see `event/routes.py` for examples)

### BlackSheep

- Route handlers are **async functions** that take `request: Request` as first arg
- Query params are `dict(request.query)` — values are lists (e.g., `params.get("code", [None])[0]`)
- Form data uses `await request.form()` — returns a dict-like object
- `request.session` is a dict-like object for cookie session data

### Security

- `AuthMiddleware` checks `request.session["user"]` against `ADMIN_USERS` set
- Podcast filenames are sanitized with `_safe_filename()` regex to prevent path traversal

## Testing

Tests are in `tests/` directory. Run with:

```bash
uv run python -m pytest tests/
```

## Editing notes

- **Formatting**: Black + isort (run `mise format`). No config files — uses defaults.
- **LSP**: Ruff server configured in `crush.json` at project root. Diagnostics appear via LSP.
- **No Makefile, no CI config** — this is a personal project.
- **`mise`** is the tool manager (like `direnv` + `asdf`). It sets env vars from `mise.local.toml` and provides shell aliases.
