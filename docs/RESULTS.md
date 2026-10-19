# Measured results

PostgreSQL 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1) on x86_64, 2 CPU cores, Python 3.13.16. Synthetic data, one machine, numbers are for comparing the designs with each other, not for capacity planning.

## 1. Three ways to write the same rows

| Method | Rows | Seconds | Rows per second |
|-|-|-|-|
| one commit per row | 5,000 | 2.83 | 1,769 |
| executemany, one transaction | 5,000 | 0.18 | 28,548 |
| COPY into staging, then upsert | 5,000 | 0.10 | 51,366 |
| COPY into staging, then upsert (full load) | 1,000,000 | 13.7 | 73,025 |

## 2. What the index on user and time buys

Query: last 50 events of one user, median of 10 users, over 1,000,000 rows in 8 partitions.

| Setup | Median execution time | Plan uses an index |
|-|-|-|
| With the index | 0.24 ms | True |
| Without the index | 43.31 ms | False |
| Speed up | 182 times | |

Index cost: user and time B-tree indexes take 30 MB in total, the whole table with all indexes is 181 MB. Every index slows writes down a little, so each one has to earn its place.

## 3. Partition pruning

A count for one day ran in 22.1 ms and scanned 1 of 8 daily partitions: events_20261003.

## 4. What breaks under concurrent writes

8 threads, 150 counter updates each, every transaction holds its row lock for 1 ms to stand in for real work.

| Pattern | Updates | Seconds | Updates per second | Final count correct |
|-|-|-|-|-|
| All threads update one hot row | 1,200 | 3.56 | 337 | True |
| Updates spread over 200 rows | 1,200 | 0.59 | 2,028 | True |

The hot row serialises the writers: each transaction waits for the one before it. Spreading the load, or inserting one row per click and summing later, removes the queue.
