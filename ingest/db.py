"""Database helpers: connect to Neon and create the chunks table."""
import os

import atexit

from psycopg_pool import ConnectionPool

import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector

load_dotenv()

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunks (
    config    text NOT NULL,
    id        text NOT NULL,
    part      text NOT NULL,
    page      int  NOT NULL,
    kind      text NOT NULL,
    section   text NOT NULL,
    content   text NOT NULL,
    embedding vector(384) NOT NULL,
    tsv       tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
    PRIMARY KEY (config, id)
);

CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw
    ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunks_tsv_gin ON chunks USING gin (tsv);

CREATE TABLE IF NOT EXISTS answer_cache (
    key        text PRIMARY KEY,
    question   text NOT NULL,
    config     text NOT NULL,
    response   jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
"""


_pool = None


def _setup(conn):
    """Runs once for each new connection the pool opens."""
    register_vector(conn)
    conn.execute("SET hnsw.iterative_scan = strict_order")
    conn.commit()


def get_pool():
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            os.environ["DATABASE_URL"],
            min_size=1,
            max_size=4,
            configure=_setup,
            check=ConnectionPool.check_connection,
            open=True,
        )
        atexit.register(_pool.close)
    return _pool


def connect():
    """Borrow a connection. `with connect() as conn:` gives it back at the end."""
    return get_pool().connection()


def create_schema():
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute(SCHEMA)
    print("chunks table and indexes ready")


if __name__ == "__main__":
    create_schema()