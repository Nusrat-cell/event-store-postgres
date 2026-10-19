RECENT_FOR_USER = (
    "SELECT event_id, event_type, occurred_at FROM events "
    "WHERE user_id = %s ORDER BY occurred_at DESC LIMIT 50"
)
DAY_COUNT = (
    "SELECT event_type, count(*) FROM events "
    "WHERE occurred_at >= %s AND occurred_at < %s GROUP BY event_type"
)


def explain(conn, sql, params):
    """Run EXPLAIN ANALYZE and return (execution_ms, plan_nodes)."""
    with conn.cursor() as cur:
        cur.execute("EXPLAIN (ANALYZE, FORMAT JSON) " + sql, params)
        doc = cur.fetchone()[0][0]
    nodes = []

    def walk(node):
        nodes.append(node)
        for child in node.get("Plans", []):
            walk(child)

    walk(doc["Plan"])
    return doc["Execution Time"], nodes


def scanned_partitions(nodes):
    return sorted({n["Relation Name"] for n in nodes
                   if "Scan" in n["Node Type"] and n.get("Relation Name", "").startswith("events_")})


def uses_index_scan(nodes):
    return any("Index" in n["Node Type"] for n in nodes)
