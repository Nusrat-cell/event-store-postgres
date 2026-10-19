import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from eventstore.db import connect  # noqa: E402
from eventstore.schema import apply_schema, ensure_partitions, reset_schema  # noqa: E402
from datetime import date  # noqa: E402

TEST_SCHEMA = "evtest"
FIRST_DAY = date(2026, 10, 1)


@pytest.fixture()
def conn():
    c = connect()
    reset_schema(c, TEST_SCHEMA)
    apply_schema(c)
    ensure_partitions(c, FIRST_DAY, 7)
    yield c
    c.close()


@pytest.fixture(scope="session", autouse=True)
def cleanup_schema():
    yield
    c = connect(autocommit=True)
    c.execute(f'DROP SCHEMA IF EXISTS "{TEST_SCHEMA}" CASCADE')
    c.close()
