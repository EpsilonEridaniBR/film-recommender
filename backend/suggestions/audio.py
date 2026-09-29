"""Validate and normalise uploaded audio explanations with ffmpeg."""

import json
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile

# Allow a little slack over the limit for encoder padding.
DURATION_TOLERANCE_SECONDS = 0.5


class AudioError(Exception):
    pass


def _run(args, timeout=60):
    try:
        return subprocess.run(
            args, capture_output=True, check=True, timeout=timeout
        ).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise AudioError("That file couldn't be read as audio.") from exc


def probe_duration(path):
    output = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "format=duration:stream=codec_type",
            "-of",
            "json",
            str(path),
        ]
    )
    info = json.loads(output or b"{}")
    if not info.get("streams"):
        raise AudioError("That file has no audio.")
    try:
        return float(info["format"]["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AudioError("Couldn't work out how long that clip is.") from exc


def process_upload(upload):
    """Returns (ContentFile of mono AAC .m4a, duration in ms).
    Raises AudioError if the upload is too big, too long, or not audio."""
    if upload.size > settings.AUDIO_MAX_BYTES:
        raise AudioError(
            f"Audio files can be at most {settings.AUDIO_MAX_BYTES // (1024 * 1024)} MB."
        )

    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "upload"
        with source.open("wb") as f:
            for chunk in upload.chunks():
                f.write(chunk)

        if (
            probe_duration(source)
            > settings.AUDIO_MAX_SECONDS + DURATION_TOLERANCE_SECONDS
        ):
            raise AudioError(
                f"Audio clips can be at most {settings.AUDIO_MAX_SECONDS} seconds."
            )

        output = Path(tmp) / "clip.m4a"
        _run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(source),
                "-vn",  # drop any video/cover art
                "-map_metadata",
                "-1",  # strip metadata (location, device, ...)
                "-ac",
                "1",
                "-c:a",
                "aac",
                "-b:a",
                "64k",
                "-t",
                str(settings.AUDIO_MAX_SECONDS),
                "-movflags",
                "+faststart",
                str(output),
            ]
        )
        duration_ms = round(probe_duration(output) * 1000)
        return ContentFile(output.read_bytes(), name="clip.m4a"), duration_ms
