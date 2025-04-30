"""
scripts/retrieve_clips.py

Provides functionality to extract a time‐range clip from a media file
using ffmpeg. Generates a unique filename per source/start/end triple
and handles errors cleanly.
"""

import os
import subprocess
import sys
import logging
from urllib.parse import urlparse, unquote

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

def generate_output_filename(source_uri: str, start_sec: float, end_sec: float, output_dir: str) -> str:
    """
    Generate a unique output filename for the clip.

    Args:
        source_uri: Path to the original media file.
        start_sec: Clip start time in seconds.
        end_sec: Clip end time in seconds.
        output_dir: Directory where the clip should be saved.

    Returns:
        Full path for the new clip file, e.g., "outputs/clips/video_0010_0020.mp4".
    """
    base = os.path.splitext(os.path.basename(source_uri))[0]
    start_i = int(start_sec)
    end_i = int(end_sec)
    filename = f"{base}_{start_i:04d}_{end_i:04d}.mp4"
    return os.path.join(output_dir, filename)

def extract_clip(source_uri: str, start_sec: float, end_sec: float, output_dir: str = "outputs/clips") -> str:
    """
    Extracts a segment from the media file with ffmpeg.

    Args:
        source_uri: Path or file:// URI to input media.
        start_sec: Start time (seconds).
        end_sec: End time (seconds).
        output_dir: Where to write the extracted clip.

    Returns:
        The path to the saved clip, or raises RuntimeError on failure.
    """
    # Handle file:// URIs by converting to local file paths
    if source_uri.startswith("file://"):
        parsed = urlparse(source_uri)
        path = unquote(parsed.path)
        # On Windows, strip leading slash from "/C:/" paths
        if os.name == "nt" and path.startswith("/") and len(path) > 2 and path[2] == ":":
            path = path[1:]
        source_uri = path

    logging.info(
        f"extract_clip() called with source_uri={source_uri!r}, "
        f"start_sec={start_sec}, end_sec={end_sec}, output_dir={output_dir!r}"
    )

    # Validate inputs
    if start_sec < 0 or end_sec <= start_sec:
        raise ValueError(f"Invalid time range: start={start_sec}, end={end_sec}")

    os.makedirs(output_dir, exist_ok=True)
    output_path = generate_output_filename(source_uri, start_sec, end_sec, output_dir)
    cmd = [
        "ffmpeg",
        "-y",                     # overwrite output
        "-ss", str(start_sec),    # start time
        "-i", source_uri,         # input file
        "-to", str(end_sec),      # end time
        "-c", "copy",             # stream copy for speed/quality
        output_path
    ]

    logging.info(f"Running ffmpeg to extract clip: {cmd}")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="ignore")
        logging.error(f"ffmpeg failed with code {result.returncode}:\n{stderr}")
        raise RuntimeError(f"ffmpeg error: {stderr}")

    logging.info(f"Clip successfully saved to: {output_path}")
    return output_path

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Extract a segment from a media file via ffmpeg"
    )
    parser.add_argument(
        "--source-uri", "-i", required=True,
        help="Path or file:// URI to input media file"
    )
    parser.add_argument(
        "--start-sec", "-s", type=float, required=True,
        help="Start time in seconds (>=0)"
    )
    parser.add_argument(
        "--end-sec", "-e", type=float, required=True,
        help="End time in seconds (> start-sec)"
    )
    parser.add_argument(
        "--output-dir", "-o", default="outputs/clips",
        help="Directory to save extracted clips"
    )
    args = parser.parse_args()

    try:
        clip_path = extract_clip(
            args.source_uri, args.start_sec, args.end_sec, args.output_dir
        )
        logging.info(f"Clip path: {clip_path}")
        print(clip_path)
    except Exception as exc:
        logging.error(f"Extraction failed: {exc}")
        sys.exit(1)

if __name__ == "__main__":
    main()