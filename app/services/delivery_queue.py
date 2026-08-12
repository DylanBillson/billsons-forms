from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue, ValidationError, field_validator, model_validator
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.encryption import decrypt_value, encrypt_value
from app.core.endpoint_validation import is_email
from app.core.network_validation import HostValidationError, normalize_hostname
from app.db.models.email_delivery_job import EmailDeliveryJob


class DeliverySnapshotError(ValueError):
    pass


class DeliverySnapshot(BaseModel):
    """Immutable, versioned configuration required to deliver one accepted submission."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    version: Literal[1] = 1
    submitted_fields: dict[str, JsonValue]
    recipients: list[str]
    sender_email: str
    sender_name: str | None = None
    subject: str
    smtp_host: str
    smtp_port: int
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_security: Literal["none", "starttls", "ssl"]
    reply_to_email: str | None = None

    @field_validator("recipients")
    @classmethod
    def validate_recipients(cls, recipients: list[str]) -> list[str]:
        if not recipients or any(not is_email(value) for value in recipients):
            raise ValueError("snapshot requires at least one valid recipient")
        if len(set(recipients)) != len(recipients):
            raise ValueError("snapshot recipients must not contain duplicates")
        return recipients

    @field_validator("sender_email")
    @classmethod
    def validate_sender(cls, value: str) -> str:
        if not is_email(value):
            raise ValueError("snapshot sender email is invalid")
        return value

    @field_validator("reply_to_email")
    @classmethod
    def validate_reply_to(cls, value: str | None) -> str | None:
        if value is not None and not is_email(value):
            raise ValueError("snapshot Reply-To email is invalid")
        return value

    @field_validator("smtp_host")
    @classmethod
    def validate_smtp_host(cls, value: str) -> str:
        try:
            normalized = normalize_hostname(value)
        except HostValidationError as exc:
            raise ValueError("snapshot SMTP hostname is invalid") from exc
        if normalized != value:
            raise ValueError("snapshot SMTP hostname must already be canonical")
        return value

    @field_validator("smtp_port")
    @classmethod
    def validate_smtp_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("snapshot SMTP port is invalid")
        return value

    @model_validator(mode="after")
    def validate_strings(self):
        if not self.subject or len(self.subject) > 255:
            raise ValueError("snapshot subject is invalid")
        if any(not key or len(key) > 500 for key in self.submitted_fields):
            raise ValueError("snapshot submitted field name is invalid")
        return self


def create_delivery_snapshot(
    *,
    submitted_fields: dict[str, object],
    recipients: list[str],
    sender_email: str,
    sender_name: str | None,
    subject: str,
    smtp_host: str,
    smtp_port: int,
    smtp_username: str | None,
    smtp_password: str | None,
    smtp_security: str,
    reply_to_email: str | None,
) -> DeliverySnapshot:
    try:
        return DeliverySnapshot.model_validate(
            {
                "version": 1,
                "submitted_fields": submitted_fields,
                "recipients": recipients,
                "sender_email": sender_email,
                "sender_name": sender_name,
                "subject": subject,
                "smtp_host": normalize_hostname(smtp_host),
                "smtp_port": smtp_port,
                "smtp_username": smtp_username,
                "smtp_password": smtp_password,
                "smtp_security": smtp_security,
                "reply_to_email": reply_to_email,
            },
            strict=True,
        )
    except (ValidationError, HostValidationError) as exc:
        raise DeliverySnapshotError("Delivery snapshot configuration is invalid.") from exc


def enqueue_delivery(db: Session, *, endpoint_id: int | None, snapshot: DeliverySnapshot) -> EmailDeliveryJob:
    encoded = snapshot.model_dump_json()
    job = EmailDeliveryJob(
        endpoint_id=endpoint_id,
        encrypted_payload=encrypt_value(encoded),
        status="queued",
        attempts=0,
        max_attempts=settings.queue_max_attempts,
        available_at=datetime.now(timezone.utc),
    )
    db.add(job)
    db.flush()
    return job


def decrypt_job_snapshot(job: EmailDeliveryJob) -> DeliverySnapshot:
    if not job.encrypted_payload:
        raise DeliverySnapshotError("Queued delivery snapshot is missing.")
    try:
        raw = decrypt_value(job.encrypted_payload)
        if raw is None:
            raise ValueError("empty encrypted value")
        decoded = json.loads(raw)
        return DeliverySnapshot.model_validate(decoded, strict=True)
    except Exception as exc:
        raise DeliverySnapshotError("Queued delivery snapshot could not be decrypted or validated.") from exc


def claim_job(db: Session, worker_id: str, *, now: datetime | None = None) -> EmailDeliveryJob | None:
    now = now or datetime.now(timezone.utc)
    stale = now - timedelta(seconds=settings.queue_lock_timeout_seconds)
    statement = (
        select(EmailDeliveryJob)
        .where(EmailDeliveryJob.available_at <= now)
        .where(
            or_(
                EmailDeliveryJob.status == "queued",
                (EmailDeliveryJob.status == "processing")
                & or_(EmailDeliveryJob.locked_at.is_(None), EmailDeliveryJob.locked_at < stale),
            )
        )
        .order_by(EmailDeliveryJob.available_at, EmailDeliveryJob.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    job = db.execute(statement).scalar_one_or_none()
    if job:
        job.status = "processing"
        job.locked_at = now
        job.locked_by = worker_id
        job.attempts += 1
        db.commit()
        db.refresh(job)
    return job


def refresh_job_heartbeat(
    job_id: int,
    worker_id: str,
    *,
    session_factory: Callable[[], Session] | None = None,
    now: datetime | None = None,
) -> bool:
    """Refresh ownership in a short independent transaction visible to other workers."""
    if session_factory is None:
        from app.db.session import SessionLocal

        session_factory = SessionLocal
    with session_factory() as heartbeat_db:
        result = heartbeat_db.execute(
            update(EmailDeliveryJob)
            .where(
                EmailDeliveryJob.id == job_id,
                EmailDeliveryJob.status == "processing",
                EmailDeliveryJob.locked_by == worker_id,
            )
            .values(locked_at=now or datetime.now(timezone.utc))
        )
        heartbeat_db.commit()
        return (result.rowcount or 0) == 1


def complete_job(db: Session, job_id: int, worker_id: str) -> bool:
    now = datetime.now(timezone.utc)
    result = db.execute(
        update(EmailDeliveryJob)
        .where(
            EmailDeliveryJob.id == job_id,
            EmailDeliveryJob.status == "processing",
            EmailDeliveryJob.locked_by == worker_id,
        )
        .values(
            status="delivered", delivered_at=now, terminal_at=now, encrypted_payload=None,
            locked_at=None, locked_by=None, last_error=None,
        )
    )
    db.commit()
    return (result.rowcount or 0) == 1


def retry_backoff_seconds(attempts: int) -> int:
    return min(3600, 15 * (2 ** max(0, min(attempts - 1, 20))))


def fail_job(db: Session, job_id: int, worker_id: str, error: str, *, retryable: bool) -> str | None:
    job = db.execute(
        select(EmailDeliveryJob)
        .where(
            EmailDeliveryJob.id == job_id,
            EmailDeliveryJob.status == "processing",
            EmailDeliveryJob.locked_by == worker_id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if job is None:
        db.rollback()
        return None
    now = datetime.now(timezone.utc)
    job.last_error = error[:2000]
    job.locked_at = None
    job.locked_by = None
    if retryable and job.attempts < job.max_attempts:
        job.status = "queued"
        job.available_at = now + timedelta(seconds=retry_backoff_seconds(job.attempts))
    else:
        job.status = "failed"
        job.terminal_at = now
        job.encrypted_payload = None
    status = job.status
    db.commit()
    return status
