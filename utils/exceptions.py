"""Custom HTTP exceptions for the application."""

from werkzeug.exceptions import HTTPException


class PaymentRequired(HTTPException):
    """402 Payment Required - for subscription/payment failures."""

    code = 402
    description = "Payment Required"


class TenantIsolationError(HTTPException):
    """403 Forbidden - for tenant isolation violations."""

    code = 403
    description = "Tenant isolation violation"


class SecurityBoundaryViolation(Exception):
    """Raised when a cross-tenant or unauthorized data access is detected."""

    def __init__(self, message: str = "Cross-tenant security boundary violated"):
        super().__init__(message)
