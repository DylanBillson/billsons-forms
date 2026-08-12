from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.db.models.audit_log import AuditLog
from app.db.models.email_delivery_job import EmailDeliveryJob
from app.db.models.rate_limit_bucket import RateLimitBucket
from app.services.delivery_queue import enqueue_delivery
from app.services.retention import cleanup_expired_data


def test_retention_uses_separate_lifetimes(db):
    now = datetime.now(timezone.utc)
    old_audit = AuditLog(action="old", created_at=now - timedelta(days=731))
    recent_audit = AuditLog(action="recent", created_at=now - timedelta(days=100))
    bucket = RateLimitBucket(scope="x", subject_key="y", window_start=now - timedelta(hours=3), request_count=1, expires_at=now - timedelta(hours=2))
    db.add_all([old_audit, recent_audit, bucket]); db.commit()
    result = cleanup_expired_data(db, now)
    assert result.audit_logs == 1 and result.rate_buckets == 1
    assert db.query(AuditLog).count() == 1


def test_terminal_queue_metadata_expires_but_retryable_jobs_survive(db, endpoint, delivery_snapshot, monkeypatch):
    monkeypatch.setattr(settings, "queue_terminal_retention_days", 7)
    now = datetime.now(timezone.utc)

    delivered = enqueue_delivery(db, endpoint_id=endpoint.id, snapshot=delivery_snapshot)
    failed = enqueue_delivery(db, endpoint_id=endpoint.id, snapshot=delivery_snapshot)
    queued = enqueue_delivery(db, endpoint_id=endpoint.id, snapshot=delivery_snapshot)
    db.flush()
    delivered.status = "delivered"; delivered.encrypted_payload = None; delivered.terminal_at = now - timedelta(days=8)
    failed.status = "failed"; failed.encrypted_payload = None; failed.terminal_at = now - timedelta(days=8)
    queued.status = "queued"; queued.available_at = now - timedelta(days=30); queued.terminal_at = None
    db.commit()

    result = cleanup_expired_data(db, now)
    assert result.queue_jobs == 2
    assert db.get(EmailDeliveryJob, queued.id) is not None
    assert db.get(EmailDeliveryJob, queued.id).encrypted_payload is not None


def test_recent_terminal_jobs_are_retained_after_payload_destruction(db, endpoint, delivery_snapshot):
    now = datetime.now(timezone.utc)
    job = enqueue_delivery(db, endpoint_id=endpoint.id, snapshot=delivery_snapshot)
    db.flush()
    job.status = "delivered"; job.encrypted_payload = None; job.terminal_at = now - timedelta(days=1)
    db.commit()
    cleanup_expired_data(db, now)
    assert db.get(EmailDeliveryJob, job.id) is not None
