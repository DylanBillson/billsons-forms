from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models.rate_limit_bucket import RateLimitBucket


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int


def _window(now: datetime, seconds: int) -> tuple[datetime, datetime]:
    epoch = int(now.timestamp())
    start = datetime.fromtimestamp(epoch - (epoch % seconds), tz=timezone.utc)
    return start, start + timedelta(seconds=seconds)


def _subject(identity: str) -> str:
    return sha256(identity.encode("utf-8")).hexdigest()


def check_rate_limit(db: Session, *, scope: str, identity: str, limit: int, window_seconds: int, now: datetime | None = None) -> RateLimitResult:
    now = now or datetime.now(timezone.utc)
    start, end = _window(now, window_seconds)
    subject = _subject(identity)
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        statement = pg_insert(RateLimitBucket).values(
            scope=scope, subject_key=subject, window_start=start, request_count=1, expires_at=end
        ).on_conflict_do_update(
            constraint="uq_rate_limit_bucket",
            set_={"request_count": RateLimitBucket.request_count + 1, "expires_at": end},
        ).returning(RateLimitBucket.request_count)
        count = int(db.execute(statement).scalar_one())
        db.commit()
    else:
        bucket = db.execute(select(RateLimitBucket).where(
            RateLimitBucket.scope == scope,
            RateLimitBucket.subject_key == subject,
            RateLimitBucket.window_start == start,
        )).scalar_one_or_none()
        if bucket is None:
            bucket = RateLimitBucket(scope=scope, subject_key=subject, window_start=start, request_count=1, expires_at=end)
            db.add(bucket)
            count = 1
        else:
            bucket.request_count += 1
            count = bucket.request_count
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return check_rate_limit(db, scope=scope, identity=identity, limit=limit, window_seconds=window_seconds, now=now)
    retry_after = max(1, int((end - now).total_seconds()) + 1)
    return RateLimitResult(count <= limit, limit, max(0, limit - count), retry_after)
