from extensions import db
from typing import Any
from models.cheque import Cheque
from models.gl import GLJournalEntry
from services.cheque_service import (
    process_cheque_receive,
    process_cheque_issue,
    process_cheque_clear,
    process_cheque_bounce,
)
from utils.currency_utils import get_system_default_currency
from utils.gl_reference_types import GLRef
from utils.gl_tenant import (
    scope_journal_entries,
    get_gl_account_by_code,
    active_tenant_id,
)


class ChequeAccountingIntegration:
    """تكامل الشيكات مع النظام المحاسبي"""

    @staticmethod
    def _scoped_entries(cheque, reference_type=None, **filters):
        from utils.gl_reference_types import ref_variants

        q = scope_journal_entries(GLJournalEntry.query, tenant_id=cheque.tenant_id)
        if reference_type is not None:
            q = q.filter(
                GLJournalEntry.reference_type.in_(ref_variants(reference_type))
            )
        for key, val in filters.items():
            q = q.filter_by(**{key: val})
        return q

    @staticmethod
    def receive_cheque(cheque_id, received_by=None):
        """تسجيل استلام شيك وارد"""
        cheque = Cheque.query.get_or_404(cheque_id)
        if cheque.cheque_type != "incoming":
            raise ValueError("هذا الشيك ليس شيك وارد")
        if cheque.status != "pending":
            raise ValueError("الشيك ليس في حالة معلق")
        try:
            entry = process_cheque_receive(cheque)
            db.session.flush()
            return entry
        except Exception as e:
            raise Exception(f"فشل في تسجيل استلام الشيك: {str(e)}")

    @staticmethod
    def issue_cheque(cheque_id, issued_by=None):
        """تسجيل إصدار شيك صادر"""
        cheque = Cheque.query.get_or_404(cheque_id)
        if cheque.cheque_type != "outgoing":
            raise ValueError("هذا الشيك ليس شيك صادر")
        if cheque.status != "pending":
            raise ValueError("الشيك ليس في حالة معلق")
        try:
            process_cheque_issue(cheque)
            db.session.flush()
            entry = (
                ChequeAccountingIntegration._scoped_entries(
                    cheque, reference_type=GLRef.CHEQUE_ISSUE, reference_id=cheque.id
                )
                .order_by(GLJournalEntry.id.desc())
                .first()
            )
            return entry
        except Exception as e:
            raise Exception(f"فشل في تسجيل إصدار الشيك: {str(e)}")

    @staticmethod
    def clear_cheque(cheque_id, cleared_by=None, bank_charges=0, exchange_gain_loss=0):
        """تسجيل صرف شيك"""
        cheque = Cheque.query.get_or_404(cheque_id)
        if cheque.status not in ["pending", "under_collection", "deposited"]:
            raise ValueError("الشيك ليس في حالة يمكن صرفه")
        try:
            exchange_rate = None
            if (
                exchange_gain_loss
                and cheque.currency
                and cheque.currency.upper() != get_system_default_currency().upper()
                and cheque.amount
            ):
                from decimal import Decimal as D

                amt_aed = cheque.amount_aed or D("0")
                target_aed = amt_aed + D(str(exchange_gain_loss))
                exchange_rate = target_aed / cheque.amount
            process_cheque_clear(
                cheque, clearance_date=None, clearance_exchange_rate=exchange_rate
            )
            try:
                db.session.flush()
            except Exception:
                raise

            # إرجاع القيد الأخير المرتبط (Cheque لا يُرجع القيد)
            entry = (
                ChequeAccountingIntegration._scoped_entries(
                    cheque, reference_type=GLRef.CHEQUE_CLEAR, reference_id=cheque.id
                )
                .order_by(GLJournalEntry.id.desc())
                .first()
            )
            if entry is None:
                # القيد قد لا يُنشأ إذا فشل _create_clearing_journal_entry
                class _DummyEntry:
                    entry_number = "—"

                return _DummyEntry()
            return entry
        except Exception as e:
            raise Exception(f"فشل في تسجيل صرف الشيك: {str(e)}")

    @staticmethod
    def bounce_cheque(cheque_id, bounced_by=None, bounce_reason=None):
        """تسجيل ارتداد شيك"""
        cheque = Cheque.query.get_or_404(cheque_id)
        if cheque.status not in ["pending", "under_collection", "deposited"]:
            raise ValueError("الشيك ليس في حالة يمكن ارتداده")
        try:
            process_cheque_bounce(cheque, reason=bounce_reason or "غير محدد")
            db.session.flush()
            # إرجاع القيد المرتبط
            entry = (
                ChequeAccountingIntegration._scoped_entries(
                    cheque, reference_type=GLRef.CHEQUE_BOUNCE, reference_id=cheque.id
                )
                .order_by(GLJournalEntry.id.desc())
                .first()
            )
            return entry
        except Exception as e:
            raise Exception(f"فشل في تسجيل ارتداد الشيك: {str(e)}")

    @staticmethod
    def get_cheque_accounting_summary(cheque_id):
        """الحصول على ملخص محاسبي للشيك"""
        cheque = Cheque.query.get_or_404(cheque_id)

        summary: dict[str, Any] = {
            "cheque_info": {
                "id": cheque.id,
                "number": cheque.cheque_bank_number,
                "type": cheque.cheque_type_ar,
                "amount": float(cheque.amount_aed or 0),
                "status": cheque.status_ar,
                "date": (
                    (cheque.issue_date or cheque.due_date).isoformat()
                    if (cheque.issue_date or cheque.due_date)
                    else None
                ),
            },
            "journal_entries": [],
            "account_impact": [],
        }

        # جمع القيود المحاسبية المرتبطة (بالاستعلام عن reference_type/reference_id)
        ref_types = [
            (GLRef.CHEQUE_RECEIVE, "receive"),
            (GLRef.CHEQUE_ISSUE, "issue"),
            (GLRef.CHEQUE_CLEAR, "clear"),
            (GLRef.CHEQUE_BOUNCE, "bounce"),
        ]
        for ref_type, entry_type in ref_types:
            entries = (
                ChequeAccountingIntegration._scoped_entries(
                    cheque, reference_type=ref_type, reference_id=cheque.id
                )
                .order_by(GLJournalEntry.id.asc())
                .all()
            )
            for entry in entries:
                summary["journal_entries"].append(
                    {
                        "type": entry_type,
                        "entry_number": entry.entry_number,
                        "date": (
                            entry.entry_date.isoformat()
                            if hasattr(entry.entry_date, "isoformat")
                            else str(entry.entry_date)
                        ),
                        "description": entry.description or "",
                    }
                )

        # حساب التأثير على الحسابات
        accounts_affected = set()
        tid = cheque.tenant_id or active_tenant_id()
        for entry_info in summary["journal_entries"]:
            entry_info_dict: dict[str, Any] = entry_info
            entry = scope_journal_entries(
                GLJournalEntry.query.filter_by(
                    entry_number=entry_info_dict["entry_number"]
                ),
                tenant_id=tid,
            ).first()
            if entry:
                for line in entry.lines:
                    accounts_affected.add(line.account.code)

        for account_code in accounts_affected:
            account = get_gl_account_by_code(account_code, tenant_id=tid)
            if account:
                summary["account_impact"].append(
                    {
                        "code": account.code,
                        "name": account.full_name,
                        "balance": float(account.get_balance()),
                    }
                )

        return summary
