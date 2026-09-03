"""ffmpeg/ffprobe operations for the workspace-tool-ffmpeg sidecar.

Thin, structured wrappers over the ``ffmpeg`` and ``ffprobe`` binaries that run
on files **in place** on the shared tenant PVC — the agent names a path, this
module reads/writes it on the shared mount, and only the path + verdict cross
the MCP wire (zero-copy data plane, mirroring the office/ocr/cad sidecars).

Deliberately NOT a generic "run any ffmpeg command" surface: each function is a
named operation with a typed signature (the agent-facing contract). ffmpeg's
arbitrary-filtergraph power stays off the table so the sidecar can't be coerced
into reading/writing outside the tenant volume.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

_FFMPEG = "/usr/bin/ffmpeg"
_FFPROBE = "/usr/bin/ffprobe"

# Bound every invocation so a pathological input can't wedge the sidecar (and,
# by extension, hold a broker call open). Transcoding a long video is the slow
# case; 10 min is generous headroom for tender-sized media.
_TIMEOUT_S = 600


class FFmpegError(Exception):
    """An ffmpeg/ffprobe invocation failed. Carries stderr for the agent."""

    def __init__(self, message: str, *, stderr: str = "") -> None:
        super().__init__(message)
        self.stderr = stderr


def _run(argv: list[str]) -> str:
    """Run ffmpeg/ffprobe, returning stdout. Raise :class:`FFmpegError` on any
    non-zero exit or timeout, folding stderr in so the agent sees why."""
    try:
        proc = subprocess.run(  # noqa: S603 - fixed binary, list argv, never shell
            argv,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError(f"ffmpeg timed out after {_TIMEOUT_S}s") from exc
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()[-3:]
        raise FFmpegError("ffmpeg failed", stderr="\n".join(tail))
    return proc.stdout


def _require(src: Path) -> Path:
    if not src.is_file():
        raise FFmpegError(f"source not found: {src}")
    return src


def _out(src: Path, dst: str | None, *, suffix: str) -> Path:
    """Resolve an output path: explicit ``dst`` or ``<src-stem>.<suffix>`` next
    to the source on the shared volume."""
    return Path(dst) if dst else src.with_suffix(suffix)


def get_media_info(path: str) -> str:
    """Return ffprobe's JSON for a media file (format + streams)."""
    src = _require(Path(path))
    out = _run(
        [
            _FFPROBE,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(src),
        ]
    )
    # Re-serialize compactly so the agent gets stable, minimal JSON.
    return json.dumps(json.loads(out), separators=(",", ":"))


def extract_audio(src: str, to: str = "mp3", dst: str | None = None) -> str:
    """Extract the audio track to ``to`` (e.g. mp3, wav, m4a, flac, ogg)."""
    source = _require(Path(src))
    out = _out(source, dst, suffix=f".{to.lstrip('.')}")
    _run([_FFMPEG, "-y", "-i", str(source), "-vn", str(out)])
    return str(out)


def clip(
    src: str,
    start: str,
    *,
    end: str | None = None,
    duration: str | None = None,
    dst: str | None = None,
) -> str:
    """Trim ``[start, end)`` (or ``start`` + ``duration``) without re-encoding.

    ``start``/``end``/``duration`` accept ``HH:MM:SS[.ms]`` or seconds. Exactly
    one of ``end``/``duration`` may be given; omit both to clip to the end.
    """
    if end and duration:
        raise FFmpegError("pass only one of end / duration")
    source = _require(Path(src))
    out = _out(source, dst, suffix=f".clip{source.suffix}")
    argv = [_FFMPEG, "-y", "-ss", start, "-i", str(source)]
    if end:
        argv += ["-to", end]
    elif duration:
        argv += ["-t", duration]
    argv += ["-c", "copy", str(out)]
    _run(argv)
    return str(out)


def transcode(src: str, to: str, dst: str | None = None) -> str:
    """Convert a media file to another container/codec by extension (e.g. mp4,
    webm, mkv, gif, mp3)."""
    source = _require(Path(src))
    out = _out(source, dst, suffix=f".{to.lstrip('.')}")
    if out == source:
        raise FFmpegError("output would overwrite the source; pass a distinct dst")
    _run([_FFMPEG, "-y", "-i", str(source), str(out)])
    return str(out)


def scale(src: str, width: int, height: int = -1, dst: str | None = None) -> str:
    """Resize video to ``width`` x ``height``. ``height=-1`` keeps the aspect
    ratio (auto-computed, rounded to even)."""
    source = _require(Path(src))
    out = _out(source, dst, suffix=f".{width}w{source.suffix}")
    _run([_FFMPEG, "-y", "-i", str(source), "-vf", f"scale={width}:{height}", str(out)])
    return str(out)


def extract_frames(src: str, fps: float = 1.0, fmt: str = "png", dst_dir: str | None = None) -> str:
    """Export frames at ``fps`` per second into ``dst_dir`` (default: a
    ``<stem>_frames/`` dir next to the source). Returns the directory path."""
    source = _require(Path(src))
    out_dir = Path(dst_dir) if dst_dir else source.with_name(f"{source.stem}_frames")
    out_dir.mkdir(parents=True, exist_ok=True)
    _run(
        [_FFMPEG, "-y", "-i", str(source), "-vf", f"fps={fps}", str(out_dir / f"frame_%04d.{fmt}")]
    )
    return str(out_dir)


def thumbnail(src: str, at: str = "00:00:01", dst: str | None = None) -> str:
    """Grab a single frame at timestamp ``at`` (``HH:MM:SS`` or seconds) as a
    JPEG poster image."""
    source = _require(Path(src))
    out = _out(source, dst, suffix=".thumb.jpg")
    _run([_FFMPEG, "-y", "-ss", at, "-i", str(source), "-frames:v", "1", str(out)])
    return str(out)
