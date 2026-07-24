"""Batch 3 — models/utils/smaller services in the 80-94% band."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


class TestPurchaseReturnBaseAmount:
    def test_base_amount_alias(self):
        from models.purchase_return import PurchaseReturn

        pr = PurchaseReturn(
            tenant_id=1,
            return_number="PR-1",
            purchase_id=1,
            supplier_id=1,
            subtotal=Decimal("0"),
            total_amount=Decimal("100"),
            amount_aed=Decimal("100"),
        )
        assert pr.base_amount == Decimal("100")
        pr.base_amount = Decimal("200")
        assert pr.amount_aed == Decimal("200")


class TestFiscalPositionMapping:
    def test_repr_and_map_tax(self, mocker):
        from models.fiscal_position import FiscalPosition, FiscalPositionTaxRule

        fp = FiscalPosition(tenant_id=1, code="export", name="Export")
        assert "export" in repr(fp)

        rule = MagicMock(destination_tax_id=99)
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = rule
        mocker.patch.object(FiscalPositionTaxRule, "query", mock_q)
        assert fp.map_tax(5) == 99

    def test_map_tax_passthrough_without_rule(self, mocker):
        from models.fiscal_position import FiscalPosition, FiscalPositionTaxRule

        fp = FiscalPosition(tenant_id=1, code="local", name="Local")
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = None
        mocker.patch.object(FiscalPositionTaxRule, "query", mock_q)
        assert fp.map_account(12) == 12


class TestHelpdeskModels:
    @pytest.mark.parametrize(
        "cls_name,attrs,token",
        [
            ("TicketCategory", {"name": "Billing"}, "Billing"),
            ("TicketPriority", {"name": "Urgent"}, "Urgent"),
            ("Ticket", {"number": "T-1", "subject": "Help"}, "T-1"),
            ("TicketComment", {"id": 3, "ticket_id": 9}, "T9"),
        ],
    )
    def test_repr(self, cls_name, attrs, token):
        from models import helpdesk as mod

        cls = getattr(mod, cls_name)
        obj = SimpleNamespace(**attrs)
        assert token in repr(cls.__repr__(obj))

    def test_ticket_to_dict(self):
        from models.helpdesk import Ticket

        ticket = Ticket(
            tenant_id=1,
            number="T-42",
            subject="Printer",
            status="open",
            source="portal",
        )
        d = ticket.to_dict()
        assert d["number"] == "T-42"
        assert d["subject"] == "Printer"


class TestModelReprBand:
    @pytest.mark.parametrize(
        "module_path,cls_name,attrs,token",
        [
            (
                "models.archive",
                "ArchivedRecord",
                {"table_name": "sales", "record_id": 9},
                "sales",
            ),
            (
                "models.login_history",
                "LoginHistory",
                {
                    "username": "admin",
                    "login_time": "2026-01-01",
                },
                "admin",
            ),
            ("models.api_key", "APIKey", {"name": "mobile", "service": "pos"}, "pos"),
            (
                "models.partner_transaction",
                "PartnerTransaction",
                {
                    "transaction_type": "dividend",
                    "amount": Decimal("50"),
                    "balance_after": Decimal("100"),
                },
                "dividend",
            ),
            ("models.package", "Package", {"name_ar": "Starter"}, "Starter"),
            (
                "models.payroll_settings",
                "PayrollSettings",
                {"tenant_id": 1},
                "tenant=1",
            ),
        ],
    )
    def test_repr_contains_token(self, module_path, cls_name, attrs, token):
        import importlib

        mod = importlib.import_module(module_path)
        cls = getattr(mod, cls_name)
        obj = SimpleNamespace(**attrs)
        assert token in repr(cls.__repr__(obj))


class TestBankReconciliationModel:
    def test_repr_and_status_ar(self):
        from models.bank_reconciliation import (
            BankReconciliation,
            BankReconciliationItem,
            BankStatementLine,
        )

        br = BankReconciliation(reconciliation_number="BR-001")
        assert "BR-001" in repr(br)
        br.status = "approved"
        assert br.status_ar == "معتمدة"

        item = BankReconciliationItem(description="Deposit")
        assert "Deposit" in repr(item)
        item.item_type = "bank_charge"
        assert item.item_type_ar == "مصروف بنكي"

        line = BankStatementLine(reference="REF-1", amount=100)
        assert "REF-1" in repr(line)

    def test_calculate_reconciliation_balanced(self):
        from decimal import Decimal
        from models.bank_reconciliation import BankReconciliation

        br = BankReconciliation(
            closing_balance_per_books=Decimal("1000"),
            closing_balance_per_bank=Decimal("1000"),
            bank_charges=Decimal("0"),
            bank_interest=Decimal("0"),
            errors_in_books=Decimal("0"),
            outstanding_deposits=Decimal("0"),
            outstanding_withdrawals=Decimal("0"),
            errors_in_bank=Decimal("0"),
        )
        result = br.calculate_reconciliation()
        assert result["is_balanced"] is True
        assert br.is_balanced is True

    def test_approve_raises_when_unbalanced(self):
        from models.bank_reconciliation import BankReconciliation

        br = BankReconciliation(is_balanced=False)
        with pytest.raises(ValueError, match="غير متوازنة"):
            br.approve(user_id=1)

    def test_approve_success(self):
        from models.bank_reconciliation import BankReconciliation

        br = BankReconciliation(is_balanced=True)
        br.approve(user_id=7)
        assert br.status == "approved"
        assert br.approved_by == 7
        assert br.approved_at is not None


class TestCashBoxModel:
    def test_repr_and_full_name(self):
        from decimal import Decimal
        from models.cash_box import CashBox

        box = CashBox(code="C01", name_ar="صندوق", box_type="cash", current_balance=Decimal("500"))
        assert "C01" in repr(box)
        assert box.full_name == "C01 - صندوق"


class TestCRMReprCoverage:
    @pytest.mark.parametrize(
        "cls_name,attrs,token",
        [
            ("CRMStage", {"name": "New"}, "New"),
            ("CRMTeam", {"name": "Sales"}, "Sales"),
            ("CRMLead", {"name": "Lead"}, "Lead"),
            ("CRMActivity", {"activity_type": "call", "lead_id": 4}, "call"),
        ],
    )
    def test_repr(self, cls_name, attrs, token):
        from models import crm as mod

        cls = getattr(mod, cls_name)
        obj = SimpleNamespace(**attrs)
        assert token in repr(cls.__repr__(obj))

    def test_stage_to_dict_english(self):
        from models.crm import CRMStage

        stage = CRMStage(name="Qualified", name_ar="مؤهل")
        data = stage.to_dict(lang="en")
        assert data["name"] == "Qualified"

    def test_to_dict_with_arabic_stage(self):
        from models.crm import CRMLead, CRMStage

        lead = CRMLead(name="Acme", email="a@b.com", phone="050", expected_revenue=1000)
        lead.stage = CRMStage(name="Stage", name_ar="مرحلة")
        data = lead.to_dict(lang="ar")
        assert data["name"] == "Acme"
        assert data["stage_name"] == "مرحلة"

    def test_lead_to_dict_without_stage(self):
        from datetime import datetime, timezone
        from models.crm import CRMLead

        lead = CRMLead(
            name="Solo",
            created_at=datetime(2025, 3, 1, tzinfo=timezone.utc),
        )
        lead.id = 5
        data = lead.to_dict()
        assert data["id"] == 5
        assert data["stage_name"] == ""


class TestEmailMarketingRepr:
    @pytest.mark.parametrize(
        "cls_name,attrs,token",
        [
            ("EmailList", {"name": "Newsletter"}, "Newsletter"),
            ("EmailSubscriber", {"email": "u@test.com"}, "u@test.com"),
            ("EmailTemplate", {"name": "Welcome"}, "Welcome"),
            ("EmailCampaign", {"name": "Summer"}, "Summer"),
            ("CampaignLog", {"campaign_id": 3, "status": "sent"}, "C3"),
        ],
    )
    def test_repr(self, cls_name, attrs, token):
        from models import email_marketing as mod

        cls = getattr(mod, cls_name)
        obj = SimpleNamespace(**attrs)
        assert token in repr(cls.__repr__(obj))


class TestIndustryFieldDefinition:
    def test_repr(self):
        from models.industry_field_definition import IndustryFieldDefinition

        row = IndustryFieldDefinition(industry_code="retail", field_code="size")
        assert "retail.size" in repr(row)


class TestLoginHistoryModel:
    def test_to_dict(self):
        from datetime import datetime, timezone
        from models.login_history import LoginHistory

        row = LoginHistory(
            username="admin",
            login_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
            success=True,
        )
        data = row.to_dict()
        assert data["username"] == "admin"
        assert data["success"] is True


class TestPackageModel:
    def test_package_to_dict(self):
        from models.package import Package

        pkg = Package(name_ar="أساسي", name_en="Basic", slug="basic", price=99.0)
        pkg.id = 1
        data = pkg.to_dict()
        assert data["slug"] == "basic"
        assert data["price"] == 99.0

    def test_package_purchase_repr_and_to_dict(self):
        from models.package import PackagePurchase

        purchase = PackagePurchase(customer_email="buyer@test.com")
        purchase.id = 2
        purchase.package = MagicMock(name_ar="باقة")
        assert "buyer@test.com" in repr(purchase)
        assert purchase.to_dict()["package_name"] == "باقة"


class TestPartnerDistributionAndTransaction:
    def test_distribution_repr_and_status_label(self):
        from datetime import date
        from decimal import Decimal
        from models.partner_profit_distribution import PartnerProfitDistribution

        dist = PartnerProfitDistribution(
            partner_id=1,
            period_start=date(2025, 1, 1),
            period_end=date(2025, 1, 31),
            share_percentage=Decimal("25"),
            net_due=Decimal("1000"),
        )
        assert "P1" in repr(dist)
        dist.status = "paid"
        assert dist.status_label == "مدفوع"

    def test_transaction_labels_and_credit_debit(self):
        from decimal import Decimal
        from models.partner_transaction import PartnerTransaction

        tx = PartnerTransaction(
            transaction_type="withdrawal",
            amount=Decimal("-50"),
            balance_after=Decimal("100"),
        )
        assert tx.transaction_type_label == "مسحوبات"
        assert tx.is_debit is True
        assert tx.is_credit is False
        tx.amount = Decimal("25")
        assert tx.is_credit is True
        assert tx.is_debit is False


class TestPayrollEmployee:
    def test_employee_repr_and_balance(self):
        from models.payroll import Employee

        emp = Employee(name="Sara")
        assert "Sara" in repr(emp)
        assert emp.get_balance() == 0


class TestPosSessionModel:
    def test_close_and_duration(self):
        from datetime import datetime, timedelta, timezone
        from decimal import Decimal
        from models.pos_session import PosSession

        opened = datetime.now(timezone.utc) - timedelta(minutes=30)
        session = PosSession(
            session_number="POS-1",
            opening_balance_cash=Decimal("100"),
            total_cash_sales=Decimal("50"),
            opened_at=opened,
            status=PosSession.STATUS_OPEN,
        )
        session.close(Decimal("150"), notes="shift end")
        assert session.status == "closed"
        assert session.notes == "shift end"
        assert session.duration_minutes >= 29

    def test_duration_naive_datetimes(self):
        from datetime import datetime, timedelta, timezone
        from models.pos_session import PosSession

        opened = datetime.now(timezone.utc) - timedelta(minutes=5)
        session = PosSession(session_number="POS-3", opened_at=opened)
        session.closed_at = datetime.now(timezone.utc)
        assert session.duration_minutes >= 4

        from datetime import datetime, timezone
        from models.pos_session import PosSession

        session = PosSession(session_number="POS-2", opened_at=datetime.now(timezone.utc))
        assert session.duration_minutes >= 0
        assert "POS-2" in repr(session)


class TestProductWarehouseCostModel:
    def test_repr_and_is_empty(self):
        from decimal import Decimal
        from models.product_warehouse_cost import ProductWarehouseCost

        pwc = ProductWarehouseCost(product_id=1, warehouse_id=2, average_cost=Decimal("10"))
        assert "p=1" in repr(pwc)
        pwc.total_quantity = Decimal("0")
        assert pwc.is_empty is True
        pwc.total_quantity = Decimal("5")
        assert pwc.is_empty is False


class TestProfitCenterModel:
    def test_repr_and_full_name(self):
        from models.profit_center import ProfitCenter

        pc = ProfitCenter(code="PC1", name_ar="مركز")
        assert "PC1" in repr(pc)
        assert pc.full_name == "PC1 - مركز"


class TestFiscalPositionTaxRuleRepr:
    def test_repr(self):
        from models.fiscal_position import FiscalPositionTaxRule

        rule = FiscalPositionTaxRule(rule_type="tax_map")
        assert "tax_map" in repr(rule)


class TestWarehouseModels:
    def test_warehouse_repr_and_type_labels(self):
        from datetime import datetime, timezone
        from models.warehouse import Warehouse, ProductWarehouseStock, StockMovement

        wh = Warehouse(name="Main", warehouse_type=Warehouse.TYPE_ONLINE)
        assert "Main" in repr(wh)
        assert wh.is_online is True
        assert wh.type_label_ar() == "أونلاين"
        wh.warehouse_type = Warehouse.TYPE_PHYSICAL
        assert wh.type_label_ar() == "فعلي"

        pws = ProductWarehouseStock(product_id=1, warehouse_id=2, quantity=10)
        assert "P#1" in repr(pws)

        mv = StockMovement(movement_type="sale", quantity=3)
        assert "sale" in repr(mv)
        assert mv.get_type_display("ar") == "بيع"
        mv.product = MagicMock(name="Widget")
        mv.reference_type = "sale"
        mv.reference_id = 9
        mv.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
        d = mv.to_dict()
        assert d["movement_type"] == "sale"
        assert "sale #9" in d["reference"]
