INSERT_SQL = (
    "INSERT INTO events (event_id, user_id, campaign_id, event_type, occurred_at, payload) "
    "VALUES (%s, %s, %s, %s, %s, %s::jsonb) ON CONFLICT (event_id, occurred_at) DO NOTHING"
)


def insert_rowwise(conn, rows):
    """Worst case: one statement and one commit per row."""
    for r in rows:
        conn.execute(INSERT_SQL, r)
        conn.commit()


def insert_many(conn, rows):
    """One transaction, statements sent in a pipeline."""
    with conn.cursor() as cur:
        cur.executemany(INSERT_SQL, rows)
    conn.commit()


def copy_upsert(conn, rows):
    """COPY into a temporary table, then one INSERT that skips rows already stored.

    Safe to run twice with the same rows, and safe with duplicates inside the batch.
    Returns how many rows were new.
    """
    with conn.cursor() as cur:
        cur.execute("CREATE TEMP TABLE staging (LIKE events INCLUDING DEFAULTS) ON COMMIT DROP")
        with cur.copy(
            "COPY staging (event_id, user_id, campaign_id, event_type, occurred_at, payload) FROM STDIN"
        ) as cp:
            for r in rows:
                cp.write_row(r)
        cur.execute(
            "INSERT INTO events SELECT * FROM staging ON CONFLICT (event_id, occurred_at) DO NOTHING"
        )
        new_rows = cur.rowcount
    conn.commit()
    return new_rows
