import asyncio
import os
import re
import uuid
from pathlib import Path

import aiofiles
from blacksheep import (
    ContentDispositionType,
    Request,
    Response,
    StreamedContent,
    redirect,
)
from blacksheep.exceptions import BadRequest, RangeNotSatisfiable
from blacksheep.ranges import InvalidRangeValue, Range

from born_portal.auth.guard import allow_anonymous, auth
from born_portal.core import ADMIN, BASE_URL, SHOWS_CACHE_DIR, SHOWS_DIR, form_value, render

SHOWS_DIR.mkdir(exist_ok=True)

SHOWS_CACHE_DIR.mkdir(exist_ok=True)

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".webm"}

_conversion_status: dict[str, str] = {}


_STREAM_FILE_RE = re.compile(
    r"^(.+)-([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.mp4$"
)


def _list_shows() -> list[dict]:
    """Scan SHOWS_DIR for video files and match against cached streams."""
    # Build stem -> stream_id mapping from cached stream files
    stream_map: dict[str, str] = {}
    for f in SHOWS_CACHE_DIR.iterdir():
        if f.is_file():
            m = _STREAM_FILE_RE.match(f.name)
            if m:
                stream_map[m.group(1)] = m.group(2)

    files = []
    for f in sorted(SHOWS_DIR.iterdir(), key=os.path.getmtime, reverse=True):
        if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS:
            # Skip cached stream files in case they are in the same directory
            if _STREAM_FILE_RE.match(f.name):
                continue

            stream_id = stream_map.get(f.stem)
            status = _conversion_status.get(f.name, "ready" if stream_id else "")

            files.append(
                {
                    "name": f.stem,
                    "filename": f.name,
                    "size": f.stat().st_size,
                    "stream_id": stream_id,
                    "status": status,
                }
            )
    return files


def _stream_filename_pattern(name: str) -> bool:
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
    @auth(roles=[ADMIN])
    async def shows_page(request: Request):
        return render("shows.html", request, shows=_list_shows())

    @app.router.post("/shows/convert")
    @auth(roles=[ADMIN])
    async def shows_convert(request: Request):
        form = await request.form()
        filename = form_value(form, "filename") or ""

        if not filename:
            return render(
                "shows.html",
                request,
                shows=_list_shows(),
                error="No filename provided.",
            )

        filepath = SHOWS_DIR / filename
        if not filepath.exists() or not filepath.is_file():
            return render(
                "shows.html",
                request,
                shows=_list_shows(),
                error=f"File not found: {filename}",
            )

        if filepath.suffix.lower() not in VIDEO_EXTENSIONS:
            return render(
                "shows.html",
                request,
                shows=_list_shows(),
                error=f"Unsupported file type: {filepath.suffix}",
            )

        current_status = _conversion_status.get(filename, "")
        if current_status == "converting":
            return render(
                "shows.html",
                request,
                shows=_list_shows(),
                error=f"Already converting: {filename}",
            )

        stream_id = f"{filepath.stem}-{uuid.uuid4()}"
        output_path = SHOWS_CACHE_DIR / f"{stream_id}.mp4"

        asyncio.create_task(_convert(filepath, output_path))

        return redirect("/shows")

    @app.router.get("/shows/{id}")
    @auth(roles=[ADMIN])
    async def shows_player(request: Request, id: str):
        if not _stream_filename_pattern(id):
            return render("error.html", request, message="Invalid stream ID.")
        shows = [s for s in _list_shows() if s.get("stream_id") == id]
        if len(shows) == 0:
            return render("error.html", request, message="Stream not found.")
        stream_file = (
            SHOWS_CACHE_DIR / f"{shows[0]['name']}-{shows[0]['stream_id']}.mp4"
        )
        if not stream_file.exists() or not stream_file.is_file():
            return render("error.html", request, message="Stream file not found.")

        return render(
            "shows_player.html",
            request,
            id=id,
            title=shows[0]["name"],
            video_url=f"{BASE_URL}/shows/video/{id}.mp4",
        )

    @app.router.get("/shows/video/{id}.mp4")
    @allow_anonymous()
    async def shows_video(request: Request, id: str):
        if not _stream_filename_pattern(id):
            return render("error.html", request, message="Invalid stream ID.")
        shows = [s for s in _list_shows() if s.get("stream_id") == id]
        if len(shows) == 0:
            return render("error.html", request, message="Stream not found.")
        stream_file = (
            SHOWS_CACHE_DIR / f"{shows[0]['name']}-{shows[0]['stream_id']}.mp4"
        )
        if not stream_file.exists() or not stream_file.is_file():
            return render("error.html", request, message="Stream file not found.")

        file_size = stream_file.stat().st_size

        range_header = request.get_first_header(b"range")
        requested_range = None
        if range_header:
            try:
                requested_range = Range.parse(range_header)
            except InvalidRangeValue:
                raise BadRequest("Invalid Range header")
            if requested_range.unit != "bytes" or requested_range.is_multipart:
                # ignore units we don't understand; keep it simple and skip
                # multipart ranges (rare for a single <video> tag request)
                requested_range = None

        headers = [(b"Accept-Ranges", b"bytes")]

        if requested_range:
            if not requested_range.can_satisfy(file_size):
                raise RangeNotSatisfiable()

            part = requested_range.parts[0]
            start = (
                part.start if part.start is not None else file_size - (part.end or 0)
            )
            end = (
                part.end
                if (part.end is not None and part.start is not None)
                else file_size - 1
            )

            content_length = end - start + 1
            status = 206
            headers.append(
                (b"Content-Range", f"bytes {start}-{end}/{file_size}".encode())
            )
        else:
            start, end = 0, file_size - 1
            content_length = file_size
            status = 200

        async def data_provider():
            async with aiofiles.open(stream_file, "rb") as f:
                await f.seek(start)
                remaining = content_length
                while remaining > 0:
                    chunk = await f.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        content = StreamedContent(b"video/mp4", data_provider, content_length)
        headers.append(
            (b"Content-Disposition", ContentDispositionType.INLINE.value.encode())
        )
        return Response(status, headers, content)
