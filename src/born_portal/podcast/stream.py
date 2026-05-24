import aiofiles
from urllib.parse import unquote
from blacksheep import Request, Response, StreamedContent


CHUNK_SIZE = 64 * 1024


def parse_range(range_header: str, file_size: int):
    """
    Returns (start, end) or None if invalid/missing.
    """
    if not range_header or not range_header.startswith("bytes="):
        return None

    range_val = range_header[6:]
    start_str, end_str = range_val.split("-", 1)

    try:
        start = int(start_str) if start_str else 0
        end = int(end_str) if end_str else file_size - 1
    except ValueError:
        return None

    if start > end or start >= file_size:
        return None

    end = min(end, file_size - 1)
    return start, end


def audio(file_path, content_type="audio/mpeg"):
    file_size = file_path.stat().st_size

    async def handler(request: Request):
        range_header = request.headers.get_first(b"Range")
        range_header = range_header.decode() if range_header else None

        parsed = parse_range(range_header, file_size)

        # -------------------------
        # FULL FILE (no range)
        # -------------------------
        if parsed is None:

            async def full_stream():
                async with aiofiles.open(file_path, "rb") as f:
                    while True:
                        chunk = await f.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        yield chunk

            return Response(
                200,
                [
                    (b"Content-Type", content_type.encode()),
                    (b"Content-Length", str(file_size).encode()),
                    (b"Accept-Ranges", b"bytes"),
                    (b"Cache-Control", b"public, max-age=86400"),
                ],
                StreamedContent(content_type.encode(), full_stream),
            )

        # -------------------------
        # PARTIAL CONTENT (range)
        # -------------------------
        start, end = parsed
        length = end - start + 1

        async def range_stream():
            async with aiofiles.open(file_path, "rb") as f:
                await f.seek(start)
                remaining = length

                while remaining > 0:
                    chunk = await f.read(min(CHUNK_SIZE, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return Response(
            206,
            [
                (b"Content-Type", content_type.encode()),
                (b"Content-Length", str(length).encode()),
                (b"Content-Range", f"bytes {start}-{end}/{file_size}".encode()),
                (b"Accept-Ranges", b"bytes"),
                (b"Cache-Control", b"public, max-age=86400"),
            ],
            StreamedContent(content_type.encode(), range_stream),
        )

    return handler
