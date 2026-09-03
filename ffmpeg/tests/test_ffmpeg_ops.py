"""Unit tests for the ffmpeg op helpers.

Covers the validation + path-resolution logic that runs BEFORE any ffmpeg
invocation (so no ffmpeg binary is needed), plus one mocked success path that
asserts the argv we hand to ffmpeg is well-formed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src import ffmpeg_ops
from src.ffmpeg_ops import FFmpegError


def test_out_defaults_next_to_source() -> None:
    src = Path("/home/agent/clip.mov")
    assert ffmpeg_ops._out(src, None, suffix=".mp3") == Path("/home/agent/clip.mp3")
    assert ffmpeg_ops._out(src, "/home/agent/x.wav", suffix=".mp3") == Path("/home/agent/x.wav")


def test_require_missing_raises() -> None:
    with pytest.raises(FFmpegError, match="source not found"):
        ffmpeg_ops._require(Path("/nope/missing.mp4"))


def test_clip_rejects_both_end_and_duration(tmp_path) -> None:
    src = tmp_path / "v.mp4"
    src.write_bytes(b"\x00")  # exists so _require passes; validation fails before ffmpeg
    with pytest.raises(FFmpegError, match="only one of end / duration"):
        ffmpeg_ops.clip(str(src), "0", end="5", duration="5")


def test_transcode_rejects_overwriting_source(tmp_path) -> None:
    src = tmp_path / "v.mp4"
    src.write_bytes(b"\x00")
    with pytest.raises(FFmpegError, match="overwrite the source"):
        ffmpeg_ops.transcode(str(src), "mp4")  # same extension => out == src


def test_extract_audio_builds_expected_argv(tmp_path, monkeypatch) -> None:
    src = tmp_path / "talk.mov"
    src.write_bytes(b"\x00")
    captured: dict[str, list[str]] = {}

    def fake_run(argv: list[str]) -> str:
        captured["argv"] = argv
        return ""

    monkeypatch.setattr(ffmpeg_ops, "_run", fake_run)
    out = ffmpeg_ops.extract_audio(str(src), to="mp3")

    assert out == str(tmp_path / "talk.mp3")
    argv = captured["argv"]
    assert argv[0].endswith("ffmpeg")
    assert "-vn" in argv  # drop video, keep audio
    assert argv[-1] == str(tmp_path / "talk.mp3")
