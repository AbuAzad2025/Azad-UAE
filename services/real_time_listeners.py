from datetime import datetime, timezone
from extensions import db
from sqlalchemy import event
from models.gl import GLJournalEntry, GLJournalLine, GLAccount
from models.advanced_accounting import AdvancedExpense
from models.cheque import Cheque
import json


class RealTimeAccountingListeners:
    """مستمعات لحظية للأحداث المحاسبية"""

    _listeners_registered = False

    @staticmethod
    def setup_listeners():
        """إعداد جميع المستمعات (idempotent — safe if called more than once)."""
        if RealTimeAccountingListeners._listeners_registered:
            return
        RealTimeAccountingListeners._listeners_registered = True

        # مستمع إنشاء القيود
        @event.listens_for(GLJournalEntry, "after_insert")
        def journal_entry_created(mapper, connection, target):
            RealTimeAccountingListeners._on_journal_entry_created(target)

        # مستمع تحديث القيود
        @event.listens_for(GLJournalEntry, "after_update")
        def journal_entry_updated(mapper, connection, target):
            RealTimeAccountingListeners._on_journal_entry_updated(target)

        # مستمع إنشاء سطور القيود
        @event.listens_for(GLJournalLine, "after_insert")
        def journal_line_created(mapper, connection, target):
            RealTimeAccountingListeners._on_journal_line_created(target)

        # مستمع تحديث الأرصدة
        @event.listens_for(GLAccount, "after_update")
        def account_updated(mapper, connection, target):
            RealTimeAccountingListeners._on_account_updated(target)

        # مستمع المصروفات المتقدمة
        @event.listens_for(AdvancedExpense, "after_insert")
        def expense_created(mapper, connection, target):
            RealTimeAccountingListeners._on_expense_created(target)

        # مستمع الشيكات
        @event.listens_for(Cheque, "after_update")
        def cheque_updated(mapper, connection, target):
            RealTimeAccountingListeners._on_cheque_updated(target)

    @staticmethod
    def _on_journal_entry_created(entry):
        """عند إنشاء قيد جديد"""
        try:
            # تسجيل الحدث
            RealTimeAccountingListeners._log_event(
                "journal_entry_created",
                {
                    "entry_id": entry.id,
                    "entry_number": entry.entry_number,
                    "description": entry.description,
                    "amount": float(entry.total_debit),
                    "type": entry.entry_type,
                    "date": entry.entry_date.isoformat() if entry.entry_date else None,
                },
            )

            # إشعار فوري
            RealTimeAccountingListeners._send_notification(
                "قيد جديد", f"تم إنشاء قيد جديد رقم {entry.entry_number}", "success"
            )

            # تحديث الإحصائيات
            RealTimeAccountingListeners._update_statistics()

        except Exception as e:
            print(f"خطأ في مستمع إنشاء القيد: {e}")

    @staticmethod
    def _on_journal_entry_updated(entry):
        """عند تحديث قيد"""
        try:
            # تسجيل الحدث
            RealTimeAccountingListeners._log_event(
                "journal_entry_updated",
                {
                    "entry_id": entry.id,
                    "entry_number": entry.entry_number,
                    "is_posted": entry.is_posted,
                    "is_reversed": entry.is_reversed,
                    "updated_at": (
                        entry.updated_at.isoformat() if entry.updated_at else None
                    ),
                },
            )

            # إشعار حسب نوع التحديث
            if entry.is_posted:
                RealTimeAccountingListeners._send_notification(
                    "قيد مرحل", f"تم ترحيل القيد رقم {entry.entry_number}", "info"
                )
            elif entry.is_reversed:
                RealTimeAccountingListeners._send_notification(
                    "قيد معكوس", f"تم عكس القيد رقم {entry.entry_number}", "warning"
                )

        except Exception as e:
            print(f"خطأ في مستمع تحديث القيد: {e}")

    @staticmethod
    def _on_journal_line_created(line):
        """عند إنشاء سطر قيد"""
        try:
            # Safely access account
            account_code = "Unknown"
            account_name = "Unknown"

            if line.account:
                account_code = line.account.code
                account_name = line.account.full_name
            elif line.account_id:
                # Try to load if relationship is missing but ID exists
                account_code = str(line.account_id)

            # تسجيل الحدث
            RealTimeAccountingListeners._log_event(
                "journal_line_created",
                {
                    "line_id": line.id,
                    "entry_id": line.entry_id,
                    "account_code": account_code,
                    "account_name": account_name,
                    "debit": float(line.debit or 0),
                    "credit": float(line.credit or 0),
                    "description": line.description or "",
                },
            )

            # تحديث رصيد الحساب فورياً
            if line.account_id:
                RealTimeAccountingListeners._update_account_balance(line.account_id)

        except Exception as e:
            print(f"خطأ في مستمع إنشاء سطر القيد: {e}")

    @staticmethod
    def _on_account_updated(account):
        """عند تحديث حساب"""
        try:
            # تسجيل الحدث
            RealTimeAccountingListeners._log_event(
                "account_updated",
                {
                    "account_id": account.id,
                    "account_code": account.code,
                    "account_name": account.full_name,
                    "balance": float(account.get_balance()),
                    "updated_at": (
                        account.updated_at.isoformat() if account.updated_at else None
                    ),
                },
            )

            # فحص الأرصدة العالية
            balance = account.get_balance()
            if abs(balance) > 100000:  # أكثر من 100,000 درهم
                RealTimeAccountingListeners._send_notification(
                    "رصيد عالي",
                    f"رصيد حساب {account.full_name} عالي: {balance:,.2f} درهم",
                    "warning",
                )

        except Exception as e:
            print(f"خطأ في مستمع تحديث الحساب: {e}")

    @staticmethod
    def _on_expense_created(expense):
        """عند إنشاء مصروف متقدم"""
        try:
            # تسجيل الحدث
            RealTimeAccountingListeners._log_event(
                "expense_created",
                {
                    "expense_id": expense.id,
                    "expense_number": expense.expense_number,
                    "description": expense.description_ar,
                    "amount": float(expense.amount_aed),
                    "category": expense.category.name_ar,
                    "tax_amount": float(expense.tax_amount),
                    "customs_amount": float(expense.customs_amount),
                },
            )

            # إشعار فوري
            RealTimeAccountingListeners._send_notification(
                "مصروف جديد",
                f"تم إنشاء مصروف جديد رقم {expense.expense_number} بقيمة {expense.amount_aed:,.2f} درهم",
                "info",
            )

            # فحص حدود الموافقة
            if (
                expense.requires_approval
                and expense.amount_aed > expense.category.approval_limit
            ):
                RealTimeAccountingListeners._send_notification(
                    "موافقة مطلوبة",
                    f"مصروف رقم {expense.expense_number} يحتاج موافقة (يتجاوز الحد المسموح)",
                    "warning",
                )

        except Exception as e:
            print(f"خطأ في مستمع إنشاء المصروف: {e}")

    @staticmethod
    def _on_cheque_updated(cheque):
        """عند تحديث شيك"""
        try:
            # تسجيل الحدث
            RealTimeAccountingListeners._log_event(
                "cheque_updated",
                {
                    "cheque_id": cheque.id,
                    "cheque_number": cheque.cheque_bank_number,
                    "status": cheque.status,
                    "amount": float(cheque.amount_aed),
                    "type": cheque.cheque_type,
                    "updated_at": (
                        cheque.updated_at.isoformat() if cheque.updated_at else None
                    ),
                },
            )

            # إشعار حسب الحالة
            status_messages = {
                "received": "تم استلام شيك وارد",
                "issued": "تم إصدار شيك صادر",
                "cleared": "تم صرف شيك",
                "bounced": "شيك مرتد",
            }

            if cheque.status in status_messages:
                RealTimeAccountingListeners._send_notification(
                    status_messages[cheque.status],
                    f"شيك رقم {cheque.cheque_bank_number} - {cheque.status_ar}",
                    (
                        "success"
                        if cheque.status == "cleared"
                        else "warning"
                        if cheque.status == "bounced"
                        else "info"
                    ),
                )

        except Exception as e:
            print(f"خطأ في مستمع تحديث الشيك: {e}")

    @staticmethod
    def _log_event(event_type, data):
        """تسجيل الحدث"""
        try:
            # يمكن حفظ الأحداث في قاعدة بيانات أو ملف
            # طباعة للاختبار (يمكن استبدالها بحفظ في قاعدة البيانات)
            print(
                f"🔔 حدث محاسبي: {event_type} - {json.dumps(data, ensure_ascii=False)}"
            )

        except Exception as e:
            print(f"خطأ في تسجيل الحدث: {e}")

    @staticmethod
    def _send_notification(title, message, level="info"):
        """إرسال إشعار فوري"""
        try:
            # يمكن ربط هذا بنظام إشعارات حقيقي
            icons = {"success": "✅", "info": "ℹ️", "warning": "⚠️", "error": "❌"}

            icon = icons.get(level, "ℹ️")
            print(f"{icon} {title}: {message}")

        except Exception as e:
            print(f"خطأ في إرسال الإشعار: {e}")

    @staticmethod
    def _update_statistics():
        """تحديث الإحصائيات"""
        try:
            # حساب إحصائيات سريعة
            total_entries = GLJournalEntry.query.count()
            posted_entries = GLJournalEntry.query.filter_by(is_posted=True).count()
            reversed_entries = GLJournalEntry.query.filter_by(is_reversed=True).count()

            stats = {
                "total_entries": total_entries,
                "posted_entries": posted_entries,
                "reversed_entries": reversed_entries,
                "pending_entries": total_entries - posted_entries,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

            print(f"📊 إحصائيات محدثة: {json.dumps(stats, ensure_ascii=False)}")

        except Exception as e:
            print(f"خطأ في تحديث الإحصائيات: {e}")

    @staticmethod
    def _update_account_balance(account_id):
        """تحديث رصيد الحساب فورياً"""
        try:
            account = db.session.get(GLAccount, account_id)
            if account:
                # حساب الرصيد الجديد
                new_balance = account.get_balance()

                # تسجيل التحديث
                RealTimeAccountingListeners._log_event(
                    "account_balance_updated",
                    {
                        "account_id": account_id,
                        "account_code": account.code,
                        "new_balance": float(new_balance),
                    },
                )

        except Exception as e:
            print(f"خطأ في تحديث رصيد الحساب: {e}")


class AccountingEventStream:
    """تيار الأحداث المحاسبية"""

    def __init__(self):
        self.listeners = []
        self.events = []

    def add_listener(self, callback):
        """إضافة مستمع للأحداث"""
        self.listeners.append(callback)

    def emit_event(self, event_type, data):
        """إرسال حدث لجميع المستمعين"""
        event = {
            "id": len(self.events) + 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "data": data,
        }

        self.events.append(event)

        # إرسال لجميع المستمعين
        for listener in self.listeners:
            try:
                listener(event)
            except Exception as e:
                print(f"خطأ في المستمع: {e}")

    def get_recent_events(self, limit=50):
        """الحصول على الأحداث الأخيرة"""
        return self.events[-limit:] if self.events else []

    def get_events_by_type(self, event_type):
        """الحصول على الأحداث حسب النوع"""
        return [event for event in self.events if event["type"] == event_type]


# إنشاء تيار الأحداث العام
accounting_event_stream = AccountingEventStream()

# إعداد المستمعات
RealTimeAccountingListeners.setup_listeners()
