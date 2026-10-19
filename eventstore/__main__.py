"""python -m eventstore bench | health | init"""
import os
import sys

from . import bench
from .db import connect
from .health import health
from .schema import apply_schema, ensure_partitions


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "bench"
    if cmd == "bench":
        n = int(os.environ.get("BENCH_ROWS", "1000000"))
        result = bench.run(n)
        out = os.path.join(os.path.dirname(__file__), "..", "docs", "RESULTS.md")
        bench.write_report(result, out)
        print(open(out, encoding="utf-8").read())
    elif cmd == "init":
        conn = connect()
        apply_schema(conn)
        ensure_partitions(conn, bench.START, bench.DAYS)
        print("schema and partitions ready")
    elif cmd == "health":
        conn = connect(schema=os.environ.get("EVENTSTORE_SCHEMA"))
        for k, v in health(conn).items():
            print(k, v)
    else:
        sys.exit("usage: python -m eventstore bench | init | health")


if __name__ == "__main__":
    main()
