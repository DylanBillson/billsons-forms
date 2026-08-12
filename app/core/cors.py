from __future__ import annotations

from fastapi import Request
from fastapi.responses import Response

from app.core.origins import normalize_origin, OriginError

ALLOWED_METHODS = "POST, OPTIONS"
ALLOWED_HEADERS = {"accept", "content-type"}


def add_vary_origin(response: Response) -> None:
    current = response.headers.get("Vary", "")
    values = {item.strip() for item in current.split(",") if item.strip()}
    values.add("Origin")
    response.headers["Vary"] = ", ".join(sorted(values))


def apply_cors(response: Response, origin: str | None, allowed_origins: list[str]) -> Response:
    add_vary_origin(response)
    if origin:
        try:
            normalized = normalize_origin(origin)
        except OriginError:
            return response
        if not allowed_origins or normalized in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = normalized
    return response


def preflight_response(request: Request, allowed_origins: list[str], allowed: bool) -> Response:
    if not allowed:
        response = Response(status_code=403)
        return apply_cors(response, request.headers.get("origin"), allowed_origins)
    requested_method = request.headers.get("access-control-request-method", "").upper()
    requested_headers = {
        item.strip().lower()
        for item in request.headers.get("access-control-request-headers", "").split(",")
        if item.strip()
    }
    if requested_method != "POST" or not requested_headers.issubset(ALLOWED_HEADERS):
        response = Response(status_code=403)
        return apply_cors(response, request.headers.get("origin"), allowed_origins)
    response = Response(status_code=204)
    apply_cors(response, request.headers.get("origin"), allowed_origins)
    response.headers["Access-Control-Allow-Methods"] = ALLOWED_METHODS
    response.headers["Access-Control-Allow-Headers"] = ", ".join(sorted(ALLOWED_HEADERS))
    response.headers["Access-Control-Max-Age"] = "600"
    return response
