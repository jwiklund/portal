import asyncio
from urllib.parse import unquote

import os
from pathlib import Path

from blacksheep import Request, file
from blacksheep.server.responses import redirect

from born_portal.core import render

PODCAST_DIR = Path("podcasts")
PODCAST_DIR.mkdir(exist_ok=True)


import re


def _safe_filename(name: str) -> str:
    """Strip everything except letters, numbers, spaces, dots, and hyphens."""
    return re.sub(r"[^a-zA-Z0-9 ._\-]", "", name)


def _clean_filenames():
    """Rename files in PODCAST_DIR to safe names if needed."""
    for f in list(PODCAST_DIR.iterdir()):
        if f.is_file() and f.suffix in (".mp3", ".m4a", ".ogg", ".wav", ".opus"):
            safe = _safe_filename(f.name)
            if safe != f.name:
                f.rename(PODCAST_DIR / safe)


def _list_podcasts() -> list[dict]:
    mime_map = {
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".ogg": "audio/ogg",
        ".opus": "audio/opus",
        ".wav": "audio/wav",
    }
    files = []
    for f in sorted(PODCAST_DIR.iterdir(), key=os.path.getmtime, reverse=True):
        if f.is_file() and f.suffix in mime_map:
            files.append(
                {
                    "name": f.name,
                    "size": f.stat().st_size,
                    "path": f"/podcasts/audio/{f.name}",
                    "mime_type": mime_map[f.suffix],
                }
            )
    return files


def register_routes(app):
    @app.router.get("/podcasts")
    async def podcast_page(request: Request):
        return render("podcasts.html", user=user(request), podcasts=_list_podcasts())

    @app.router.post("/podcasts/download")
    async def podcast_download(request: Request):
        form = await request.form()
        url = form.get("url", "")

        if not url:
            return render(
                "podcasts.html",
                user=user(request),
                podcasts=_list_podcasts(),
                error="Please enter a URL",
            )

        try:
            proc = await asyncio.create_subprocess_exec(
                "yt-dlp",
                "-x",
                "--audio-format",
                "mp3",
                "-o",
                f"{PODCAST_DIR}/%(title)s.%(ext)s",
                url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                return render(
                    "podcasts.html",
                    user=user(request),
                    podcasts=_list_podcasts(),
                    error=f"Download failed: {stderr.decode()[:500]}",
                )

            _clean_filenames()
        except FileNotFoundError:
            return render(
                "podcasts.html",
                user=user(request),
                podcasts=_list_podcasts(),
                error="yt-dlp not found. Please install it first.",
            )

        return redirect("/podcasts")

    @app.router.post("/podcasts/delete")
    async def podcast_delete(request: Request):
        form = await request.form()
        filename = form.get("filename", "")

        if filename:
            # Only allow safe filenames to prevent path traversal
            safe = _safe_filename(filename)
            if filename != safe:
                return render(
                    "error.html",
                    user=user(request),
                    message="Invalid filename.",
                )
            filepath = PODCAST_DIR / filename
            if filepath.exists() and filepath.is_file():
                filepath.unlink()

        return redirect("/podcasts")

    @app.router.get("/podcasts/audio/{filename}")
    async def podcast_audio(request: Request, filename: str):
        filename = unquote(filename)
        # Only allow safe filenames
        safe = _safe_filename(filename)
        if filename != safe:
            return render("error.html", user=user(request), message="Invalid filename.")

        filepath = PODCAST_DIR / filename
        if not filepath.exists() or not filepath.is_file():
            return render("error.html", user=user(request), message="File not found")

        content_type = "audio/mpeg"
        if filename.endswith(".m4a"):
            content_type = "audio/mp4"
        elif filename.endswith(".ogg"):
            content_type = "audio/ogg"
        elif filename.endswith(".opus"):
            content_type = "audio/opus"
        elif filename.endswith(".wav"):
            content_type = "audio/wav"

        return file(str(filepath), content_type=content_type)


def user(request: Request) -> dict:
    email = request.session.get("user")
    return {"name": email.split("@")[0], "email": email}
