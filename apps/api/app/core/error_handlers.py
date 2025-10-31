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
    """Register global exception handlers for consistent JSON errors."""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException):  # type: ignore[override]
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    @app.exception_handler(ServiceError)
    async def service_error_handler(_: Request, exc: ServiceError):  # type: ignore[override]
        logger.warning("ServiceError: %s", exc)
        return JSONResponse(
            status_code=400,
            content={"error": exc.code, "detail": str(exc)},
        )

    @app.exception_handler(PydanticValidationError)
    async def pydantic_validation_handler(_: Request, exc: PydanticValidationError):  # type: ignore[override]
        return JSONResponse(
            status_code=422,
            content={"error": "validation_error", "detail": exc.errors()},
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_error_handler(_: Request, exc: SQLAlchemyError):  # type: ignore[override]
        logger.exception("Database error")
        return JSONResponse(
            status_code=500,
            content={"error": "database_error", "detail": "An internal database error occurred."},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(_: Request, exc: Exception):  # type: ignore[override]
        logger.exception("Unhandled error")
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "detail": "An unexpected error occurred."},
        )
