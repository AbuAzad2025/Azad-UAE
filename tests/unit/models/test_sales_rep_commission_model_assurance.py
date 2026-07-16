"""SalesRepCommission model — schema, constraints, repr."""
from __future__ import annotations

from decimal import Decimal



class TestSalesRepCommissionModel:
    """SalesRepCommission — columns, FKs, commission representation."""

    def test_required_columns_present(self, db_session):
        from models.sales_rep_commission import SalesRepCommission

        cols = SalesRepCommission.__table__.c
        assert cols.tenant_id.nullable is False
        assert cols.sale_id.nullable is False
        assert cols.sales_rep_id.nullable is False
        assert cols.commission_rate.nullable is False
        assert cols.commission_amount.nullable is False

    def test_optional_sale_line_and_product(self, db_session):
        from models.sales_rep_commission import SalesRepCommission

        assert SalesRepCommission.__table__.c.sale_line_id.nullable is True
        assert SalesRepCommission.__table__.c.product_id.nullable is True

    def test_is_paid_defaults_false(self, db_session):
        from models.sales_rep_commission import SalesRepCommission

        assert SalesRepCommission.__table__.c.is_paid.default.arg is False

    def test_repr_includes_sale_and_rep(self, db_session):
        from models.sales_rep_commission import SalesRepCommission

        row = SalesRepCommission(
            tenant_id=1,
            sale_id=10,
            sales_rep_id=3,
            commission_rate=Decimal('5.00'),
            commission_amount=Decimal('25.500'),
        )
        text = repr(row)
        assert 'S#10' in text
        assert 'rep=3' in text

    def test_commission_rate_precision_metadata(self, db_session):
        from models.sales_rep_commission import SalesRepCommission

        rate_col = SalesRepCommission.__table__.c.commission_rate
        amount_col = SalesRepCommission.__table__.c.commission_amount
        assert str(rate_col.type.precision) == '5'
        assert str(amount_col.type.precision) == '15'

    def test_foreign_keys_to_sale_and_rep(self, db_session):
        from models.sales_rep_commission import SalesRepCommission

        fk_targets = {fk.column.table.name for fk in SalesRepCommission.__table__.foreign_keys}
        assert 'sales' in fk_targets
        assert 'users' in fk_targets
        assert 'tenants' in fk_targets
