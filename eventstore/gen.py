import json
import random
import uuid
from datetime import datetime, timedelta, timezone

TYPES = ["impression"] * 85 + ["click"] * 12 + ["conversion"] * 3
COUNTRIES = ["DK", "DE", "SE", "NL", "US", "GB"]


def make_events(n, start, days, seed=7, users=50_000, campaigns=200):
    """Deterministic synthetic events spread over `days` days from `start` (a date)."""
    rnd = random.Random(seed)
    t0 = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    span = days * 86400
    rows = []
    for _ in range(n):
        rows.append((
            uuid.UUID(int=rnd.getrandbits(128), version=4),
            rnd.randint(1, users),
            rnd.randint(1, campaigns),
            rnd.choice(TYPES),
            t0 + timedelta(seconds=rnd.randrange(span), microseconds=rnd.randrange(1_000_000)),
            json.dumps({"country": rnd.choice(COUNTRIES)}),
        ))
    return rows
