"""Tests for the ffmpeg MCP server wiring.

Verifies the server registers every media tool with a sane schema, and that a
missing source surfaces as an MCP error (no real ffmpeg in CI — running an
actual transcode is the integration suite's job against the live sidecar).
"""

from __future__ import annotations

import pytest

from src import server

_EXPECTED_TOOLS = {
    "get_media_info",
    "extract_audio",
    "clip",
    "transcode",
    "scale",
    "extract_frames",
    "thumbnail",
}


@pytest.mark.asyncio
async def test_all_media_tools_are_registered() -> None:
    names = {t.name for t in await server.mcp.list_tools()}
    assert names >= _EXPECTED_TOOLS


@pytest.mark.asyncio
async def test_clip_tool_schema_requires_src_and_start() -> None:
    tools = await server.mcp.list_tools()
    clip = next(t for t in tools if t.name == "clip")
    props = clip.inputSchema["properties"]
    assert "src" in props and "start" in props
    required = clip.inputSchema.get("required", [])
    assert "src" in required and "start" in required


def test_missing_source_raises(tmp_path) -> None:
    from src.ffmpeg_ops import FFmpegError

    with pytest.raises(FFmpegError):
        server.get_media_info(str(tmp_path / "absent.mp4"))
