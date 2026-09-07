"""Toolspace sidecar (ffmpeg) — MCP server over Streamable HTTP.

Exposes structured ffmpeg/ffprobe operations as MCP tools the workspace agent
calls over ``http://localhost:8094/mcp`` (the containers share the pod network
namespace). Moves ffmpeg — ~400 MB of llvm/mesa/codec libraries, the single
biggest slice of the workspace image — out of the per-chat main container, the
same way LibreOffice moved to the office sidecar. The agent names a path on the
shared tenant PVC; this sidecar reads/writes it in place and the RPC carries
only the path + verdict (zero-copy data plane).

Transport is Streamable HTTP (not stdio) because the server lives in a separate
container from the agent. The tool surface IS the agent-facing contract — the
typed signatures + docstrings tell the agent when/how to use each op.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from typing import Any

import loopwatch
import toollog
from mcp.server.fastmcp import FastMCP

from src import ffmpeg_ops
from src.ffmpeg_ops import FFmpegError

log = logging.getLogger("workspace-tool-ffmpeg")

HOST = "0.0.0.0"  # noqa: S104 - pod-local bind; nothing injects a host, the pod netns is the fence
PORT = int(os.environ["WORKSPACE_TOOL_PORT"])

mcp = FastMCP("ffmpeg", host=HOST, port=PORT, lifespan=loopwatch.lifespan)


def _logged(op: str, fn: Callable[..., str], **kwargs: Any) -> str:
    """Run an op, emitting one structured line per call (keys match the
    office/ocr sidecars so Loki charts error rate without per-pod scraping)."""
    started = time.monotonic()
    try:
        result = fn(**kwargs)
    except FFmpegError as exc:
        log.warning(
            "tool=ffmpeg op=%s outcome=error dur_ms=%d err=%s",
            op,
            int((time.monotonic() - started) * 1000),
            exc,
        )
        detail = f": {exc.stderr.strip()}" if exc.stderr else ""
        raise FFmpegError(f"{exc}{detail}") from exc
    log.info("tool=ffmpeg op=%s outcome=ok dur_ms=%d", op, int((time.monotonic() - started) * 1000))
    return result


@mcp.tool()
def get_media_info(path: str) -> str:
    """Probe a media file and return its metadata as JSON (duration, container,
    and per-stream codec/dimensions/fps/bitrate). Use this first to learn what
    you're working with before clipping/transcoding.

    Args:
        path: Absolute path to the media file on the shared workspace volume.
    """
    return _logged("get_media_info", ffmpeg_ops.get_media_info, path=path)


@mcp.tool()
def extract_audio(src: str, to: str = "mp3", dst: str | None = None) -> str:
    """Extract the audio track from a video/media file.

    Args:
        src: Absolute path to the source media on the shared volume.
        to: Output audio format — mp3 (default), wav, m4a, flac, ogg.
        dst: Optional output path; defaults to ``<src-stem>.<to>`` next to src.

    Returns: the absolute path of the written audio file.
    """
    return _logged("extract_audio", ffmpeg_ops.extract_audio, src=src, to=to, dst=dst)


@mcp.tool()
def clip(
    src: str,
    start: str,
    end: str | None = None,
    duration: str | None = None,
    dst: str | None = None,
) -> str:
    """Trim a media file to a time range without re-encoding (fast, lossless).

    Args:
        src: Absolute path to the source media on the shared volume.
        start: Start time as ``HH:MM:SS[.ms]`` or seconds.
        end: Optional end time (same format). Pass end OR duration, not both.
        duration: Optional length (same format) instead of an explicit end.
        dst: Optional output path; defaults to ``<src-stem>.clip<ext>``.

    Returns: the absolute path of the trimmed file.
    """
    return _logged(
        "clip", ffmpeg_ops.clip, src=src, start=start, end=end, duration=duration, dst=dst
    )


@mcp.tool()
def transcode(src: str, to: str, dst: str | None = None) -> str:
    """Convert a media file to another container/codec (e.g. mov→mp4, mp4→webm,
    video→gif). Re-encodes, so slower than clip.

    Args:
        src: Absolute path to the source media on the shared volume.
        to: Target format/extension — mp4, webm, mkv, mov, gif, mp3, ...
        dst: Optional output path; defaults to ``<src-stem>.<to>``.

    Returns: the absolute path of the converted file.
    """
    return _logged("transcode", ffmpeg_ops.transcode, src=src, to=to, dst=dst)


@mcp.tool()
def scale(src: str, width: int, height: int = -1, dst: str | None = None) -> str:
    """Resize a video. Pass ``height=-1`` (default) to keep the aspect ratio.

    Args:
        src: Absolute path to the source video on the shared volume.
        width: Target width in pixels.
        height: Target height in pixels, or -1 to auto-compute from the aspect.
        dst: Optional output path; defaults to ``<src-stem>.<width>w<ext>``.

    Returns: the absolute path of the resized video.
    """
    return _logged("scale", ffmpeg_ops.scale, src=src, width=width, height=height, dst=dst)


@mcp.tool()
def extract_frames(src: str, fps: float = 1.0, fmt: str = "png", dst_dir: str | None = None) -> str:
    """Export still frames from a video at ``fps`` frames per second — useful for
    pulling stills out of a CCTV walkthrough clip in a tender.

    Args:
        src: Absolute path to the source video on the shared volume.
        fps: Frames to export per second of video (default 1).
        fmt: Image format — png (default), jpg, webp.
        dst_dir: Optional output directory; defaults to ``<src-stem>_frames/``.

    Returns: the absolute path of the directory holding ``frame_NNNN.<fmt>``.
    """
    return _logged(
        "extract_frames", ffmpeg_ops.extract_frames, src=src, fps=fps, fmt=fmt, dst_dir=dst_dir
    )


@mcp.tool()
def thumbnail(src: str, at: str = "00:00:01", dst: str | None = None) -> str:
    """Grab a single poster frame at timestamp ``at`` as a JPEG.

    Args:
        src: Absolute path to the source video on the shared volume.
        at: Timestamp as ``HH:MM:SS`` or seconds (default 1s in).
        dst: Optional output path; defaults to ``<src-stem>.thumb.jpg``.

    Returns: the absolute path of the thumbnail image.
    """
    return _logged("thumbnail", ffmpeg_ops.thumbnail, src=src, at=at, dst=dst)


def main() -> None:
    """Run the MCP server forever over Streamable HTTP. Blocks; entrypoint."""
    toollog.configure("ffmpeg")
    log.info("workspace-tool-ffmpeg MCP server on %s:%d (/mcp)", HOST, PORT)
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
