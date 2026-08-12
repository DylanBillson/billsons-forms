import pytest
from fastapi import HTTPException
from starlette.requests import Request
from app.services.payloads import parse_submission_payload


def make_request(body: bytes, content_type: str):
    sent = False
    async def receive():
        nonlocal sent
        if sent: return {"type": "http.request", "body": b"", "more_body": False}
        sent = True; return {"type": "http.request", "body": body, "more_body": False}
    return Request({"type": "http", "method": "POST", "path": "/", "headers": [(b"content-type", content_type.encode())]}, receive)


async def test_stream_limit_is_enforced():
    with pytest.raises(HTTPException) as exc: await parse_submission_payload(make_request(b"{}" * 10, "application/json"), 5)
    assert exc.value.status_code == 413


async def test_multipart_is_rejected():
    with pytest.raises(HTTPException) as exc: await parse_submission_payload(make_request(b"x", "multipart/form-data"), 100)
    assert exc.value.status_code == 415
