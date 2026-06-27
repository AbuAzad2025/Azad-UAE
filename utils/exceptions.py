"""Shared application exceptions."""


class SecurityBoundaryViolation(Exception):
    """Raised when a cross-tenant or unauthorized data access is detected."""

    def __init__(self, message: str = "Cross-tenant security boundary violated"):
        super().__init__(message)
