#!/usr/bin/env python
"""
scripts/pipeline.py

Unified CLI to drive the full content‐analysis pipeline.
"""

import argparse
import subprocess
import sys
import os
import shutil

def run_command(cmd_list):
    """Run a shell command and stream output."""
    proc = subprocess.Popen(cmd_list, stdout=sys.stdout, stderr=sys.stderr)
    proc.communicate()
    if proc.returncode != 0:
        sys.exit(proc.returncode)

def cmd_ingest(args):
    """Ingest media and transcripts."""
    run_command([sys.executable, "scripts/ingest_data.py", "--file", args.file])

def cmd_enrich(args):
    """Run all enrichment steps (embeddings, entities, summaries, tags)."""
    run_command([sys.executable, "scripts/generate_embeddings.py"])
    run_command([sys.executable, "scripts/generate_entities.py"])
    run_command([sys.executable, "scripts/generate_summaries.py"])
    run_command([sys.executable, "scripts/generate_tags.py"])

def cmd_query(args):
    """Perform semantic search, optional extraction and assembly."""
    cmd = [
        sys.executable, "scripts/query_pipeline.py",
        args.query,
        "--top_n", str(args.top_n)
    ]
    if args.tag_type:
        cmd += ["--tag-type", args.tag_type]
    if args.tag_value:
        cmd += ["--tag-value", args.tag_value]
    if args.extract_all:
        cmd += ["--extract-all"]
    if args.assemble:
        cmd += ["--assemble"]
    if args.assembled_out:
        cmd += ["--assembled-out", args.assembled_out]
    run_command(cmd)

def cmd_extract(args):
    """Extract a single clip."""
    run_command([
        sys.executable, "scripts/retrieve_clips.py",
        "--source-uri", args.source_uri,
        "--start-sec", str(args.start_sec),
        "--end-sec", str(args.end_sec),
        "--output-dir", args.output_dir
    ])

def cmd_assemble(args):
    """Concatenate clips into one video."""
    run_command([
        sys.executable, "scripts/concatenate_clips.py",
        "--input-dir", args.input_dir,
        "--output-file", args.output_file
    ])

def cmd_clean(args):
    """Remove outputs/clips and outputs/assembled directories."""
    for d in ("outputs/clips", "outputs/assembled"):
        if os.path.isdir(d):
            print(f"Removing {d} …")
            shutil.rmtree(d)
        else:
            print(f"{d} does not exist, skipping.")

def cmd_help(args):
    """Show help (default)."""
    parser.print_help()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Master pipeline CLI for Content Analysis Pipeline"
    )
    subparsers = parser.add_subparsers(dest="command")

    # ingest
    p_ingest = subparsers.add_parser("ingest", help="Ingest a media file")
    p_ingest.add_argument("--file", "-f", required=True, help="Path to media file")
    p_ingest.set_defaults(func=cmd_ingest)

    # enrich
    p_enrich = subparsers.add_parser("enrich", help="Run all enrichment steps")
    p_enrich.set_defaults(func=cmd_enrich)

    # query
    p_query = subparsers.add_parser("query", help="Semantic search (and optional extract/assemble)")
    p_query.add_argument("query", type=str, help="Text query for semantic search")
    p_query.add_argument("-n", "--top_n", type=int, default=5, help="Number of results")
    p_query.add_argument("--tag-type", type=str, help="Filter by tag type")
    p_query.add_argument("--tag-value", type=str, help="Filter by tag value")
    p_query.add_argument("--extract-all", action="store_true", help="Extract all returned clips")
    p_query.add_argument("--assemble", action="store_true", help="Concatenate extracted clips")
    p_query.add_argument("--assembled-out", type=str, default="outputs/assembled/combined.mp4", help="Path for combined video")
    p_query.set_defaults(func=cmd_query)

    # extract
    p_ext = subparsers.add_parser("extract", help="Extract a single clip")
    p_ext.add_argument("--source-uri", "-i", required=True, help="Media file URI or path")
    p_ext.add_argument("--start-sec", "-s", type=float, required=True, help="Start time in seconds")
    p_ext.add_argument("--end-sec", "-e", type=float, required=True, help="End time in seconds")
    p_ext.add_argument("--output-dir", "-o", type=str, default="outputs/clips", help="Output directory")
    p_ext.set_defaults(func=cmd_extract)

    # assemble
    p_ass = subparsers.add_parser("assemble", help="Concatenate clips into one video")
    p_ass.add_argument("--input-dir", "-i", required=True, help="Directory of clips")
    p_ass.add_argument("--output-file", "-o", type=str, default="outputs/assembled/combined.mp4", help="Output file path")
    p_ass.set_defaults(func=cmd_assemble)

    # clean
    p_clean = subparsers.add_parser("clean", help="Remove all generated clips and assemblies")
    p_clean.set_defaults(func=cmd_clean)

    # default help
    parser.set_defaults(func=cmd_help)

    args = parser.parse_args()
    args.func(args)