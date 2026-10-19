import threading
import uuid
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from eventstore import ingest, queries
from eventstore.db import connect
from eventstore.gen import make_events
from eventstore.health import health
from eventstore.schema import ensure_partitions
from conftest import FIRST_DAY, TEST_SCHEMA


def count(conn, table="events"):
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def one_event(day=3, user=1, kind="click", event_id=None):
    return (event_id or uuid.uuid4(), user, 5, kind,
            datetime(2026, 10, day, 12, 0, tzinfo=timezone.utc), "{}")


def test_one_partition_per_day_plus_default(conn):
    names = [r[0] for r in conn.execute(
        "SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid "
        "WHERE i.inhparent = 'events'::regclass ORDER BY 1")]
    assert names[0] == "events_20261001" and names[-1] == "events_default"
    assert len(names) == 8


def test_event_lands_in_the_partition_of_its_day(conn):
    ingest.copy_upsert(conn, [one_event(day=3)])
    where = conn.execute("SELECT tableoid::regclass::text FROM events").fetchone()[0]
    assert where.endswith("events_20261003")


def test_event_outside_every_partition_goes_to_default_and_health_reports_it(conn):
    ingest.copy_upsert(conn, [one_event(day=3), (uuid.uuid4(), 1, 5, "click", datetime(2026, 9, 1, tzinfo=timezone.utc), "{}")])
    assert count(conn, "events_default") == 1
    assert health(conn)["late_events_in_default"] == 1


def test_copy_upsert_is_idempotent(conn):
    rows = make_events(500, FIRST_DAY, 7, seed=3)
    assert ingest.copy_upsert(conn, rows) == 500
    assert ingest.copy_upsert(conn, rows) == 0
    assert count(conn) == 500


def test_duplicates_inside_one_batch_are_stored_once(conn):
    e = one_event()
    assert ingest.copy_upsert(conn, [e, e, e]) == 1
    assert count(conn) == 1


def test_all_three_write_methods_store_the_same_rows(conn):
    rows = make_events(300, FIRST_DAY, 7, seed=4)
    ingest.insert_many(conn, rows)
    ingest.copy_upsert(conn, rows)
    ingest.insert_rowwise(conn, rows[:50])
    assert count(conn) == 300


def test_bad_event_type_is_rejected_by_the_database(conn):
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("INSERT INTO events VALUES (%s, 1, 1, 'purchase', %s, '{}')",
                     (uuid.uuid4(), datetime(2026, 10, 2, tzinfo=timezone.utc)))
    conn.rollback()


def test_user_query_uses_the_index_and_falls_back_to_scans_without_it(conn):
    ingest.copy_upsert(conn, make_events(20_000, FIRST_DAY, 7, seed=5, users=200))
    conn.execute("ANALYZE events")
    conn.commit()
    _, nodes = queries.explain(conn, queries.RECENT_FOR_USER, (42,))
    assert queries.uses_index_scan(nodes)
    conn.execute("DROP INDEX events_user_time_idx")
    conn.commit()
    _, nodes = queries.explain(conn, queries.RECENT_FOR_USER, (42,))
    assert not queries.uses_index_scan(nodes)


def test_query_for_one_day_scans_only_that_partition(conn):
    ingest.copy_upsert(conn, make_events(5_000, FIRST_DAY, 7, seed=6))
    conn.execute("ANALYZE events")
    conn.commit()
    lo = datetime(2026, 10, 3, tzinfo=timezone.utc)
    _, nodes = queries.explain(conn, queries.DAY_COUNT, (lo, lo + timedelta(days=1)))
    assert queries.scanned_partitions(nodes) == ["events_20261003"]


def test_concurrent_updates_of_one_hot_row_lose_nothing(conn):
    conn.execute("INSERT INTO campaign_counters VALUES (1, 0)")
    conn.commit()

    def worker():
        c = connect(schema=TEST_SCHEMA)
        for _ in range(100):
            c.execute("UPDATE campaign_counters SET clicks = clicks + 1 WHERE campaign_id = 1")
            c.commit()
        c.close()

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert conn.execute("SELECT clicks FROM campaign_counters WHERE campaign_id = 1").fetchone()[0] == 400


def test_health_report_has_what_an_on_call_engineer_needs(conn):
    ingest.copy_upsert(conn, make_events(1_000, FIRST_DAY, 7, seed=8))
    h = health(conn)
    assert h["partitions"] == 7
    assert set(h) >= {"partition_bytes", "late_events_in_default", "index_scans", "dead_tuples"}
    assert "user_id_occurred_at_idx" in h["index_scans"]


def test_creating_partitions_twice_is_harmless(conn):
    ensure_partitions(conn, FIRST_DAY, 7)
    assert health(conn)["partitions"] == 7
