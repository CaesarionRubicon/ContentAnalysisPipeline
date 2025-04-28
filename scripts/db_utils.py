import psycopg2
import logging
import sys
from pathlib import Path

# --- Add Project Root to Python Path ---
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))
from config import config  # Import settings

def get_db_connection():
    """Establishes and returns a database connection using config."""
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

def close_db_connection(conn, context=""):
    """Closes the database connection if it's open."""
    if conn and not conn.closed:
        try:
            conn.close()
            logging.debug(f"Database connection closed for {context if context else 'operation'}.")
        except psycopg2.Error as e:
            logging.error(f"Error closing database connection for {context if context else 'operation'}: {e}")
    elif conn and conn.closed:
        logging.debug(f"Database connection already closed for {context if context else 'operation'}.")