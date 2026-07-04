import asyncio
import os
import re
import uuid
from pathlib import Path
from urllib.parse import unquote

import aiofiles
from blacksheep import Request, file
from blacksheep.server.responses import ContentDispositionType, redirect

from born_portal.core import BASE_URL, SHOWS_CACHE_DIR, SHOWS_DIR, render, user

SHOWS_DIR = Path(SHOWS_DIR)
SHOWS_DIR.mkdir(exist_ok=True)

SHOWS_CACHE_DIR = Path(SHOWS_CACHE_DIR)
SHOWS_CACHE_DIR.mkdir(exist_ok=True)

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".webm"}

_conversion_status: dict[str, str] = {}


def _list_shows() -> list[dict]:
    """Scan SHOWS_DIR for video files and match against cached streams."""
    files = []
    for f in sorted(SHOWS_DIR.iterdir(), key=os.path.getmtime, reverse=True):
        if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS:
            stream_id = None
            stem = f.stem
            for sf in sorted(
                SHOWS_CACHE_DIR.iterdir(), key=os.path.getmtime, reverse=True
            ):
                if sf.is_file() and sf.suffix.lower() == ".mp4":
                    if sf.stem.startswith(stem + "-"):
                        stream_id = sf.stem[len(stem) + 1 :]
                        break

            status = _conversion_status.get(f.name, "ready" if stream_id else "")

            files.append(
                {
                    "name": f.stem,
                    "size": f.stat().st_size,
                    "stream_id": stream_id,
                    "status": status,
                }
            )
    return files


def _stream_filename_pattern(name: str) -> str:
    """Validate a stream filename matches 'stem-uuid.mp4' pattern."""
    return bool(
        re.match(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", name
        )
    )


async def _check_codecs(filepath: Path) -> str:
    """Run ffprobe, return 'copy' if all video=h264 and all audio=aac, else 'reencode'."""
    proc = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_name,codec_type",
        "-of",
        "csv=p=0",
        str(filepath),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {stderr.decode()[:500]}")

    output = stdout.decode().strip()
    if not output:
        raise RuntimeError("ffprobe returned no stream info")

    for line in output.splitlines():
        parts = line.split(",")
        if len(parts) != 2:
            continue
        codec_type = parts[1].strip()
        codec_name = parts[0].strip()
        if codec_type == "video" and codec_name != "h264":
            return "reencode"
        if codec_type == "audio" and codec_name != "aac":
            return "reencode"

    return "copy"


async def _convert(filepath: Path, output_path: Path):
    """Run ffmpeg conversion (remux or re-encode) as background task."""
    filename = filepath.name
    try:
        _conversion_status[filename] = "converting"

        mode = await _check_codecs(filepath)

        if mode == "copy":
            cmd = [
                "ffmpeg",
                "-i",
                str(filepath),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(output_path),
                "-y",
            ]
        else:
            cmd = [
                "ffmpeg",
                "-i",
                str(filepath),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                str(output_path),
                "-y",
            ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            _conversion_status[filename] = "error"
            print(f"ffmpeg error for {filename}: {stderr.decode()[:500]}")
        else:
            _conversion_status[filename] = "ready"

    except FileNotFoundError:
        _conversion_status[filename] = "error"
        print(f"ffmpeg/ffprobe not found while converting {filename}")
    except Exception as e:
        _conversion_status[filename] = "error"
        print(f"Conversion error for {filename}: {e}")


def register_routes(app):
    @app.router.get("/shows")
    async def shows_page(request: Request):
        return render("shows.html", user=user(request), shows=_list_shows())

    @app.router.post("/shows/convert")
    async def shows_convert(request: Request):
        form = await request.form()
        filename = form.get("filename", "")

        if not filename:
            return render(
                "shows.html",
                user=user(request),
                shows=_list_shows(),
                error="No filename provided.",
            )

        filepath = SHOWS_DIR / filename
        if not filepath.exists() or not filepath.is_file():
            return render(
                "shows.html",
                user=user(request),
                shows=_list_shows(),
                error=f"File not found: {filename}",
            )

        if filepath.suffix.lower() not in VIDEO_EXTENSIONS:
            return render(
                "shows.html",
                user=user(request),
                shows=_list_shows(),
                error=f"Unsupported file type: {filepath.suffix}",
            )

        current_status = _conversion_status.get(filename, "")
        if current_status == "converting":
            return render(
                "shows.html",
                user=user(request),
                shows=_list_shows(),
                error=f"Already converting: {filename}",
            )

        stream_id = f"{filepath.stem}-{uuid.uuid4()}"
        output_path = SHOWS_CACHE_DIR / f"{stream_id}.mp4"

        asyncio.create_task(_convert(filepath, output_path))

        return redirect("/shows")

    @app.router.get("/shows/{id}")
    async def shows_player(request: Request, id: str):
        if not _stream_filename_pattern(id):
            return render("error.html", message="Invalid stream ID.")
        shows = [s for s in _list_shows() if s.get("stream_id") == id]
        if len(shows) == 0:
            return render("error.html", message="Stream not found.")
        stream_file = (
            SHOWS_CACHE_DIR / f"{shows[0]['name']}-{shows[0]['stream_id']}.mp4"
        )
        print(stream_file)
        if not stream_file.exists() or not stream_file.is_file():
            return render("error.html", message="Stream file not found.")

        return render(
            "shows_player.html",
            id=id,
            title=shows[0]["name"],
            video_url=f"{BASE_URL}/shows/video/{id}.mp4",
        )

    @app.router.get("/shows/video/{id}.mp4")
    async def shows_video(request: Request, id: str):
        filepath = SHOWS_CACHE_DIR / f"{id}.mp4"
        if not filepath.exists() or not filepath.is_file():
            return render("error.html", message="File not found.")

        async with aiofiles.open(filepath, "rb") as f:
            data = await f.read()

        return file(
            data,
            "video/mp4",
            content_disposition=ContentDispositionType.INLINE,
        )
