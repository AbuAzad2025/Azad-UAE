"""Coverage boost for services/fiscal_position_service.py.

Targets: get_for_customer address_country + no-local-None + explicit-missing,
apply_to_sale pos-None / unchanged-mapping / missing-attrs, compute_tax
customer-routed tenant_scope / rule-without-destination / no-source-tax /
unit defaults. Real service calls; DB rows are real, fixtures real.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock


class TestGetForCustomerReal:
    def test_address_country_match(self, db_session, sample_tenant, sample_customer):
        from models import FiscalPosition
        from services.fiscal_position_service import FiscalPositionService

        pos = FiscalPosition(
            tenant_id=sample_tenant.id,
            code="gcc-c3",
            name="GCC",
            name_ar="خليجي",
            country_code="SA",
            auto_apply=True,
            is_active=True,
        )
        db_session.add(pos)
        db_session.flush()
        sample_customer.country = None
        sample_customer.address_country = "SA"
        db_session.flush()
        db_session.commit()
        assert FiscalPositionService.get_for_customer(sample_customer.id) is not None

    def test_no_local_returns_none(self, db_session, sample_tenant):
        from services.customer_service import CustomerService
        from services.fiscal_position_service import FiscalPositionService

        c = CustomerService.create_customer(name="NoFP", tenant_id=sample_tenant.id)
        db_session.flush()
        db_session.commit()
        # ensure no country and no local code row
        from models import FiscalPosition

        FiscalPosition.query.filter_by(tenant_id=sample_tenant.id, code="local").delete()
        db_session.flush()
        db_session.commit()
        assert FiscalPositionService.get_for_customer(c.id) is None

    def test_explicit_valid_position_returns_it(self, db_session, sample_tenant, sample_customer):
        from models import FiscalPosition
        from services.fiscal_position_service import FiscalPositionService

        pos = FiscalPosition(
            tenant_id=sample_tenant.id,
            code="explicit-c3",
            name="Explicit",
            name_ar="صريح",
            auto_apply=False,
            is_active=True,
        )
        db_session.add(pos)
        db_session.flush()
        sample_customer.fiscal_position_id = pos.id
        db_session.flush()
        db_session.commit()
        assert FiscalPositionService.get_for_customer(sample_customer.id).id == pos.id


class TestApplyToSaleBranches:
    def test_pos_none_returns_sale_unchanged(self, mocker):
        from services.fiscal_position_service import FiscalPositionService

        sale = MagicMock(customer_id=5, lines=[])
        mocker.patch.object(FiscalPositionService, "get_for_customer", return_value=None)
        assert FiscalPositionService.apply_to_sale(sale, customer_id=5) is sale

    def test_unchanged_mapping_and_missing_attrs(self, mocker):
        from services.fiscal_position_service import FiscalPositionService

        line_same = SimpleNamespace(tax_id=10, income_account_id=200)
        line_plain = SimpleNamespace()
        sale = SimpleNamespace(customer_id=1, lines=[line_same, line_plain])
        pos = SimpleNamespace(map_tax=lambda tid: tid, map_account=lambda aid: aid)
        mocker.patch.object(FiscalPositionService, "get_for_customer", return_value=pos)
        out = FiscalPositionService.apply_to_sale(sale, customer_id=1)
        assert out.lines[0].tax_id == 10
        assert out.lines[0].income_account_id == 200

    def test_explicit_customer_id_used(self, mocker):
        from services.fiscal_position_service import FiscalPositionService

        sale = SimpleNamespace(customer_id=None, lines=[])
        seen = {}
        orig = FiscalPositionService.get_for_customer

        def _spy(cid):
            seen["cid"] = cid
            return None

        mocker.patch.object(FiscalPositionService, "get_for_customer", side_effect=_spy)
        FiscalPositionService.apply_to_sale(sale, customer_id=42)
        assert seen["cid"] == 42
        assert orig is not None


class TestComputeTaxBranches:
    def test_customer_routed_with_tenant_scope(self, db_session, sample_tenant, sample_customer):
        from models import FiscalPosition
        from services.fiscal_position_service import FiscalPositionService

        pos = FiscalPosition(
            tenant_id=sample_tenant.id, code="local-c3", name="Local", name_ar="محلي", auto_apply=False, is_active=True
        )
        db_session.add(pos)
        db_session.flush()
        sample_customer.fiscal_position_id = pos.id
        db_session.flush()
        db_session.commit()
        # No tax rule rows and no such source tax: routing via the customer
        # still resolves the position (tenant_scope filter) and yields 0 rate.
        line = SimpleNamespace(tax_id=99999999, unit_price=Decimal("100"), quantity=2)
        amount, rate = FiscalPositionService.compute_tax_for_line(
            line, fiscal_position_id=None, customer_id=sample_customer.id
        )
        assert rate == Decimal("0")
        assert amount == Decimal("0.000")

    def test_rule_without_destination_falls_back(self, mocker):
        from services.fiscal_position_service import FiscalPositionService

        line = SimpleNamespace(tax_id=9, unit_price=100, quantity=1)
        rule = SimpleNamespace(destination_tax=None)
        mocker.patch(
            "services.fiscal_position_service.FiscalPositionTaxRule.query"
        ).filter_by.return_value.first.return_value = rule
        mocker.patch("services.fiscal_position_service.db.session.get", return_value=SimpleNamespace(rate=7))
        _, rate = FiscalPositionService.compute_tax_for_line(line, fiscal_position_id=3)
        assert rate == Decimal("7")

    def test_no_source_tax_rate_zero_and_defaults(self, mocker):
        from services.fiscal_position_service import FiscalPositionService

        line = SimpleNamespace(tax_id=None, unit_price=None, quantity=None)
        amount, rate = FiscalPositionService.compute_tax_for_line(line)
        assert rate == Decimal("0")
        assert amount == Decimal("0.000")
