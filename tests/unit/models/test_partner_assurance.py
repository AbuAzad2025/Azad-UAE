"""Partner model — scope labels and balance summary."""

from __future__ import annotations

import pytest


def _partner_stub(**kwargs):
    """Minimal instance carrying Partner method/property descriptors."""
    from models.partner import Partner

    class Stub:
        investment_amount = kwargs.get("investment_amount", 10000)
        total_additional_investment = kwargs.get("total_additional_investment", 2000)
        total_withdrawals = kwargs.get("total_withdrawals", 1500)
        current_balance = kwargs.get("current_balance", 500)
        total_profit_received = kwargs.get("total_profit_received", 3000)
        total_loss_borne = kwargs.get("total_loss_borne", 200)
        scope_type = kwargs.get("scope_type", "company")
        scope_id = kwargs.get("scope_id", None)
        partner_type = kwargs.get("partner_type", "investor")
        share_percentage = kwargs.get("share_percentage", 25)
        name = kwargs.get("name", "Test Partner")

        scope_label = Partner.scope_label
        partner_type_label = Partner.partner_type_label
        net_investment = Partner.net_investment
        get_balance_summary = Partner.get_balance_summary

    return Stub()


class TestPartnerProperties:
    def test_scope_label_company(self):
        assert _partner_stub(scope_type="company").scope_label == "مستوى الشركة"

    def test_scope_label_branch(self):
        assert _partner_stub(scope_type="branch", scope_id=3).scope_label == "فرع #3"

    def test_scope_label_warehouse(self):
        assert (
            _partner_stub(scope_type="warehouse", scope_id=8).scope_label == "مستودع #8"
        )

    def test_scope_label_unknown(self):
        assert _partner_stub(scope_type="other").scope_label == "—"

    @pytest.mark.parametrize(
        "ptype,label",
        [
            ("investor", "شريك استثماري"),
            ("working_partner", "شريك عامل"),
            ("silent_partner", "شريك صامت"),
            ("branch_partner", "شريك فرع"),
            ("warehouse_partner", "شريك مستودع"),
            ("custom_type", "custom_type"),
        ],
    )
    def test_partner_type_label(self, ptype, label):
        assert _partner_stub(partner_type=ptype).partner_type_label == label

    def test_net_investment(self):
        p = _partner_stub(
            investment_amount=10000,
            total_additional_investment=2000,
            total_withdrawals=1500,
        )
        assert p.net_investment == 10500.0

    def test_get_balance_summary(self):
        p = _partner_stub()
        summary = p.get_balance_summary()
        assert summary["investment"] == 10000.0
        assert summary["current_balance"] == 500.0
        assert summary["net_investment"] == p.net_investment

    def test_repr(self):
        from models.partner import Partner

        p = Partner()
        p.name = "Ahmed"
        p.share_percentage = 25
        assert repr(p) == "<Partner Ahmed (25%)>"
