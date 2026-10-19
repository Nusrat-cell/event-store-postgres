"""Measure what the design choices cost. Every number in docs/RESULTS.md comes from this file."""
import os
import platform
import statistics
import threading
import time
from datetime import date, datetime, timedelta, timezone

from . import ingest, queries
from .db import connect
from .gen import make_events
from .schema import apply_schema, ensure_partitions, reset_schema

START = date(2026, 10, 1)
DAYS = 7
BENCH_SCHEMA = "bench"


def _timed(fn):
    t = time.perf_counter()
    result = fn()
    return time.perf_counter() - t, result


def load_methods(n_small):
    """Same rows, three ways to write them."""
    out = {}
    for name, fn in (("one commit per row", ingest.insert_rowwise),
                     ("executemany, one transaction", ingest.insert_many),
                     ("COPY into staging, then upsert", ingest.copy_upsert)):
        conn = connect()
        reset_schema(conn, BENCH_SCHEMA)
        apply_schema(conn)
        ensure_partitions(conn, START, DAYS)
        rows = make_events(n_small, START, DAYS, seed=1)
        seconds, _ = _timed(lambda: fn(conn, rows))
        out[name] = (n_small, seconds, n_small / seconds)
        conn.close()
    return out


def load_big(conn, n):
    rows = make_events(n, START, DAYS, seed=2)
    seconds = 0.0
    for i in range(0, n, 100_000):
        chunk = rows[i:i + 100_000]
        s, _ = _timed(lambda: ingest.copy_upsert(conn, chunk))
        seconds += s
    conn.execute("ANALYZE events")
    conn.commit()
    return n, seconds, n / seconds


def median_ms(conn, sql, params_list):
    times = []
    nodes = None
    for p in params_list:
        ms, nodes = queries.explain(conn, sql, p)
        times.append(ms)
    return statistics.median(times), nodes


def index_effect(conn):
    users = [(u,) for u in (4242, 17, 31337, 25000, 49999, 1234, 777, 9001, 40404, 12345)]
    with_idx, nodes_with = median_ms(conn, queries.RECENT_FOR_USER, users)
    conn.execute("DROP INDEX events_user_time_idx")
    conn.commit()
    without, nodes_without = median_ms(conn, queries.RECENT_FOR_USER, users)
    conn.execute("CREATE INDEX events_user_time_idx ON events (user_id, occurred_at DESC)")
    conn.execute("ANALYZE events")
    conn.commit()
    return with_idx, without, queries.uses_index_scan(nodes_with), queries.uses_index_scan(nodes_without)


def pruning(conn):
    lo = datetime(2026, 10, 3, tzinfo=timezone.utc)
    ms, nodes = queries.explain(conn, queries.DAY_COUNT, (lo, lo + timedelta(days=1)))
    return ms, queries.scanned_partitions(nodes)


def index_sizes(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT pg_size_pretty(sum(pg_relation_size(c.oid))) FROM pg_class c "
                    "WHERE c.relkind = 'i' AND c.relname LIKE 'events_%%_user_id_occurred_at_idx'")
        btree = cur.fetchone()[0]
        cur.execute("SELECT pg_size_pretty(sum(pg_relation_size(c.oid))) FROM pg_class c "
                    "WHERE c.relkind = 'i' AND c.relname LIKE 'events_%%_occurred_at_idx'")
        other = cur.fetchone()[0]
        cur.execute("SELECT pg_size_pretty(sum(pg_total_relation_size(c.oid))) FROM pg_inherits i "
                    "JOIN pg_class c ON c.oid = i.inhrelid WHERE i.inhparent = 'events'::regclass")
        total = cur.fetchone()[0]
    return btree, other, total


def hot_row(threads, per_thread, spread, work_ms=1):
    """Concurrent counter updates. Each transaction holds its row lock for work_ms."""
    setup = connect(schema=BENCH_SCHEMA)
    setup.execute("TRUNCATE campaign_counters")
    setup.execute("INSERT INTO campaign_counters SELECT g, 0 FROM generate_series(1, 200) g")
    setup.commit()
    setup.close()

    def worker(idx):
        conn = connect(schema=BENCH_SCHEMA)
        for i in range(per_thread):
            cid = 1 if not spread else 1 + (idx * per_thread + i) % 200
            conn.execute("UPDATE campaign_counters SET clicks = clicks + 1 WHERE campaign_id = %s", (cid,))
            conn.execute("SELECT pg_sleep(%s)", (work_ms / 1000.0,))
            conn.commit()
        conn.close()

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(threads)]
    t = time.perf_counter()
    for x in ts:
        x.start()
    for x in ts:
        x.join()
    seconds = time.perf_counter() - t
    check = connect(schema=BENCH_SCHEMA)
    total = check.execute("SELECT sum(clicks) FROM campaign_counters").fetchone()[0]
    check.close()
    return threads * per_thread, seconds, total


def run(n_big):
    n_small = int(os.environ.get("BENCH_SMALL", "5000"))
    loads = load_methods(n_small)
    conn = connect()
    reset_schema(conn, BENCH_SCHEMA)
    apply_schema(conn)
    ensure_partitions(conn, START, DAYS)
    big = load_big(conn, n_big)
    idx_with, idx_without, used_with, used_without = index_effect(conn)
    prune_ms, parts = pruning(conn)
    btree, other, total = index_sizes(conn)
    version = conn.execute("SHOW server_version").fetchone()[0]
    conn.close()
    hot = hot_row(8, 150, spread=False)
    spread = hot_row(8, 150, spread=True)
    return dict(loads=loads, big=big, idx_with=idx_with, idx_without=idx_without, used_with=used_with,
                used_without=used_without, prune_ms=prune_ms, parts=parts, btree=btree, other=other,
                total=total, hot=hot, spread=spread, version=version, n_big=n_big)


def write_report(r, path):
    L = []
    L.append("# Measured results")
    L.append("")
    L.append(f"PostgreSQL {r['version']} on {platform.processor() or platform.machine()}, "
             f"{os.cpu_count()} CPU cores, Python {platform.python_version()}. Synthetic data, one machine, "
             "numbers are for comparing the designs with each other, not for capacity planning.")
    L.append("")
    L.append("## 1. Three ways to write the same rows")
    L.append("")
    L.append("| Method | Rows | Seconds | Rows per second |")
    L.append("|-|-|-|-|")
    for name, (n, s, rate) in r["loads"].items():
        L.append(f"| {name} | {n:,} | {s:.2f} | {rate:,.0f} |")
    n, s, rate = r["big"]
    L.append(f"| COPY into staging, then upsert (full load) | {n:,} | {s:.1f} | {rate:,.0f} |")
    L.append("")
    L.append("## 2. What the index on user and time buys")
    L.append("")
    L.append(f"Query: last 50 events of one user, median of 10 users, over {r['n_big']:,} rows in 8 partitions.")
    L.append("")
    L.append("| Setup | Median execution time | Plan uses an index |")
    L.append("|-|-|-|")
    L.append(f"| With the index | {r['idx_with']:.2f} ms | {r['used_with']} |")
    L.append(f"| Without the index | {r['idx_without']:.2f} ms | {r['used_without']} |")
    L.append(f"| Speed up | {r['idx_without'] / max(r['idx_with'], 0.001):,.0f} times | |")
    L.append("")
    L.append(f"Index cost: user and time B-tree indexes take {r['btree']} in total, the whole table with all "
             f"indexes is {r['total']}. Every index slows writes down a little, so each one has to earn its place.")
    L.append("")
    L.append("## 3. Partition pruning")
    L.append("")
    L.append(f"A count for one day ran in {r['prune_ms']:.1f} ms and scanned {len(r['parts'])} of 8 daily "
             f"partitions: {', '.join(r['parts'])}.")
    L.append("")
    L.append("## 4. What breaks under concurrent writes")
    L.append("")
    L.append("8 threads, 150 counter updates each, every transaction holds its row lock for 1 ms to stand in "
             "for real work.")
    L.append("")
    L.append("| Pattern | Updates | Seconds | Updates per second | Final count correct |")
    L.append("|-|-|-|-|-|")
    for name, (n, s, total) in (("All threads update one hot row", r["hot"]), ("Updates spread over 200 rows", r["spread"])):
        L.append(f"| {name} | {n:,} | {s:.2f} | {n / s:,.0f} | {total == n} |")
    L.append("")
    L.append("The hot row serialises the writers: each transaction waits for the one before it. Spreading the "
             "load, or inserting one row per click and summing later, removes the queue.")
    L.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
