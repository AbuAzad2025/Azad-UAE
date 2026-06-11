"""Canonical GL journal reference types — single source of truth."""
from __future__ import annotations


class GLRef:
    SALE = "Sale"
    SALE_COGS = "SaleCOGS"
    SALE_REVERSED = "SaleReversed"
    PURCHASE = "Purchase"
    EXPENSE = "Expense"
    PAYMENT = "Payment"
    RECEIPT = "Receipt"
    PRODUCT_RETURN = "ProductReturn"
    PARTNER_COMMISSION = "PartnerCommission"
    CHEQUE_RECEIVE = "ChequeReceive"
    CHEQUE_ISSUE = "ChequeIssue"
    CHEQUE_CLEAR = "ChequeClear"
    CHEQUE_BOUNCE = "ChequeBounce"
    CHEQUE_CANCEL = "ChequeCancel"
    STOCK_ADJUSTMENT = "StockAdjustment"
    SALARY_ADVANCE = "SalaryAdvance"
    PAYROLL = "Payroll"
    BANK_RECONCILIATION = "BankReconciliation"
    DEPRECIATION = "Depreciation"
    ASSET_DISPOSAL = "AssetDisposal"
    INVENTORY_MIGRATION = "InventoryMigration"
    PRODUCT_CREATION = "ProductCreation"
    PRODUCT_UPDATE = "ProductUpdate"
    STOCK_TRANSFER = "StockTransfer"
    DONATION = "Donation"
    AZAD_PLATFORM_FEE = "AzadPlatformFee"
    AZAD_SUBSCRIPTION_FEE = "AzadSubscriptionFee"


LEGACY_REF_MAP: dict[str, str] = {
    "sale": GLRef.SALE,
    "sale_cogs": GLRef.SALE_COGS,
    "Sale-Reversed": GLRef.SALE_REVERSED,
    "purchase": GLRef.PURCHASE,
    "expense": GLRef.EXPENSE,
    "cheque_receive": GLRef.CHEQUE_RECEIVE,
    "cheque_issue": GLRef.CHEQUE_ISSUE,
    "cheque_clear": GLRef.CHEQUE_CLEAR,
    "cheque_bounce": GLRef.CHEQUE_BOUNCE,
    "cheque_cancel": GLRef.CHEQUE_CANCEL,
    "stock_adjustment": GLRef.STOCK_ADJUSTMENT,
    "salary_advance": GLRef.SALARY_ADVANCE,
    "payroll": GLRef.PAYROLL,
    "bank_reconciliation": GLRef.BANK_RECONCILIATION,
    "depreciation": GLRef.DEPRECIATION,
    "asset_disposal": GLRef.ASSET_DISPOSAL,
    "inventory_migration": GLRef.INVENTORY_MIGRATION,
    "Product Creation": GLRef.PRODUCT_CREATION,
    "Product Update": GLRef.PRODUCT_UPDATE,
    "Cheque": GLRef.CHEQUE_ISSUE,
}


def _build_variants() -> dict[str, list[str]]:
    variants: dict[str, set[str]] = {}
    for canonical in {
        v for v in vars(GLRef).values() if isinstance(v, str) and not v.startswith("_")
    }:
        variants.setdefault(canonical, set()).add(canonical)
    for legacy, canonical in LEGACY_REF_MAP.items():
        variants.setdefault(canonical, set()).add(legacy)
        variants.setdefault(canonical, set()).add(canonical)
    return {k: sorted(v) for k, v in variants.items()}


REF_VARIANTS = _build_variants()


def normalize_ref_type(value: str | None) -> str | None:
    if not value:
        return value
    return LEGACY_REF_MAP.get(value, value)


def ref_variants(canonical_or_legacy: str) -> list[str]:
    canonical = normalize_ref_type(canonical_or_legacy) or canonical_or_legacy
    return REF_VARIANTS.get(canonical, [canonical])


def filter_entries_by_ref(query, canonical_or_legacy: str):
    from models import GLJournalEntry

    variants = ref_variants(canonical_or_legacy)
    return query.filter(GLJournalEntry.reference_type.in_(variants))


def delete_entries_by_ref(reference_id, *canonical_types):
    from extensions import db
    from models import GLJournalEntry

    types: list[str] = []
    for t in canonical_types:
        types.extend(ref_variants(t))
    if not types:
        return 0
    return GLJournalEntry.query.filter(
        GLJournalEntry.reference_id == reference_id,
        GLJournalEntry.reference_type.in_(types),
    ).delete(synchronize_session=False)
