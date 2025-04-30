import subprocess
import sys
import pytest

CLI = [sys.executable, "scripts/pipeline.py"]

@pytest.mark.parametrize(
    "args, expected",
    [
        (["--help"], "Master pipeline CLI"),
        (["ingest", "--help"], "Ingest a media file"),
        (["enrich", "--help"], "Run all enrichment steps"),
        (["query", "--help"], "semantic search"),
        (["extract", "--help"], "Extract a single clip"),
        (["assemble", "--help"], "Concatenate clips"),
        (["clean", "--help"], "Remove all generated clips"),
    ],
)
def test_help_messages(args, expected):
    result = subprocess.run(CLI + args,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True)
    assert expected in result.stdout
    assert result.returncode == 0