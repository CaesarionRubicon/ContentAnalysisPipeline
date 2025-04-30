import os
import sys
import logging
import argparse
import psycopg2
from psycopg2 import sql
from psycopg2.extras import DictCursor
from pathlib import Path
from sentence_transformers import SentenceTransformer
import torch

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from retrieve_clips import extract_clip
from concatenate_clips import concatenate_clips
import datetime

from config import config
from scripts import db_utils

# Logging
log_file = config.LOGS_DIR / 'query.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(log_file, encoding='utf-8'), logging.StreamHandler()]
)

# Load model
try:
    logging.info(f"Loading Sentence Transformer model: {config.EMBEDDING_MODEL}")
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    logging.info(f"Using device: {device}")
    embedding_model = SentenceTransformer(config.EMBEDDING_MODEL, device=device)
    logging.info("Model loaded.")
except Exception as e:
    logging.error(f"Failed to load model: {e}")
    logging.warning("Falling back to CPU.")
    try:
        embedding_model = SentenceTransformer(config.EMBEDDING_MODEL, device='cpu')
        logging.info("Fallback model loaded on CPU.")
    except Exception as e2:
        logging.error(f"CPU fallback failed: {e2}")
        embedding_model = None

def semantic_search_with_tags(query_text, top_n=5, filter_tag_type=None, filter_tag_value=None):
    if not embedding_model or not query_text:
        return []

    conn = db_utils.get_db_connection()
    if not conn:
        return []

    initial_results, final_results = [], []
    try:
        logging.info(f"Encoding query: '{query_text}'")
        qe = embedding_model.encode(query_text).tolist()

        # Fetch candidates
        limit = top_n * 5 if (filter_tag_type and filter_tag_value) else top_n
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute(
                sql.SQL("""
                    SELECT e.transcript_id, t.media_id, t.start_sec, t.end_sec,
                           t.text, m.filename, m.source_uri,
                           e.embedding <=> %s::vector AS distance
                    FROM content_creation.embeddings e
                    JOIN content_creation.transcripts t ON e.transcript_id = t.id
                    JOIN content_creation.media m ON t.media_id = m.id
                    WHERE e.model_name = %s
                    ORDER BY distance ASC
                    LIMIT %s;
                """),
                (qe, config.EMBEDDING_MODEL, limit)
            )
            initial_results = [dict(r) for r in cur.fetchall()]
            logging.info(f"{len(initial_results)} candidates found.")

            if filter_tag_type and filter_tag_value:
                ids = [r['transcript_id'] for r in initial_results]
                cur.execute(
                    sql.SQL("""
                        SELECT DISTINCT transcript_id
                        FROM content_creation.content_tags
                        WHERE transcript_id = ANY(%s)
                          AND tag_type = %s
                          AND tag_value ILIKE %s;
                    """),
                    (ids, filter_tag_type, f"%{filter_tag_value}%")
                )
                matches = {r['transcript_id'] for r in cur.fetchall()}
                filtered = [r for r in initial_results if r['transcript_id'] in matches]
                final_results = filtered[:top_n]
                logging.info(f"{len(final_results)} after tag filter.")
            else:
                final_results = initial_results[:top_n]
                logging.info(f"No tag filter applied; returning top {len(final_results)}.")

            # Fetch summaries and tags
            if final_results:
                tids = [r['transcript_id'] for r in final_results]
                cur.execute(
                    sql.SQL("""
                        SELECT transcript_id, summary_text
                        FROM content_creation.summaries
                        WHERE transcript_id = ANY(%s);
                    """), (tids,)
                )
                sums = {r['transcript_id']: r['summary_text'] for r in cur.fetchall()}

                cur.execute(
                    sql.SQL("""
                        SELECT transcript_id, tag_type, tag_value, score
                        FROM content_creation.content_tags
                        WHERE transcript_id = ANY(%s)
                        ORDER BY transcript_id, score DESC;
                    """), (tids,)
                )
                tags = {}
                for r in cur.fetchall():
                    tid0 = r['transcript_id']
                    tags.setdefault(tid0, []).append(f"{r['tag_type']}:{r['tag_value']} ({r['score']:.2f})")

                for r in final_results:
                    r['summary'] = sums.get(r['transcript_id'], 'N/A')
                    r['tags'] = tags.get(r['transcript_id'], [])
    except Exception as e:
        logging.exception(f"Search error: {e}")
    finally:
        db_utils.close_db_connection(conn)

    return final_results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="CLI for semantic search + clip extraction/assembly"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    p_query = subparsers.add_parser(
        "query",
        help="Semantic search (and optional extract/assemble)",
        description="semantic search (and optional extract/assemble)"
    )
    p_query.add_argument("query", type=str, help="Search text")
    p_query.add_argument("-n", "--top_n", type=int, default=5, help="Number of results")
    p_query.add_argument("--tag-type", type=str, help="Filter by tag type")
    p_query.add_argument("--tag-value", type=str, help="Filter by tag value")
    p_query.add_argument("--extract-all", action="store_true", help="Extract all returned clips")
    p_query.add_argument("--assemble", action="store_true", help="Concatenate extracted clips")
    p_query.add_argument("--assembled-out", type=str, default="outputs/assembled/combined.mp4", help="Path for combined video")
    p_query.add_argument("-d", "--duration", type=float, help="Override clip length in seconds")

    args = parser.parse_args()
    if not embedding_model:
        logging.error("Embedding model not loaded, aborting.")
        sys.exit(1)
    if args.command == "query":
        if args.tag_value and not args.tag_type:
            parser.error("--tag-type is required with --tag-value")
        if args.tag_type and not args.tag_value:
            parser.error("--tag-value is required with --tag-type")

        results = semantic_search_with_tags(
            args.query, args.top_n, args.tag_type, args.tag_value
        )

        if results:
            print("\n--- Search Results ---")
            for i, res in enumerate(results):
                print(f"\nResult {i+1}: Distance={res['distance']:.4f}")
                print(f"  Media:    {res['filename']} (ID: {res['media_id']})")
                print(f"  Source:   {res['source_uri']}")
                print(f"  Time:     {res['start_sec']:.2f}s - {res['end_sec']:.2f}s")
                print(f"  Transcript: {res['text']}")
                print(f"  Summary:  {res.get('summary', 'N/A')}")
                print(f"  Tags:     {', '.join(res.get('tags', ['N/A']))}")

                do_extract = args.extract_all
                if not args.extract_all:
                    choice = input("    Extract this clip? [y/N]: ").strip().lower()
                    do_extract = (choice == "y")

                if do_extract:
                    end_time = args.duration + res['start_sec'] if args.duration else res['end_sec']
                    clip_path = extract_clip(res['source_uri'], res['start_sec'], end_time)
                    print(f"    [INFO] Clip saved to: {clip_path}")

            print("\n--- End of Results ---")

            if args.assemble:
                try:
                    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    base = args.assembled_out.rstrip(".mp4")
                    out_path = f"{base}_{ts}.mp4"
                    concatenate_clips("outputs/clips", out_path)
                    print(f"\n[INFO] Combined video saved to: {out_path}")
                except Exception as e:
                    print(f"\n[ERROR] Failed to assemble clips: {e}")
        else:
            print("No results found matching your criteria or an error occurred.")

    logging.info("--- Query Script Finished ---")