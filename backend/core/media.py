"""Serve uploaded media in development, with HTTP Range support.

iOS's audio player only plays files from servers that answer Range requests
(206 Partial Content), which Django's own static file view doesn't. Production
serves audio from Spaces, which supports them, so this is DEBUG only.
"""

import mimetypes
import re
from pathlib import Path

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.http import Http404, HttpResponse
from django.utils._os import safe_join
from django.views.static import serve

RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


def serve_media(request, path):
    try:
        full_path = Path(safe_join(settings.MEDIA_ROOT, path))
    except SuspiciousFileOperation:  # Tried to escape MEDIA_ROOT.
        raise Http404
    match = RANGE.match(request.headers.get("Range", ""))
    if not match or not full_path.is_file():
        response = serve(request, path, document_root=settings.MEDIA_ROOT)
        response["Accept-Ranges"] = "bytes"
        return response

    size = full_path.stat().st_size
    first, last = match.groups()
    if first:
        start, end = int(first), int(last) if last else size - 1
    elif last:  # "bytes=-500": the last 500 bytes.
        start, end = max(size - int(last), 0), size - 1
    else:
        start, end = 0, size - 1
    end = min(end, size - 1)
    if start > end:
        response = HttpResponse(status=416)
        response["Content-Range"] = f"bytes */{size}"
        return response

    with full_path.open("rb") as file:
        file.seek(start)
        data = file.read(end - start + 1)
    content_type = mimetypes.guess_type(full_path)[0] or "application/octet-stream"
    response = HttpResponse(data, status=206, content_type=content_type)
    response["Content-Range"] = f"bytes {start}-{end}/{size}"
    response["Accept-Ranges"] = "bytes"
    return response
