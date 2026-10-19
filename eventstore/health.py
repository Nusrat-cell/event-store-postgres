def health(conn):
    """Numbers an on-call engineer wants: partition sizes, late events, index use, dead rows."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT c.relname, pg_total_relation_size(c.oid) FROM pg_inherits i "
            "JOIN pg_class c ON c.oid = i.inhrelid WHERE i.inhparent = 'events'::regclass ORDER BY 1"
        )
        sizes = {name: size for name, size in cur.fetchall()}
        cur.execute("SELECT count(*) FROM events_default")
        late = cur.fetchone()[0]
        cur.execute(
            "SELECT regexp_replace(indexrelname, '^events_(default|[0-9]+)_', ''), sum(idx_scan)::bigint "
            "FROM pg_stat_user_indexes WHERE relname LIKE 'events%%' GROUP BY 1 ORDER BY 1"
        )
        index_scans = {name: scans for name, scans in cur.fetchall()}
        cur.execute("SELECT coalesce(sum(n_dead_tup), 0)::bigint FROM pg_stat_user_tables WHERE relname LIKE 'events%%'")
        dead = cur.fetchone()[0]
    return {
        "partitions": len(sizes) - 1 if "events_default" in sizes else len(sizes),
        "partition_bytes": sizes,
        "late_events_in_default": late,
        "index_scans": index_scans,
        "dead_tuples": dead,
    }
