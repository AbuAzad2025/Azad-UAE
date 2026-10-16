"""
Comprehensive User Messaging & Error Governance Framework

Strict classification rules:
- SYSTEM errors (DB timeouts, unhandled 500s, code bugs):
    * Log full technical trace + correlation ID in backend.
    * User sees a calm, polite, non-technical message with the correlation ID.
    * NEVER expose raw stack traces, Python exceptions, or SQL errors.
- BUSINESS / USER errors (validation, accounting rules, permissions, state):
    * Do NOT treat as crashes; treat as guided feedback.
    * Message explains exactly what went wrong in business terms.
    * Message includes the corrective action the user must take.

All routes, services, and form validators must use this layer.
"""

from __future__ import annotations

import logging
import uuid

from flask import flash

# ------------------------------------------------------------------
# Correlation / traceability
# ------------------------------------------------------------------


def generate_correlation_id() -> str:
    return f"ERR-{uuid.uuid4().hex[:8].upper()}"


# ------------------------------------------------------------------
# Classification: System vs Business
# ------------------------------------------------------------------


class ErrorCategory:
    SYSTEM = "system"
    BUSINESS = "business"
    VALIDATION = "validation"
    SECURITY = "security"
    STATE = "state"


# ------------------------------------------------------------------
# Structured message dictionaries (bilingual: Arabic defaults + EN keys)
# ------------------------------------------------------------------

MESSAGE_REGISTRY: dict[str, dict[str, str]] = {
    # --- System (never show raw exception to user) ---
    ErrorCategory.SYSTEM: {
        "title_ar": "حدث خطأ تقني غير متوقع",
        "title_en": "Unexpected Technical Issue",
        "body_ar": (
            "واجهنا مشكلة تقنية أثناء معالجة طلبك. يرجى المحاولة مرة أخرى أو التواصل مع الدعم مع ذكر رمز الخطأ: {id}"
        ),
        "body_en": (
            "We encountered a technical issue while processing your request. "
            "Please try again or contact support quoting Error ID: {id}"
        ),
        "action_ar": "المحاولة مرة أخرى أو الاتصال بالدعم",
        "action_en": "Retry or contact support",
    },
    # --- Validation (form / input errors) ---
    ErrorCategory.VALIDATION: {
        "title_ar": "بيانات غير صحيحة أو غير مكتملة",
        "title_en": "Invalid or Incomplete Input",
        "body_ar": "الحقل التالي يحتوي على قيمة غير صحيحة أو مفقود: {field}. يرجى تصحيح البيانات والمحاولة مجددًا.",
        "body_en": "The following field is invalid or missing: {field}. Please correct it and try again.",
        "action_ar": "تصحيح الحقل المحدد والمحاولة مجددًا",
        "action_en": "Correct the highlighted field and retry",
    },
    # --- Security / Access ---
    ErrorCategory.SECURITY: {
        "title_ar": "الوصول مرفوض",
        "title_en": "Access Denied",
        "body_ar": ("لا تملك الصلاحيات اللازمة لإجراء هذه العملية. يرجى مراجعة المسؤول إذا كنت تعتقد أن هذا خطأ."),
        "body_en": (
            "You do not have the required permissions for this action. "
            "Contact your administrator if you believe this is an error."
        ),
        "action_ar": "مراجعة المسؤول أو تسجيل الدخول بحساب آخر",
        "action_en": "Review permissions or sign in with a different account",
    },
    # --- Business / Accounting rules ---
    ErrorCategory.BUSINESS: {
        "title_ar": "لا يمكن إكمال العملية بسبب قاعدة محاسبية أو تجارية",
        "title_en": "Operation Cannot Be Completed — Business Rule",
        "body_ar": "{reason}. الإجراء المطلوب: {action}",
        "body_en": "{reason}. Required action: {action}",
        "action_ar": "يرجى مراجعة البيانات المحاسبية أو حالة المستند",
        "action_en": "Review the accounting data or document status",
    },
    # --- State / Workflow (e.g., period closed, document archived) ---
    ErrorCategory.STATE: {
        "title_ar": "حالة المستند أو الفترة لا تسمح بهذه العملية",
        "title_en": "Document or Period State Does Not Allow This Action",
        "body_ar": "{reason}. يرجى {action} قبل المحاولة مجددًا.",
        "body_en": "{reason}. Please {action} before retrying.",
        "action_ar": "حل حالة المستند أو فتح الفترة المناسبة",
        "action_en": "Resolve the document state or open the appropriate period",
    },
}

# ------------------------------------------------------------------
# Custom exception classes (map cleanly to user-facing responses)
# ------------------------------------------------------------------


class ERPError(Exception):
    """Base for all business-facing errors with structured response."""

    def __init__(
        self,
        message_key: str,
        category: str = ErrorCategory.BUSINESS,
        correlation_id: str | None = None,
        extra: dict | None = None,
        status_code: int = 400,
    ):
        self.category = category
        self.correlation_id = correlation_id or generate_correlation_id()
        self.extra = extra or {}
        self.status_code = status_code
        self.message_key = message_key
        super().__init__(self.format_message())

    def format_message(self) -> str:
        registry = MESSAGE_REGISTRY.get(self.category, MESSAGE_REGISTRY[ErrorCategory.SYSTEM])
        template = registry.get("body_ar", "حدث خطأ: {reason}")
        return template.format(
            id=self.correlation_id,
            reason=self.message_key,
            field=self.extra.get("field", "-"),
            action=self.extra.get("action", "-"),
        )

    def to_response(self, lang: str = "ar") -> dict:
        registry = MESSAGE_REGISTRY.get(self.category, MESSAGE_REGISTRY[ErrorCategory.SYSTEM])
        body_key = "body_ar" if lang == "ar" else "body_en"
        action_key = "action_ar" if lang == "ar" else "action_en"
        return {
            "success": False,
            "category": self.category,
            "correlation_id": self.correlation_id,
            "message": registry.get(body_key, registry.get("body_ar", "")).format(
                id=self.correlation_id,
                reason=self.message_key,
                field=self.extra.get("field", "-"),
                action=self.extra.get("action", "-"),
            ),
            "action_hint": registry.get(action_key, "-"),
            "status_code": self.status_code,
        }


# ------------------------------------------------------------------
# Specific business exception shortcuts
# ------------------------------------------------------------------


class UnbalancedLedgerError(ERPError):
    def __init__(self, correlation_id: str | None = None, extra: dict | None = None):
        super().__init__(
            message_key="Balance does not equal debit/credit (entry is unbalanced).",
            category=ErrorCategory.BUSINESS,
            correlation_id=correlation_id,
            extra={**(extra or {}), "action": "تأكد من تطابق الإجمالي مع مجموع المدين والدائن"},
            status_code=400,
        )


class InsufficientStockError(ERPError):
    def __init__(self, correlation_id: str | None = None, extra: dict | None = None):
        super().__init__(
            message_key="Quantity exceeds available stock for the requested item.",
            category=ErrorCategory.BUSINESS,
            correlation_id=correlation_id,
            extra={**(extra or {}), "action": "راجع المخزون المتاح أو خفض الكمية المطلوبة"},
            status_code=409,
        )


class ClosedPeriodError(ERPError):
    def __init__(self, correlation_id: str | None = None, extra: dict | None = None):
        super().__init__(
            message_key="The fiscal or accounting period is closed.",
            category=ErrorCategory.STATE,
            correlation_id=correlation_id,
            extra={**(extra or {}), "action": "افتح الفترة المحاسبية المناسبة أولاً"},
            status_code=403,
        )


class BudgetExceededError(ERPError):
    def __init__(self, correlation_id: str | None = None, extra: dict | None = None):
        super().__init__(
            message_key="The requested amount exceeds the remaining budget.",
            category=ErrorCategory.BUSINESS,
            correlation_id=correlation_id,
            extra={**(extra or {}), "action": "راجع الميزانية المتبقية أو عدِّل المبلغ"},
            status_code=400,
        )


class ArchiveScopeError(ERPError):
    """Branch-scoped restore/archive failure (the production bug found)."""

    def __init__(self, correlation_id: str | None = None, extra: dict | None = None):
        super().__init__(
            message_key="Archive snapshot is missing the branch required for scope.",
            category=ErrorCategory.SYSTEM,
            correlation_id=correlation_id,
            extra={**(extra or {}), "action": "تأكد من وجود branch_id في snapshot (model.to_dict)"},
            status_code=403,
        )


# ------------------------------------------------------------------
# Global safe handler for routes
# ------------------------------------------------------------------


def safe_flash(
    message: str,
    category: str = "danger",
    correlation_id: str | None = None,
    lang: str = "ar",
):
    """Flash a clean, non-technical message; never expose exceptions directly."""
    flash(message, category)


def handle_erp_exception(error: ERPError) -> dict:
    """Convert an ERPError to a clean user-facing dict for APIs/forms."""
    return error.to_response()


# ------------------------------------------------------------------
# Logging wrapper: never leak raw DB errors to user-facing output
# ------------------------------------------------------------------


def log_safe_exception(
    category: str,
    exception: Exception,
    user_context: dict | None = None,
) -> str:
    """Log full technical details securely; return a clean correlation ID."""
    correlation_id = generate_correlation_id()
    logger = logging.getLogger(__name__)
    logger.error(
        "[ERP-%s] Correlation=%s Context=%s Exception=%s",
        category,
        correlation_id,
        user_context or {},
        repr(exception),
        exc_info=True,
    )
    return correlation_id
