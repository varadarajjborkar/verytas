"""Serving an upload to a page: inline, never cached, and in byte ranges so a video can be played and sought.

Ranges are read from the database with substr, so seeking in a 150 MB video sends and loads two megabytes,
not the whole file. Callers check access first; this only shapes the response.
"""

from __future__ import annotations

import re

from fastapi import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from verytas.models import MediaBlob

# The most one ranged read returns; a player asks again for the rest.
RANGE_CHUNK = 2 * 1024 * 1024
_RANGE = re.compile(r"^bytes=(\d{0,15})-(\d{0,15})$")


async def inline(session: AsyncSession, blob_id: str, media_type: str, size: int, range_header: str | None,
                 *, sandbox: bool = True) -> Response:
    headers = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
               "Content-Disposition": "inline", "Accept-Ranges": "bytes"}
    # Opened on its own, a file can't run anything. A PDF is left to the browser's viewer, which a sandboxed
    # response would stop from drawing it.
    if sandbox and media_type != "application/pdf":
        headers["Content-Security-Policy"] = "default-src 'none'; img-src 'self'; media-src 'self'; sandbox"
    m = _RANGE.match(range_header.strip()) if range_header else None
    if m and (m.group(1) or m.group(2)):
        if m.group(1):
            start = int(m.group(1))
            end = min(int(m.group(2)) if m.group(2) else size - 1, size - 1, start + RANGE_CHUNK - 1)
        else:  # the last N bytes
            start, end = max(0, size - int(m.group(2))), size - 1
        if start >= size or start > end:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
        chunk = await session.scalar(select(func.substr(MediaBlob.data, start + 1, end - start + 1))
                                     .where(MediaBlob.id == blob_id))
        return Response(bytes(chunk or b""), status_code=206, media_type=media_type,
                        headers=headers | {"Content-Range": f"bytes {start}-{end}/{size}"})
    data = await session.scalar(select(MediaBlob.data).where(MediaBlob.id == blob_id))
    return Response(bytes(data or b""), media_type=media_type, headers=headers)
