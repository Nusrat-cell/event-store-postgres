import os
import time

import psycopg

DEFAULT_URL = "postgresql://postgres:postgres@localhost:5432/postgres"


def connect(schema=None, autocommit=False, wait_seconds=30):
    """Connect, retrying while the database is still starting. Optionally pin a schema."""
    url = os.environ.get("DATABASE_URL", DEFAULT_URL)
    deadline = time.time() + wait_seconds
    while True:
        try:
            conn = psycopg.connect(url, autocommit=True)
            break
        except psycopg.OperationalError:
            if time.time() > deadline:
                raise
            time.sleep(1)
    if schema:
        conn.execute(f'SET search_path TO "{schema}"')
    conn.autocommit = autocommit
    return conn
