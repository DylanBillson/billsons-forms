from datetime import datetime, timedelta, timezone

import pytest

from app.db.models.email_delivery_job import EmailDeliveryJob
from app.db.models.form_endpoint_recipient import FormEndpointRecipient
from app.core.encryption import encrypt_value
from app.services.delivery_queue import (
    DeliverySnapshotError,
    claim_job,
    complete_job,
    decrypt_job_snapshot,
    enqueue_delivery,
    fail_job,
    retry_backoff_seconds,
)


def queued(db, endpoint, snapshot):
    job = enqueue_delivery(db, endpoint_id=endpoint.id, snapshot=snapshot)
    db.commit()
    return job


def test_snapshot_contains_every_accepted_delivery_value(db, endpoint, delivery_snapshot):
    job = queued(db, endpoint, delivery_snapshot)
    decoded = decrypt_job_snapshot(job)
    assert decoded.submitted_fields["message"] == "private form content"
    assert decoded.recipients == ["team@example.com"]
    assert (decoded.smtp_host, decoded.smtp_port, decoded.smtp_username, decoded.smtp_password) == (
        "smtp.example.com", 587, "smtp-user", "smtp-secret"
    )
    assert decoded.sender_email == "forms@example.com"
    assert decoded.sender_name == "Billson Forms"
    assert decoded.subject == "Accepted subject"
    assert decoded.smtp_security == "starttls"
    assert decoded.reply_to_email == "ada@example.com"


def test_snapshot_is_encrypted_and_plaintext_is_absent_from_job_columns(db, endpoint, delivery_snapshot):
    job = queued(db, endpoint, delivery_snapshot)
    values = " ".join(str(value) for value in vars(job).values() if value is not None)
    assert "private form content" not in values
    assert "smtp-secret" not in values
    assert job.encrypted_payload and "team@example.com" not in job.encrypted_payload


def test_endpoint_and_recipient_edits_do_not_change_snapshot(db, endpoint, delivery_snapshot):
    job = queued(db, endpoint, delivery_snapshot)
    endpoint.smtp_host = "new-smtp.example.com"
    endpoint.sender_email = "changed@example.com"
    recipient = db.query(FormEndpointRecipient).filter_by(endpoint_id=endpoint.id).one()
    recipient.email = "new-recipient@example.com"
    endpoint.is_active = False
    endpoint.is_deleted = True
    db.commit()
    decoded = decrypt_job_snapshot(job)
    assert decoded.smtp_host == "smtp.example.com"
    assert decoded.sender_email == "forms@example.com"
    assert decoded.recipients == ["team@example.com"]


def test_hard_deleted_endpoint_sets_reporting_fk_null_without_invalidating_snapshot(db, endpoint, delivery_snapshot):
    job = queued(db, endpoint, delivery_snapshot)
    db.query(FormEndpointRecipient).filter_by(endpoint_id=endpoint.id).delete()
    db.delete(endpoint)
    db.commit()
    db.refresh(job)
    assert job.endpoint_id is None
    assert decrypt_job_snapshot(job).subject == "Accepted subject"


def test_success_destroys_encrypted_snapshot(db, endpoint, delivery_snapshot):
    job = queued(db, endpoint, delivery_snapshot)
    assert claim_job(db, "worker-1").id == job.id
    assert complete_job(db, job.id, "worker-1")
    db.refresh(job)
    assert job.status == "delivered" and job.encrypted_payload is None


def test_terminal_failure_destroys_snapshot_but_retry_retains_it(db, endpoint, delivery_snapshot):
    retry_job = queued(db, endpoint, delivery_snapshot)
    claim_job(db, "worker-1")
    assert fail_job(db, retry_job.id, "worker-1", "temporary", retryable=True) == "queued"
    db.refresh(retry_job)
    assert retry_job.encrypted_payload is not None
    retry_job.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    retry_job.max_attempts = retry_job.attempts + 1
    db.commit()
    claim_job(db, "worker-2")
    assert fail_job(db, retry_job.id, "worker-2", "still failing", retryable=True) == "failed"
    db.refresh(retry_job)
    assert retry_job.encrypted_payload is None and retry_job.terminal_at is not None


def test_permanent_failure_and_maximum_attempts_are_terminal(db, endpoint, delivery_snapshot):
    permanent = queued(db, endpoint, delivery_snapshot)
    claim_job(db, "worker-1")
    assert fail_job(db, permanent.id, "worker-1", "bad credentials", retryable=False) == "failed"
    db.refresh(permanent)
    assert permanent.encrypted_payload is None

    maximum = queued(db, endpoint, delivery_snapshot)
    maximum.max_attempts = 1
    db.commit()
    claim_job(db, "worker-2")
    assert fail_job(db, maximum.id, "worker-2", "timeout", retryable=True) == "failed"


def test_exponential_backoff_is_bounded():
    assert retry_backoff_seconds(1) == 15
    assert retry_backoff_seconds(2) == 30
    assert retry_backoff_seconds(20) == 3600
    assert retry_backoff_seconds(10_000) == 3600


@pytest.mark.parametrize("encrypted", ["not-fernet", None, encrypt_value('{"version":1,"submitted_fields":{}}')])
def test_malformed_or_missing_snapshot_fails_strict_decoding(db, endpoint, delivery_snapshot, encrypted):
    job = queued(db, endpoint, delivery_snapshot)
    job.encrypted_payload = encrypted
    db.commit()
    with pytest.raises(DeliverySnapshotError):
        decrypt_job_snapshot(job)


def test_completion_by_worker_that_lost_ownership_is_rejected(db, endpoint, delivery_snapshot):
    job = queued(db, endpoint, delivery_snapshot)
    claim_job(db, "worker-1")
    job.locked_by = "worker-2"
    db.commit()
    assert not complete_job(db, job.id, "worker-1")


@pytest.mark.postgres
@pytest.mark.integration
def test_postgresql_fk_sets_endpoint_null_and_preserves_job(postgres_session_factory, endpoint_factory, delivery_snapshot):
    with postgres_session_factory() as session:
        endpoint = endpoint_factory(session)
        job = enqueue_delivery(session, endpoint_id=endpoint.id, snapshot=delivery_snapshot)
        session.commit()
        job_id = job.id
        session.query(FormEndpointRecipient).filter_by(endpoint_id=endpoint.id).delete()
        session.delete(endpoint)
        session.commit()

    # Use a completely fresh identity map so this verifies PostgreSQL's
    # ON DELETE SET NULL result, not a cached expire_on_commit=False object.
    with postgres_session_factory() as verification_session:
        preserved = verification_session.get(EmailDeliveryJob, job_id)
        assert preserved is not None
        assert preserved.endpoint_id is None
        assert decrypt_job_snapshot(preserved) == delivery_snapshot
