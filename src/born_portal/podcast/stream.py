import logging
import aiofiles
from blacksheep import Request, file as file_response
from blacksheep.server.responses import ContentDispositionType


logger = logging.getLogger(__name__)


def audio(file_path, content_type="audio/mpeg"):
    async def handler(request: Request):
        logger.info(
            "Audio request: path=%s",
            request.url.path.decode() if isinstance(request.url.path, bytes) else request.url.path,
        )

        async with aiofiles.open(file_path, "rb") as f:
            data = await f.read()

        return file_response(data, content_type, content_disposition=ContentDispositionType.INLINE)
    return handler
