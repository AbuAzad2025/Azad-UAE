"""Commission GL service — partner commission posting."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock


class TestPostSaleCommissions:
    def test_returns_none_when_no_entries(self, mocker):
        mocker.patch(
            "services.commission_gl_service.PartnerCommissionEntry",
        ).query.filter_by.return_value.all.return_value = []
        from services.commission_gl_service import post_sale_commissions

        sale = MagicMock(id=1, tenant_id=1)
        assert post_sale_commissions(sale) is None

    def test_returns_none_when_total_non_positive(self, mocker):
        entry = MagicMock(commission_amount_aed=Decimal("0"))
        PartnerCommissionEntry = mocker.patch(
            "services.commission_gl_service.PartnerCommissionEntry"
        )
        PartnerCommissionEntry.query.filter_by.return_value.all.return_value = [entry]
        from services.commission_gl_service import post_sale_commissions

        sale = MagicMock(id=1, tenant_id=1, exchange_rate=Decimal("1"), currency="AED")
        assert post_sale_commissions(sale) is None

    def test_posts_commission_with_currency_fallback(self, mocker):
        entry = MagicMock(commission_amount_aed=Decimal("50"))
        PartnerCommissionEntry = mocker.patch(
            "services.commission_gl_service.PartnerCommissionEntry"
        )
        PartnerCommissionEntry.query.filter_by.return_value.all.return_value = [entry]
        mocker.patch(
            "utils.currency_utils.resolve_tenant_base_currency",
            side_effect=RuntimeError("no currency"),
        )
        ensure = mocker.patch(
            "services.commission_gl_service.GLService.ensure_core_accounts"
        )
        post = mocker.patch(
            "services.commission_gl_service.post_or_fail", return_value=MagicMock(id=9)
        )
        from services.commission_gl_service import post_sale_commissions

        sale = MagicMock(
            id=3,
            tenant_id=1,
            sale_number="S-100",
            exchange_rate=None,
            currency="USD",
            branch_id=2,
        )
        result = post_sale_commissions(sale)
        assert result.id == 9
        ensure.assert_called_once_with(tenant_id=1)
        post.assert_called_once()
