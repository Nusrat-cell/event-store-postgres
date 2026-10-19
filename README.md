# Event store on PostgreSQL

A small event store for advertising style events (impressions, clicks, conversions), built to
learn what a database does under load instead of reading about it. Daily partitions, three kinds
of index, idempotent bulk loading, a health report, and a benchmark that writes down what each
design choice costs. All data is synthetic.

I built it because I could write SQL but could not yet say what an index costs, what breaks when
many writers hit one row, or why people say "use COPY". The numbers below came from running it.

## What I measured

PostgreSQL 16 on a 2 core machine, 1,000,000 events over 7 days (full tables in `docs/RESULTS.md`).

| Question | Result |
|-|-|
| One commit per row against COPY into staging, 5,000 rows | 1,769 rows per second against 51,366 |
| Full load of 1,000,000 rows with COPY and upsert | 13.7 seconds, 73,025 rows per second |
| Last 50 events of one user, with and without the index on (user, time) | 0.24 ms against 43.31 ms, about 180 times |
| Cost of that index | 30 MB of a 181 MB table |
| Count for one day | scans 1 of 8 partitions (partition pruning) |
| 8 writers updating one counter row against 200 rows | 337 against 2,028 updates per second |

The last row used a 1 ms sleep inside each transaction to stand in for real work. The point is the
shape of the result: a hot row turns parallel writers into a queue. Final counts were correct in
both runs, so nothing was lost, it was only slow.

## Design

* `events` is partitioned by day on `occurred_at`. The primary key is `(event_id, occurred_at)`
  because a primary key on a partitioned table has to include the partition key.
* A default partition catches events outside every daily partition, so one late event does not fail
  a whole batch. `health` reports how many are waiting there.
* Indexes: a B-tree on `(user_id, occurred_at DESC)` for the main read, a partial index on
  conversions only (about 3 percent of rows), and a BRIN index on time, which is tiny because rows
  arrive in time order.
* `copy_upsert` copies into a temporary staging table and then runs one `INSERT ... ON CONFLICT DO
  NOTHING`. Sending the same file twice, or the same event twice inside one file, stores it once.
* `health` reports partition sizes, late events, index scan counts per index (an index with no
  scans is a candidate for removal) and dead tuples.

## Tests

12 pytest tests against a real PostgreSQL: one partition per day, an event lands in the partition of
its day, a late event goes to the default partition, idempotent loading, duplicates inside a batch,
the check constraint rejects a bad event type, the plan uses the index and stops using it when the
index is dropped, a one day query scans one partition, 4 threads times 100 updates of one row end at
exactly 400, and the health report. GitHub Actions runs them against a `postgres:16` service
container on every push, and then runs a smaller benchmark.

```bash
pip install -r requirements.txt
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres
python -m pytest -q
python -m eventstore bench       # BENCH_ROWS=100000 for a quicker run
python -m eventstore health
```

`docker-compose.yml` starts a local PostgreSQL 16 for this.

## What I ran and did not run

* Run: all tests and the full benchmark on PostgreSQL 16.15, and the tests in GitHub Actions.
* Not run: the Docker Compose file (the machine I built this on had no Docker daemon), anything on
  more than one node, connection pooling, replication, and a streaming source such as Kafka or
  Pub/Sub. Events arrive as batches here.
* Not done: dbt models on top, Terraform, and a test with MongoDB.

## Next steps

* Put a stream consumer in front of `copy_upsert` and measure batch size against latency.
* Drop old partitions on a schedule and measure that against `DELETE`.
* Add `pg_stat_statements` to `health` to list the slowest queries.
