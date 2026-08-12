from __future__ import annotations

import json
from urllib.parse import parse_qs

from fastapi import HTTPException, Request, status

SUPPORTED_CONTENT_TYPES = {"application/json", "application/x-www-form-urlencoded"}


async def read_limited_body(request: Request, limit_bytes: int) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) < 0:
                raise ValueError
            if int(content_length) > limit_bytes:
                raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Payload too large.")
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid Content-Length header.") from exc
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit_bytes:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Payload too large.")
    return bytes(body)


async def parse_submission_payload(request: Request, limit_bytes: int) -> tuple[dict[str, object], int]:
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type not in SUPPORTED_CONTENT_TYPES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only application/json and application/x-www-form-urlencoded are supported; file uploads are not accepted.")
    body = await read_limited_body(request, limit_bytes)
    try:
        if media_type == "application/json":
            value = json.loads(body or b"{}")
            if not isinstance(value, dict):
                raise ValueError("JSON payload must be an object.")
            return value, len(body)
        decoded = body.decode("utf-8", errors="strict")
        parsed = parse_qs(decoded, keep_blank_values=True, strict_parsing=False, max_num_fields=1000)
        payload = {key: values[-1] if len(values) == 1 else values for key, values in parsed.items()}
        return payload, len(body)
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Malformed submission body.") from exc
