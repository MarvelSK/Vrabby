from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import ServiceError

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers for consistent JSON errors.

    Response envelope shape (aligned with frontend expectations):
    {
      "type": "error",
      "error": {"type": "<error_code>", "message": "<human message>"},
      "request_id": "<uuid>"
    }
    """
    import uuid

    def _request_id(request: Request) -> str:
        try:
            rid = request.headers.get("x-request-id") or getattr(getattr(request, "state", object()), "request_id", None)
            return str(rid) if rid else str(uuid.uuid4())
        except Exception:
            return str(uuid.uuid4())

    def _json_error(request: Request, status: int, err_type: str, message: str) -> JSONResponse:
        rid = _request_id(request)
        return JSONResponse(
            status_code=status,
            content={
                "type": "error",
                "error": {"type": err_type, "message": message},
                "request_id": rid,
            },
            headers={"X-Request-ID": rid},
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):  # type: ignore[override]
        # Map common HTTP status codes to stable error types
        code_map = {
            400: "bad_request",
            401: "unauthorized",
            402: "payment_required",
            403: "forbidden",
            404: "not_found",
            409: "conflict",
            422: "validation_error",
            429: "rate_limit_exceeded",
            503: "service_unavailable",
        }
        err_type = code_map.get(exc.status_code, "api_error")
        # FastAPI may pass dict or str as detail
        detail = exc.detail if isinstance(exc.detail, str) else getattr(exc.detail, "get", lambda k, d=None: None)("message", None) or str(exc.detail)
        return _json_error(request, exc.status_code, err_type, detail or "Request failed")

    @app.exception_handler(ServiceError)
    async def service_error_handler(request: Request, exc: ServiceError):  # type: ignore[override]
        logger.warning("ServiceError: %s", exc)
        return _json_error(request, 400, exc.code or "service_error", str(exc))

    @app.exception_handler(PydanticValidationError)
    async def pydantic_validation_handler(request: Request, exc: PydanticValidationError):  # type: ignore[override]
        return _json_error(request, 422, "validation_error", "Invalid request payload")

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError):  # type: ignore[override]
        logger.exception("Database error")
        return _json_error(request, 500, "database_error", "An internal database error occurred.")

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):  # type: ignore[override]
        logger.exception("Unhandled error")
        return _json_error(request, 500, "api_error", "Internal server error")
