class ServiceError(Exception):
    """Base class for service-layer errors."""

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        self.code = code or "service_error"


class NotFoundError(ServiceError):
    def __init__(self, message: str = "Not found"):
        super().__init__(message, code="not_found")


class ValidationError(ServiceError):
    def __init__(self, message: str = "Validation error"):
        super().__init__(message, code="validation_error")
