from unittest.mock import Mock

from app.core.encryption import encrypt_value
from app.core.origins import origins_to_storage
from app.db.models.email_delivery_job import EmailDeliveryJob
from app.db.models.endpoint_delivery_log import EndpointDeliveryLog
from app.db.models.rate_limit_bucket import RateLimitBucket
from app.db.models.audit_log import AuditLog
from app.services.cap import CAPResult, CAPStatus
from app.services.delivery_queue import decrypt_job_snapshot


def test_acceptance_creates_exactly_one_complete_immutable_snapshot(client, endpoint, db):
    response = client.post(
        "/api/v1/forms/contact",
        json={"name": "Ada", "email": "ada@example.com", "message": "private contents"},
        headers={"Origin": "https://site.example"},
    )
    assert response.status_code == 202
    jobs = db.query(EmailDeliveryJob).all()
    assert len(jobs) == 1
    snapshot = decrypt_job_snapshot(jobs[0])
    assert snapshot.submitted_fields == {"name": "Ada", "email": "ada@example.com", "message": "private contents"}
    assert snapshot.recipients == ["team@example.com"]
    assert snapshot.smtp_password == "smtp-secret"
    assert snapshot.reply_to_email == "ada@example.com"


def test_accepted_snapshot_and_log_reflect_endpoint_at_acceptance(client, endpoint, db):
    response = client.post("/api/v1/forms/contact", json={"email": "ada@example.com"})
    assert response.status_code == 202
    job = db.query(EmailDeliveryJob).one()
    log = db.query(EndpointDeliveryLog).one()
    endpoint.smtp_host = "edited.example.com"
    endpoint.sender_email = "edited@example.com"
    db.commit()
    snapshot = decrypt_job_snapshot(job)
    assert snapshot.smtp_host == "smtp.example.com"
    assert snapshot.sender_email == "forms@example.com"
    assert log.smtp_host == "smtp.example.com"
    assert log.sender_email == "forms@example.com"


def test_http_202_does_not_attempt_or_depend_on_smtp(client, endpoint, monkeypatch):
    smtp = Mock(side_effect=AssertionError("SMTP must not run during acceptance"))
    monkeypatch.setattr("app.services.email._send_submission_email", smtp)
    response = client.post("/api/v1/forms/contact", json={"email": "ada@example.com"})
    assert response.status_code == 202
    smtp.assert_not_called()


def test_origin_cap_and_rate_limit_finish_before_enqueue(client, endpoint, db, monkeypatch):
    endpoint.allowed_origins = origins_to_storage(["https://allowed.example"])
    db.commit()
    assert client.post("/api/v1/forms/contact", json={"email": "ada@example.com"}).status_code == 403
    assert db.query(EmailDeliveryJob).count() == 0

    endpoint.allowed_origins = None
    endpoint.cap_enabled = True
    endpoint.cap_verify_url = "https://cap.example.com/siteverify"
    endpoint.cap_secret_key = encrypt_value("cap-secret")
    db.commit()

    async def rejected(*args, **kwargs):
        return CAPResult(CAPStatus.REJECTED, "rejected")

    monkeypatch.setattr("app.api.forms.verify_cap_token", rejected)
    assert client.post("/api/v1/forms/contact", json={"email": "ada@example.com", "cap-token": "bad"}).status_code == 403
    assert db.query(EmailDeliveryJob).count() == 0

    endpoint.cap_enabled = False
    endpoint.rate_limit_requests = 1
    db.query(RateLimitBucket).delete()
    db.commit()
    assert client.post("/api/v1/forms/contact", json={"email": "ada@example.com"}).status_code == 202
    assert client.post("/api/v1/forms/contact", json={"email": "ada@example.com"}).status_code == 429
    assert db.query(EmailDeliveryJob).count() == 1


def test_invalid_reply_to_and_unsupported_upload_never_enqueue(client, endpoint, db):
    assert client.post("/api/v1/forms/contact", json={"email": "not-an-email"}).status_code == 400
    assert client.post("/api/v1/forms/contact", files={"file": ("x.txt", b"x")}).status_code == 415
    assert db.query(EmailDeliveryJob).count() == 0


def test_submission_contents_never_enter_normal_logs(client, endpoint, db):
    secret = "highly-sensitive-message-value"
    assert client.post("/api/v1/forms/contact", json={"email": "ada@example.com", "message": secret}).status_code == 202
    log = db.query(EndpointDeliveryLog).one()
    values = " ".join(str(value) for value in vars(log).values() if value is not None)
    assert secret not in values
    assert "ada@example.com" not in values
    assert db.query(AuditLog).count() == 0
