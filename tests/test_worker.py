from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.db.models.email_delivery_job import EmailDeliveryJob
from app.db.models.endpoint_delivery_log import EndpointDeliveryLog
from app.db.models.form_endpoint_recipient import FormEndpointRecipient
from app.services import worker
from app.services.delivery_queue import claim_job, enqueue_delivery
from app.services.email import PermanentEmailError, TemporaryEmailError


def add_job(session, endpoint, snapshot):
    job = enqueue_delivery(session, endpoint_id=endpoint.id, snapshot=snapshot)
    session.flush()
    log = EndpointDeliveryLog(
        endpoint_id=endpoint.id, success=True, cap_verified=False, delivery_job_id=job.id,
        delivery_status="queued", smtp_host=snapshot.smtp_host, smtp_port=snapshot.smtp_port,
        sender_email=snapshot.sender_email, recipient_summary=", ".join(snapshot.recipients),
    )
    session.add(log)
    session.commit()
    return job, log


async def test_worker_sends_exclusively_from_immutable_snapshot(monkeypatch, db, db_session_factory, endpoint, delivery_snapshot):
    job, log = add_job(db, endpoint, delivery_snapshot)
    endpoint.smtp_host = "edited.example.com"
    endpoint.smtp_port = 2525
    endpoint.sender_email = "edited@example.com"
    endpoint.email_subject = "Edited subject"
    endpoint.is_active = False
    endpoint.is_deleted = True
    db.query(FormEndpointRecipient).filter_by(endpoint_id=endpoint.id).update({"email": "edited-recipient@example.com"})
    db.commit()
    smtp = AsyncMock()
    monkeypatch.setattr(worker, "send_submission_email", smtp)

    assert await worker.process_one("worker-1", session_factory=db_session_factory, heartbeat_seconds=0.01)
    smtp.assert_awaited_once()
    sent = smtp.await_args.kwargs
    assert sent == {
        "smtp_host": "smtp.example.com", "smtp_port": 587, "smtp_username": "smtp-user",
        "smtp_password": "smtp-secret", "smtp_security": "starttls",
        "sender_email": "forms@example.com", "sender_name": "Billson Forms",
        "recipients": ["team@example.com"], "subject": "Accepted subject",
        "body": "New form submission\n\nname: Ada\nemail: ada@example.com\nmessage: private form content",
        "reply_to_email": "ada@example.com",
    }
    db.expire_all()
    assert db.get(EmailDeliveryJob, job.id).status == "delivered"
    assert db.get(EmailDeliveryJob, job.id).encrypted_payload is None
    assert db.get(EndpointDeliveryLog, log.id).delivery_status == "delivered"


@pytest.mark.parametrize(
    ("exception", "expected_status", "payload_destroyed", "error_prefix"),
    [
        (TemporaryEmailError("timeout"), "queued", False, "Temporary SMTP failure"),
        (PermanentEmailError("bad credentials"), "failed", True, "Permanent SMTP failure"),
    ],
)
async def test_worker_classifies_smtp_failures(monkeypatch, db, db_session_factory, endpoint, delivery_snapshot, exception, expected_status, payload_destroyed, error_prefix):
    job, log = add_job(db, endpoint, delivery_snapshot)
    monkeypatch.setattr(worker, "send_submission_email", AsyncMock(side_effect=exception))
    await worker.process_one("worker-1", session_factory=db_session_factory, heartbeat_seconds=0.01)
    db.expire_all()
    refreshed_job = db.get(EmailDeliveryJob, job.id)
    refreshed_log = db.get(EndpointDeliveryLog, log.id)
    assert refreshed_job.status == expected_status
    assert (refreshed_job.encrypted_payload is None) is payload_destroyed
    assert refreshed_log.delivery_status == expected_status
    assert refreshed_log.success is False
    assert refreshed_log.error_message.startswith(error_prefix)


async def test_malformed_snapshot_fails_safely_without_smtp(monkeypatch, db, db_session_factory, endpoint, delivery_snapshot):
    job, log = add_job(db, endpoint, delivery_snapshot)
    job.encrypted_payload = "corrupt"
    db.commit()
    smtp = AsyncMock()
    monkeypatch.setattr(worker, "send_submission_email", smtp)
    await worker.process_one("worker-1", session_factory=db_session_factory)
    smtp.assert_not_awaited()
    db.expire_all()
    assert db.get(EmailDeliveryJob, job.id).status == "failed"
    assert db.get(EmailDeliveryJob, job.id).encrypted_payload is None
    assert db.get(EndpointDeliveryLog, log.id).delivery_status == "failed"


async def test_heartbeat_refreshes_lock_and_stops_after_processing(monkeypatch, db, db_session_factory, endpoint, delivery_snapshot):
    job, _ = add_job(db, endpoint, delivery_snapshot)
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0
    original = worker.refresh_job_heartbeat

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    async def slow_smtp(**kwargs):
        started.set()
        await release.wait()

    monkeypatch.setattr(worker, "refresh_job_heartbeat", counted)
    monkeypatch.setattr(worker, "send_submission_email", slow_smtp)
    task = asyncio.create_task(worker.process_one("worker-1", session_factory=db_session_factory, heartbeat_seconds=0.02))
    await started.wait()
    await asyncio.sleep(0.08)
    with db_session_factory() as inspection:
        locked_at = inspection.get(EmailDeliveryJob, job.id).locked_at
        assert locked_at is not None
    assert calls >= 2
    release.set()
    await task
    stopped_at = calls
    await asyncio.sleep(0.06)
    assert calls == stopped_at


async def test_worker_that_loses_ownership_cannot_finalize_or_overwrite_log(monkeypatch, db, db_session_factory, endpoint, delivery_snapshot):
    job, log = add_job(db, endpoint, delivery_snapshot)

    def lose_ownership(job_id, worker_id, **kwargs):
        with db_session_factory() as other:
            claimed = other.get(EmailDeliveryJob, job_id)
            claimed.locked_by = "worker-2"
            other.commit()
        return False

    async def yielding_smtp(**kwargs):
        await asyncio.sleep(0.03)

    monkeypatch.setattr(worker, "refresh_job_heartbeat", lose_ownership)
    monkeypatch.setattr(worker, "send_submission_email", yielding_smtp)
    await worker.process_one("worker-1", session_factory=db_session_factory, heartbeat_seconds=0.01)
    db.expire_all()
    preserved = db.get(EmailDeliveryJob, job.id)
    preserved_log = db.get(EndpointDeliveryLog, log.id)
    assert preserved.status == "processing" and preserved.locked_by == "worker-2"
    assert preserved.encrypted_payload is not None
    assert preserved_log.delivery_status == "queued"


def test_genuinely_stale_job_can_be_reclaimed(db, endpoint, delivery_snapshot, monkeypatch):
    job, _ = add_job(db, endpoint, delivery_snapshot)
    monkeypatch.setattr(settings, "queue_lock_timeout_seconds", 10)
    now = datetime.now(timezone.utc)
    assert claim_job(db, "worker-1", now=now).id == job.id
    reclaimed = claim_job(db, "worker-2", now=now + timedelta(seconds=11))
    assert reclaimed and reclaimed.id == job.id and reclaimed.locked_by == "worker-2"


@pytest.mark.postgres
@pytest.mark.integration
def test_postgresql_genuinely_stale_job_can_be_reclaimed(monkeypatch, postgres_session_factory, endpoint_factory, delivery_snapshot):
    with postgres_session_factory() as session:
        endpoint = endpoint_factory(session)
        job, _ = add_job(session, endpoint, delivery_snapshot)
        job_id = job.id
    monkeypatch.setattr(settings, "queue_lock_timeout_seconds", 10)
    now = datetime.now(timezone.utc)
    with postgres_session_factory() as first:
        assert claim_job(first, "worker-1", now=now).id == job_id
    with postgres_session_factory() as second:
        reclaimed = claim_job(second, "worker-2", now=now + timedelta(seconds=11))
        assert reclaimed and reclaimed.id == job_id and reclaimed.locked_by == "worker-2"


@pytest.mark.postgres
@pytest.mark.integration
async def test_live_heartbeat_prevents_reclaim(monkeypatch, postgres_session_factory, endpoint_factory, delivery_snapshot):
    with postgres_session_factory() as session:
        endpoint = endpoint_factory(session)
        job, _ = add_job(session, endpoint, delivery_snapshot)
    monkeypatch.setattr(settings, "queue_lock_timeout_seconds", 1)
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_smtp(**kwargs):
        started.set()
        await release.wait()

    monkeypatch.setattr(worker, "send_submission_email", slow_smtp)
    task = asyncio.create_task(worker.process_one("worker-1", session_factory=postgres_session_factory, heartbeat_seconds=0.05))
    await started.wait()
    await asyncio.sleep(1.15)
    with postgres_session_factory() as second:
        assert claim_job(second, "worker-2") is None
    release.set()
    await task


@pytest.mark.postgres
@pytest.mark.integration
async def test_two_workers_cannot_process_same_job(monkeypatch, postgres_session_factory, endpoint_factory, delivery_snapshot):
    with postgres_session_factory() as session:
        endpoint = endpoint_factory(session)
        add_job(session, endpoint, delivery_snapshot)
    started = asyncio.Event()
    release = asyncio.Event()
    sends = 0

    async def slow_smtp(**kwargs):
        nonlocal sends
        sends += 1
        started.set()
        await release.wait()

    monkeypatch.setattr(worker, "send_submission_email", slow_smtp)
    first = asyncio.create_task(worker.process_one("worker-1", session_factory=postgres_session_factory, heartbeat_seconds=0.05))
    await started.wait()
    assert await worker.process_one("worker-2", session_factory=postgres_session_factory, heartbeat_seconds=0.05) is False
    release.set()
    await first
    assert sends == 1
