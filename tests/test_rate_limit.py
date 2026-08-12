import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select

from app.db.models.rate_limit_bucket import RateLimitBucket
from app.services.rate_limit import check_rate_limit


def test_rate_limit_counts_in_database(db):
    assert check_rate_limit(db, scope="form:1", identity="192.0.2.1", limit=2, window_seconds=60).allowed
    assert check_rate_limit(db, scope="form:1", identity="192.0.2.1", limit=2, window_seconds=60).allowed
    result = check_rate_limit(db, scope="form:1", identity="192.0.2.1", limit=2, window_seconds=60)
    assert not result.allowed and result.retry_after > 0
    assert db.query(RateLimitBucket).one().request_count == 3


@pytest.mark.postgres
@pytest.mark.integration
def test_postgresql_rate_limit_is_atomic_under_concurrency(postgres_session_factory):
    scope = f"concurrency:{uuid.uuid4().hex}"

    def attempt(_):
        with postgres_session_factory() as session:
            return check_rate_limit(
                session, scope=scope, identity="198.51.100.9", limit=5, window_seconds=60
            ).allowed

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(attempt, range(20)))
    assert len(results) == 20
    assert sum(results) == 5
    with postgres_session_factory() as session:
        buckets = session.execute(select(RateLimitBucket).where(RateLimitBucket.scope == scope)).scalars().all()
        assert len(buckets) == 1
        assert buckets[0].request_count == 20
