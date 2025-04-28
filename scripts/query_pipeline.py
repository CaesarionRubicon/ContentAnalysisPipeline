import os
import sys
import logging
import argparse
import psycopg2
from psycopg2 import sql
from pathlib import Path
from sentence_transformers import SentenceTransformer

# --- Add Project Root to Python Path ---
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from config import config # Import settings from config/config.py

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

# --- Database Connection Function ---
def get_db_connection():
    """Establishes and returns a database connection using config."""
    # (Identical to the one in other scripts - consider refactoring later)
    try:
        conn = psycopg2.connect(
            dbname=config.DB_NAME,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            host=config.DB_HOST,
            port=config.DB_PORT
        )
        logging.debug(f"DB connection established to {config.DB_NAME}@{config.DB_HOST}")
        return conn
    except psycopg2.Error as e:
        logging.error(f"Database connection error: {e}")
        return None

# --- Load Embedding Model ---
# Load the *same* model used for generating embeddings
try:
    logging.info(f"Loading Sentence Transformer model for querying: {config.EMBEDDING_MODEL}")
    # Add device='cuda' if using GPU for querying too (can speed up encoding the query)
    embedding_model = SentenceTransformer(config.EMBEDDING_MODEL, device='cuda')
    logging.info("Query model loaded successfully.")
except Exception as e:
    logging.error(f"Failed to load Sentence Transformer model: {e}")
    embedding_model = None # Set to None so script can exit gracefully if model fails

# --- Semantic Search Function ---
def semantic_search(query_text, top_n=5):
    """Performs semantic search for the query text."""
    if not embedding_model:
        logging.error("Embedding model not loaded. Cannot perform search.")
        return []
    if not query_text:
        logging.error("Query text cannot be empty.")
        return []

    conn = get_db_connection()
    if not conn:
        return []

    results = []
    try:
        logging.info(f"Generating embedding for query: '{query_text}'")
        # Generate embedding for the user's query
        query_embedding = embedding_model.encode(query_text)
        query_embedding_list = query_embedding.tolist() # Convert to list for psycopg2

        logging.info(f"Searching database for top {top_n} similar segments...")
        with conn.cursor() as cur:
            # Use the <=> operator (cosine distance) for similarity search with pgvector
            # Smaller distance means more similar
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
                        e.embedding <=> %s::vector AS distance -- Calculate distance
                    FROM content_creation.embeddings e
                    JOIN content_creation.transcripts t ON e.transcript_id = t.id
                    JOIN content_creation.media m ON t.media_id = m.id
                    WHERE e.model_name = %s -- Match the model used for indexing
                    ORDER BY distance ASC -- Order by distance (most similar first)
                    LIMIT %s;
                """),
                (
                    query_embedding_list, # Pass query vector as parameter
                    config.EMBEDDING_MODEL, # Filter by model name
                    top_n # Limit results
                )
            )
            search_results = cur.fetchall()

            # Format results
            columns = [desc[0] for desc in cur.description]
            for row in search_results:
                results.append(dict(zip(columns, row)))

            logging.info(f"Found {len(results)} results.")

    except psycopg2.Error as e:
        logging.error(f"Database error during search: {e}")
        if conn: conn.rollback() # Good practice, though SELECTs don't usually need it
    except Exception as e:
        logging.error(f"An unexpected error occurred during search: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn and not conn.closed:
            conn.close()
            logging.debug("Database connection closed for semantic_search.")

    return results


# --- Main Execution ---
if __name__ == "__main__":
    logging.info("--- Starting Query Script ---")
    parser = argparse.ArgumentParser(description="Query the database using semantic search.")
    parser.add_argument("query", type=str, help="The text query for semantic search.")
    parser.add_argument("-n", "--top_n", type=int, default=5, help="Number of top results to retrieve.")

    args = parser.parse_args()

    if embedding_model: # Check if model loaded successfully
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