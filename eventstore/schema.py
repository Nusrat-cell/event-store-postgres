import os
from datetime import date, datetime, timedelta, timezone

SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "..", "schema")


def reset_schema(conn, schema):
    conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    conn.execute(f'CREATE SCHEMA "{schema}"')
    conn.execute(f'SET search_path TO "{schema}"')
    conn.commit()


def apply_schema(conn):
    for name in sorted(os.listdir(SCHEMA_DIR)):
        if name.endswith(".sql"):
            with open(os.path.join(SCHEMA_DIR, name), encoding="utf-8") as f:
                conn.execute(f.read())
    conn.commit()


def partition_name(day: date) -> str:
    return "events_" + day.strftime("%Y%m%d")


def ensure_partitions(conn, first_day: date, days: int):
    """Create one partition per day. Must run before rows for those days are loaded."""
    for i in range(days):
        day = first_day + timedelta(days=i)
        lo = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        hi = lo + timedelta(days=1)
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {partition_name(day)} PARTITION OF events "
            f"FOR VALUES FROM ('{lo.isoformat()}') TO ('{hi.isoformat()}')"
        )
    conn.commit()
