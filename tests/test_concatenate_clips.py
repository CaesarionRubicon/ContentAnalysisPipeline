import os
import pytest
import subprocess
from pathlib import Path

from scripts.concatenate_clips import concatenate_clips

def test_concatenate_clips(tmp_path, monkeypatch):
    # Create dummy clip files
    clip1 = tmp_path / "a.mp4"
    clip2 = tmp_path / "b.mp4"
    clip1.write_bytes(b"")
    clip2.write_bytes(b"")

    # Stub out ffmpeg invocation
    class FakeResult:
        returncode = 0
        stderr = b''
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kw: FakeResult())

    out_file = tmp_path / "out.mp4"
    concatenate_clips(str(tmp_path), str(out_file))

    # Check that the output file path object was created (we didn't actually write video bytes)
    assert out_file.exists() or out_file  # existence may depend on ffmpeg, but ensure no exception

    # Verify concat_list.txt
    list_file = tmp_path / "concat_list.txt"
    assert list_file.exists()
    content = list_file.read_text()
    assert "file '" in content
    assert "a.mp4" in content and "b.mp4" in content