import os
import subprocess
from pathlib import Path
import pytest

# Define paths
SAMPLE_VIDEO = Path("data/sample/sample.mp4")
OUTPUT_CLIPS_DIR = Path("outputs/clips")
OUTPUT_ASSEMBLED_DIR = Path("outputs/assembled")

@pytest.fixture(scope="function")
def clean_pipeline():
    """Fixture to clean the pipeline before and after the test."""
    subprocess.run(["python", "scripts/pipeline.py", "clean"], check=True)
    yield
    subprocess.run(["python", "scripts/pipeline.py", "clean"], check=True)

def test_pipeline_integration(clean_pipeline):
    """Test the full pipeline integration using the sample video."""
    # Ensure the sample video exists
    assert SAMPLE_VIDEO.exists(), f"Sample video not found at {SAMPLE_VIDEO}"

    # Step 1: Clean the pipeline (handled by fixture)

    # Step 2: Ingest the sample video
    subprocess.run(
        ["python", "scripts/pipeline.py", "ingest", "--file", str(SAMPLE_VIDEO)],
        check=True
    )

    # Step 3: Enrich the data
    subprocess.run(
        ["python", "scripts/pipeline.py", "enrich"],
        check=True
    )

    # Step 4: Query and assemble
    subprocess.run(
        ["python", "scripts/pipeline.py", "query", "test", "-n", "1", "--extract-all", "--assemble"],
        check=True
    )

    # Step 5: Validate outputs
    # Check that at least one .mp4 file exists in outputs/clips
    clips = list(OUTPUT_CLIPS_DIR.glob("*.mp4"))
    assert len(clips) > 0, "No .mp4 files found in outputs/clips"

    # Check that a combined_*.mp4 file exists in outputs/assembled
    assembled_files = list(OUTPUT_ASSEMBLED_DIR.glob("combined_*.mp4"))
    assert len(assembled_files) > 0, "No combined_*.mp4 file found in outputs/assembled"