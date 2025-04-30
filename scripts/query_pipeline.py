import os
import sys
import logging
import argparse
import psycopg2
from psycopg2 import sql
from psycopg2.extras import DictCursor  # Use DictCursor for easier row access
from pathlib import Path
from sentence_transformers import SentenceTransformer
import torch  # Import torch for device management

# --- Add Project Root to Python Path ---
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from retrieve_clips import extract_clip  # Import the function to extract clips

from config import config
from scripts import db_utils

# --- Logging Setup ---
log_file = config.LOGS_DIR / 'query.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# --- Load Embedding Model ---
try:
    logging.info(f"Loading Sentence Transformer model for querying: {config.EMBEDDING_MODEL}")
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    logging.info(f"Using device: {device}")
    embedding_model = SentenceTransformer(config.EMBEDDING_MODEL, device=device)
    logging.info("Query model loaded successfully.")
except Exception as e:
    logging.error(f"Failed to load Sentence Transformer model: {e}")
    logging.warning("Falling back to CPU if model loading failed.")
    try:
        embedding_model = SentenceTransformer(config.EMBEDDING_MODEL, device='cpu')
        logging.info("Query model loaded successfully on CPU (fallback).")
    except Exception as e2:
        logging.error(f"Failed to load Sentence Transformer model on CPU as fallback: {e2}")
        embedding_model = None

# --- Enhanced Semantic Search Function ---
def semantic_search_with_tags(query_text, top_n=5, filter_tag_type=None, filter_tag_value=None):
    """Performs semantic search, optionally filtering by tags."""
    if not embedding_model:
        logging.error("Embedding model not loaded. Cannot perform search.")
        return []
    if not query_text:
        logging.error("Query text cannot be empty.")
        return []

    conn = db_utils.get_db_connection()
    if not conn:
        return []

    initial_results = []
    final_results = []
    try:
        # 1. Initial Semantic Search
        logging.info(f"Generating embedding for query: '{query_text}'")
        query_embedding = embedding_model.encode(query_text)
        query_embedding_list = query_embedding.tolist()

        logging.info(f"Searching database for top {top_n * 5} potential segments...")
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute(
                sql.SQL("""
                    SELECT
                        e.id AS distance_id,
                        e.transcript_id,
                        t.media_id,
                        t.start_sec,
                        t.end_sec,
                        t.text,
                        m.filename,
                        m.source_uri,
                        e.embedding <=> %s::vector AS distance
                    FROM content_creation.embeddings e
                    JOIN content_creation.transcripts t ON e.transcript_id = t.id
                    JOIN content_creation.media m ON t.media_id = m.id
                    WHERE e.model_name = %s
                    ORDER BY distance ASC
                    LIMIT %s;
                """),
                (
                    query_embedding_list,
                    config.EMBEDDING_MODEL,
                    top_n * 5 if (filter_tag_type and filter_tag_value) else top_n
                )
            )
            initial_results = cur.fetchall()
            logging.info(f"Found {len(initial_results)} initial candidate results.")

            if not initial_results:
                return []

            initial_results = [dict(row) for row in initial_results]

            # 2. Optional Tag Filtering
            if filter_tag_type and filter_tag_value:
                logging.info(f"Filtering results by tag_type='{filter_tag_type}' and tag_value='{filter_tag_value}'...")
                candidate_ids = [r['transcript_id'] for r in initial_results]
                cur.execute(
                    sql.SQL("""
                        SELECT DISTINCT transcript_id
                        FROM content_creation.content_tags
                        WHERE transcript_id = ANY(%s)
                          AND tag_type = %s
                          AND tag_value ILIKE %s;
                    """),
                    (candidate_ids, filter_tag_type, f"%{filter_tag_value}%")
                )
                matching_ids = {row['transcript_id'] for row in cur.fetchall()}
                filtered = [r for r in initial_results if r['transcript_id'] in matching_ids]
                final_results = filtered[:top_n]
                logging.info(f"{len(final_results)} results after tag filtering.")
            else:
                final_results = initial_results[:top_n]
                logging.info(f"No tag filtering—returning top {len(final_results)} results.")

            # 3. Fetch Summaries & Tags for the final subset
            if final_results:
                tids = [r['transcript_id'] for r in final_results]
                cur.execute(
                    sql.SQL("""
                        SELECT transcript_id, summary_text
                        FROM content_creation.summaries
                        WHERE transcript_id = ANY(%s);
                    """), (tids,)
                )
                summaries = {row['transcript_id']: row['summary_text'] for row in cur.fetchall()}

                cur.execute(
                    sql.SQL("""
                        SELECT transcript_id, tag_type, tag_value, score
                        FROM content_creation.content_tags
                        WHERE transcript_id = ANY(%s)
                        ORDER BY transcript_id, score DESC;
                    """), (tids,)
                )
                tags = {}
                for row in cur.fetchall():
                    t_id = row['transcript_id']
                    tags.setdefault(t_id, []).append(
                        f"{row['tag_type']}:{row['tag_value']} ({row['score']:.2f})"
                    )

                for r in final_results:
                    r['summary'] = summaries.get(r['transcript_id'], 'N/A')
                    r['tags'] = tags.get(r['transcript_id'], [])

    except psycopg2.Error as e:
        logging.error(f"Database error during search: {e}")
        if conn: conn.rollback()
    except Exception as e:
        logging.exception(f"Unexpected error during search: {e}")
    finally:
        db_utils.close_db_connection(conn)

    return final_results


# --- Main Execution ---
if __name__ == "__main__":
    logging.info("--- Starting Query Script ---")
    parser = argparse.ArgumentParser(
        description="Query the database via semantic search, optionally filtering by tags."
    )
    parser.add_argument("query", type=str, help="The text query.")
    parser.add_argument("-n", "--top_n", type=int, default=5, help="Number of results.")
    parser.add_argument("--tag-type", type=str, help="Filter by tag type.")
    parser.add_argument("--tag-value", type=str, help="Filter by tag value (case-insensitive).")
    parser.add_argument(
        "--extract-all",
        action="store_true",
        help="Automatically extract all returned clips without prompting"
    )
    args = parser.parse_args()

    extract_all = args.extract_all

    if args.tag_value and not args.tag_type:
        parser.error("--tag-type is required when --tag-value is provided.")
    if args.tag_type and not args.tag_value:
        parser.error("--tag-value is required when --tag-type is provided.")

    if not embedding_model:
        logging.error("No embedding model loaded—aborting.")
        sys.exit(1)

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

            # --- CLIP EXTRACTION ---
            if extract_all:
                do_extract = True
            else:
                choice = input("    Extract this clip? [y/N]: ").strip().lower()
                do_extract = (choice == "y")

            if do_extract:
                try:
                    clip_path = extract_clip(res['source_uri'], res['start_sec'], res['end_sec'])
                    print(f"    [INFO] Clip saved to: {clip_path}")
                except Exception as e:
                    print(f"    [ERROR] Failed to extract clip: {e}")

        print("\n--- End of Results ---")
    else:
        print("No results found matching your criteria or an error occurred.")

    logging.info("--- Query Script Finished ---")