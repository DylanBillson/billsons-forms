from __future__ import annotations

import asyncio
import socket
import uuid
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.endpoint_delivery_log import EndpointDeliveryLog
from app.db.session import SessionLocal
from app.services.delivery_queue import (
    DeliverySnapshotError,
    claim_job,
    complete_job,
    decrypt_job_snapshot,
    fail_job,
    refresh_job_heartbeat,
)
from app.services.email import PermanentEmailError, TemporaryEmailError, build_submission_email_body, send_submission_email


async def heartbeat_job(
    job_id: int,
    worker_id: str,
    stop_event: asyncio.Event,
    ownership_lost: asyncio.Event,
    *,
    session_factory: Callable[[], Session],
    interval_seconds: float,
) -> None:
    while not stop_event.is_set():
        try:
            still_owned = await asyncio.to_thread(
                refresh_job_heartbeat,
                job_id,
                worker_id,
                session_factory=session_factory,
            )
        except Exception:
            still_owned = False
        if not still_owned:
            ownership_lost.set()
            return
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except TimeoutError:
            continue


async def stop_heartbeat(stop_event: asyncio.Event, task: asyncio.Task[None]) -> None:
    stop_event.set()
    try:
        await task
    except asyncio.CancelledError:
        pass


def update_delivery_log(db: Session, job_id: int, *, success: bool, delivery_status: str, error: str | None) -> None:
    db.query(EndpointDeliveryLog).filter_by(delivery_job_id=job_id).update(
        {"success": success, "delivery_status": delivery_status, "error_message": error},
        synchronize_session=False,
    )
    db.commit()


async def process_one(
    worker_id: str,
    *,
    session_factory: Callable[[], Session] | None = None,
    heartbeat_seconds: float | None = None,
) -> bool:
    session_factory = session_factory or SessionLocal
    db = session_factory()
    job = None
    try:
        job = claim_job(db, worker_id)
        if not job:
            return False
        try:
            snapshot = decrypt_job_snapshot(job)
        except DeliverySnapshotError as exc:
            new_status = fail_job(db, job.id, worker_id, str(exc), retryable=False)
            if new_status:
                update_delivery_log(db, job.id, success=False, delivery_status=new_status, error="Invalid encrypted delivery snapshot.")
            return True

        stop_event = asyncio.Event()
        ownership_lost = asyncio.Event()
        heartbeat_task = asyncio.create_task(
            heartbeat_job(
                job.id,
                worker_id,
                stop_event,
                ownership_lost,
                session_factory=session_factory,
                interval_seconds=heartbeat_seconds or settings.queue_heartbeat_seconds,
            )
        )
        delivery_error: Exception | None = None
        try:
            await send_submission_email(
                smtp_host=snapshot.smtp_host,
                smtp_port=snapshot.smtp_port,
                smtp_username=snapshot.smtp_username,
                smtp_password=snapshot.smtp_password,
                smtp_security=snapshot.smtp_security,
                sender_email=snapshot.sender_email,
                sender_name=snapshot.sender_name,
                recipients=snapshot.recipients,
                subject=snapshot.subject,
                body=build_submission_email_body(snapshot.submitted_fields),
                reply_to_email=snapshot.reply_to_email,
            )
        except Exception as exc:
            delivery_error = exc
        finally:
            await stop_heartbeat(stop_event, heartbeat_task)

        if ownership_lost.is_set():
            return True
        if delivery_error is None:
            if complete_job(db, job.id, worker_id):
                update_delivery_log(db, job.id, success=True, delivery_status="delivered", error=None)
            return True

        retryable = not isinstance(delivery_error, PermanentEmailError)
        new_status = fail_job(db, job.id, worker_id, f"{type(delivery_error).__name__}: {delivery_error}", retryable=retryable)
        if new_status:
            label = "Permanent SMTP failure" if not retryable else "Temporary SMTP failure"
            update_delivery_log(db, job.id, success=False, delivery_status=new_status, error=f"{label}: {delivery_error}")
        return True
    finally:
        db.close()


async def run_worker(poll_seconds: float) -> None:
    worker_id = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
    while True:
        if not await process_one(worker_id):
            await asyncio.sleep(poll_seconds)
