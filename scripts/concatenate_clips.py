"""
scripts/concatenate_clips.py

Concatenate all .mp4 clips in a directory into a single video using ffmpeg.
"""

import os
import sys
import glob
import subprocess
import logging
import argparse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

def concatenate_clips(input_dir: str, output_file: str) -> None:
    """
    Finds all .mp4 files in input_dir (sorted by name), writes an ffmpeg concat list,
    and runs ffmpeg to produce output_file.
    """
    # Validate input directory
    if not os.path.isdir(input_dir):
        raise RuntimeError(f"Input directory not found: {input_dir}")

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    # Collect .mp4 files
    pattern = os.path.join(input_dir, "*.mp4")
    clips = sorted(glob.glob(pattern))
    if not clips:
        raise RuntimeError(f"No .mp4 files found in {input_dir}")
    logging.info(f"Found {len(clips)} clips to concatenate.")

    # Prepare the concat list file
    list_path = os.path.join(input_dir, "concat_list.txt")
    with open(list_path, "w", encoding="utf-8") as f:
        for clip in clips:
            abs_path = os.path.abspath(clip)
            # ffmpeg expects: file '/absolute/path/to/clip.mp4'
            f.write(f"file '{abs_path}'\n")
    logging.info(f"Wrote concat list to: {list_path}")

    # Build and run ffmpeg concat command
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_path,
        "-c", "copy",
        output_file
    ]
    logging.info(f"Running ffmpeg to concatenate clips into: {output_file}")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="ignore")
        logging.error(f"ffmpeg concat failed:\n{stderr}")
        raise RuntimeError(f"ffmpeg concat error: {stderr}")

    logging.info(f"Successfully created concatenated video: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Concatenate all .mp4 clips in a directory into one video."
    )
    parser.add_argument(
        "--input-dir", "-i", required=True,
        help="Directory containing .mp4 clips to concatenate."
    )
    parser.add_argument(
        "--output-file", "-o", default="outputs/assembled/combined.mp4",
        help="Path to write the combined video."
    )
    args = parser.parse_args()

    try:
        concatenate_clips(args.input_dir, args.output_file)
    except Exception as e:
        logging.error(f"Concatenation failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()