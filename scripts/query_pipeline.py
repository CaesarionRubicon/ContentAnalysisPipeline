import os
import sys
import logging
import argparse # Keep argparse for command-line querying
import psycopg2
from psycopg2 import sql
from pathlib import Path
from sentence_transformers import SentenceTransformer

# --- Add Project Root to Python Path ---
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from config import config # Import settings from config/config.py
from scripts import db_utils # Import database utilities

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

# --- REMOVED local get_db_connection function ---

# --- Load Embedding Model ---
# Load the *same* model used for generating embeddings
try:
    logging.info(f"Loading Sentence Transformer model for querying: {config.EMBEDDING_MODEL}")
    embedding_model = SentenceTransformer(config.EMBEDDING_MODEL, device='cuda')
    logging.info("Query model loaded successfully.")
except Exception as e:
    logging.error(f"Failed to load Sentence Transformer model: {e}")
    embedding_model = None

# --- Semantic Search Function ---
def semantic_search(query_text, top_n=5):
    """Performs semantic search for the query text."""
    if not embedding_model:
        logging.error("Embedding model not loaded. Cannot perform search.")
        return []
    if not query_text:
        logging.error("Query text cannot be empty.")
        return []

    conn = db_utils.get_db_connection() # <<< USE DB UTILS
    if not conn:
        return []

    results = []
    try:
        logging.info(f"Generating embedding for query: '{query_text}'")
        query_embedding = embedding_model.encode(query_text)
        query_embedding_list = query_embedding.tolist()

        logging.info(f"Searching database for top {top_n} similar segments...")
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("""
                    SELECT
                        e.id AS embedding_id,
                        e.transcript_id,
                        t.media_id,
                        t.start_sec,
                        t.end_sec,
                        t.text,
                        m.filename,
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
                    top_n
                )
            )
            search_results = cur.fetchall()

            columns = [desc[0] for desc in cur.description]
            for row in search_results:
                results.append(dict(zip(columns, row)))

            logging.info(f"Found {len(results)} results.")

    except psycopg2.Error as e:
        logging.error(f"Database error during search: {e}")
        if conn: conn.rollback()
    except Exception as e:
        logging.error(f"An unexpected error occurred during search: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Use db_utils to close the connection
        db_utils.close_db_connection(conn, "semantic_search") # <<< USE DB UTILS

    return results


# --- Main Execution ---
if __name__ == "__main__":
    logging.info("--- Starting Query Script ---")
    parser = argparse.ArgumentParser(description="Query the database using semantic search.")
    parser.add_argument("query", type=str, help="The text query for semantic search.")
    parser.add_argument("-n", "--top_n", type=int, default=5, help="Number of top results to retrieve.")

    args = parser.parse_args()

    if embedding_model:
        search_results = semantic_search(args.query, args.top_n)

        if search_results:
            print("\n--- Search Results ---")
            for i, res in enumerate(search_results):
                print(f"\nResult {i+1}: Distance={res['distance']:.4f}")
                print(f"  Media: {res['filename']} (ID: {res['media_id']})")
                print(f"  Time: {res['start_sec']:.2f}s - {res['end_sec']:.2f}s")
                print(f"  Transcript (ID: {res['transcript_id']}): {res['text']}")
            print("--- End of Results ---")
        else:
            print("No results found or an error occurred.")

    logging.info("--- Query Script Finished ---")