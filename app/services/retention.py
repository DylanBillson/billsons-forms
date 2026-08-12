from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.audit_log import AuditLog
from app.db.models.email_delivery_job import EmailDeliveryJob
from app.db.models.endpoint_delivery_log import EndpointDeliveryLog
from app.db.models.rate_limit_bucket import RateLimitBucket
from app.db.models.user_session import UserSession


@dataclass(frozen=True)
class CleanupResult:
    delivery_logs: int
    audit_logs: int
    sessions: int
    rate_buckets: int
    queue_jobs: int


def cleanup_expired_data(db: Session, now: datetime | None = None) -> CleanupResult:
    now = now or datetime.now(timezone.utc)
    counts = []
    policies = (
        (EndpointDeliveryLog, EndpointDeliveryLog.created_at < now - timedelta(days=settings.delivery_log_retention_days)),
        (AuditLog, AuditLog.created_at < now - timedelta(days=settings.audit_log_retention_days)),
        (UserSession, UserSession.expires_at < now - timedelta(days=settings.expired_session_retention_days)),
        (RateLimitBucket, RateLimitBucket.expires_at < now - timedelta(hours=settings.rate_limit_retention_hours)),
        (EmailDeliveryJob, (EmailDeliveryJob.terminal_at.is_not(None)) & (EmailDeliveryJob.terminal_at < now - timedelta(days=settings.queue_terminal_retention_days))),
    )
    for model, condition in policies:
        result = db.execute(delete(model).where(condition))
        counts.append(result.rowcount or 0)
    db.commit()
    return CleanupResult(*counts)
