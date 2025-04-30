import os
import pytest
import shutil
import subprocess

from scripts.retrieve_clips import generate_output_filename, extract_clip


def test_generate_output_filename_int(tmp_path):
    out = generate_output_filename("video.mp4", 10, 20, str(tmp_path))
    # Should use two‐decimal formatting: 10.00 → 10p00, 20.00 → 20p00
    expected = os.path.join(str(tmp_path), "video_10p00_20p00.mp4")
    assert out == expected


def test_generate_output_filename_decimal(tmp_path):
    out = generate_output_filename("my/video.mp4", 5.5, 7.25, str(tmp_path))
    name = os.path.basename(out)
    assert "5p50" in name and "7p25" in name


def test_extract_clip_ffmpeg_missing(monkeypatch):
    monkeypatch.setattr(shutil, 'which', lambda x: None)
    with pytest.raises(RuntimeError):
        extract_clip("video.mp4", 0, 1)


def test_extract_clip_file_uri(monkeypatch, tmp_path):
    # Simulate ffmpeg present
    monkeypatch.setattr(shutil, 'which', lambda x: x)

    # Simulate successful ffmpeg run
    class FakeResult:
        returncode = 0
        stderr = b''

    monkeypatch.setattr(subprocess, 'run', lambda *args, **kw: FakeResult())

    clip = extract_clip("file:///C:/path/video.mp4", 0, 2, str(tmp_path))
    assert clip.startswith(str(tmp_path))
    assert clip.endswith(".mp4")
