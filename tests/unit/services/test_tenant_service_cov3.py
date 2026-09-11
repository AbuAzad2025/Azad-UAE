"""Coverage boost for services/tenant_service.py — TenantService.get_tenants_list_context.

Targets the sort/search/count branches (lines 18-89) with query chains mocked
only at the DB boundary; the real get_tenants_list_context runs unmodified.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.tenant_service import TenantService


def _query_mock(*, all_result=None):
    q = MagicMock()
    q.filter.return_value = q
    q.order_by.return_value = q
    q.all.return_value = all_result if all_result is not None else []
    return q


def _count_mock(pairs):
    q = MagicMock()
    q.filter.return_value = q
    q.group_by.return_value = q
    q.all.return_value = list(pairs)
    return q


def _run(tenant_query_mock, count_pairs=(None, None, None)):
    session = MagicMock()
    user_q, branch_q, store_q = count_pairs
    session.query.side_effect = [
        user_q or _count_mock([]),
        branch_q or _count_mock([]),
        store_q or _count_mock([]),
    ]
    with (
        patch("services.tenant_service.Tenant.query", new=tenant_query_mock),
        patch("services.tenant_service.db.session", new=session),
    ):
        return TenantService.get_tenants_list_context()


class TestDefaultSortEmpty:
    def test_default_sort_no_tenants_returns_empty_counts(self):
        q = _query_mock(all_result=[])
        with (
            patch("services.tenant_service.Tenant.query", new=q),
            patch("services.tenant_service.db") as mock_db,
        ):
            mock_db.session.query.side_effect = [_count_mock([]), _count_mock([]), _count_mock([])]
            out = TenantService.get_tenants_list_context()
        assert out == {"tenants": [], "user_counts": {}, "branch_counts": {}, "store_counts": {}}
        q.order_by.assert_called_once()

    def test_each_sort_key_desc(self):
        for sort in ("name", "slug", "plan", "status", "created_at"):
            q = _query_mock(all_result=[])
            with (
                patch("services.tenant_service.Tenant.query", new=q),
                patch("services.tenant_service.db") as mock_db,
            ):
                mock_db.session.query.side_effect = [_count_mock([]), _count_mock([]), _count_mock([])]
                out = TenantService.get_tenants_list_context(sort=sort)
            assert out["tenants"] == []

    def test_unknown_sort_falls_back_to_created_at(self):
        q = _query_mock(all_result=[])
        with (
            patch("services.tenant_service.Tenant.query", new=q),
            patch("services.tenant_service.db") as mock_db,
        ):
            mock_db.session.query.side_effect = [_count_mock([]), _count_mock([]), _count_mock([])]
            out = TenantService.get_tenants_list_context(sort="nope")
        assert out["tenants"] == []


class TestAscOrdering:
    def test_asc_maps_ordering_columns(self):
        q = _query_mock(all_result=[])
        with (
            patch("services.tenant_service.Tenant.query", new=q),
            patch("services.tenant_service.db") as mock_db,
        ):
            mock_db.session.query.side_effect = [_count_mock([]), _count_mock([]), _count_mock([])]
            TenantService.get_tenants_list_context(sort="name", order="asc")
        q.order_by.assert_called_once()

    def test_asc_with_unascable_column_keeps_original(self):
        bad_col = MagicMock()
        bad_col.asc.side_effect = Exception("no asc")
        bad_col.modifier = None
        # hasattr(bad_col, "modifier") is True for MagicMock; use a stub without the attr
        del bad_col.modifier
        good_col = MagicMock()
        good_col.asc.side_effect = Exception("no asc")
        del good_col.modifier
        with patch.dict(
            "services.tenant_service._SORT_MAP",
            {"created_at": lambda: [bad_col, good_col]},
        ):
            q = _query_mock(all_result=[])
            with (
                patch("services.tenant_service.Tenant.query", new=q),
                patch("services.tenant_service.db") as mock_db,
            ):
                mock_db.session.query.side_effect = [_count_mock([]), _count_mock([]), _count_mock([])]
                out = TenantService.get_tenants_list_context(sort="created_at", order="ASC")
        assert out["tenants"] == []
        ordered_args = q.order_by.call_args.args
        assert list(ordered_args) == [bad_col, good_col]

    def test_asc_keeps_modifier_columns_as_is(self):
        mod_col = SimpleNamespace(modifier="desc")
        with patch.dict(
            "services.tenant_service._SORT_MAP",
            {"created_at": lambda: [mod_col]},
        ):
            q = _query_mock(all_result=[])
            with (
                patch("services.tenant_service.Tenant.query", new=q),
                patch("services.tenant_service.db") as mock_db,
            ):
                mock_db.session.query.side_effect = [_count_mock([]), _count_mock([]), _count_mock([])]
                TenantService.get_tenants_list_context(sort="created_at", order="asc")
        q.order_by.assert_called_once_with(mod_col)


class TestSearch:
    def test_search_applies_like_filter(self):
        q = _query_mock(all_result=[])
        with (
            patch("services.tenant_service.Tenant.query", new=q),
            patch("services.tenant_service.db") as mock_db,
        ):
            mock_db.session.query.side_effect = [_count_mock([]), _count_mock([]), _count_mock([])]
            out = TenantService.get_tenants_list_context(search="Acme")
        assert out["tenants"] == []
        assert q.filter.call_count >= 1

    def test_search_fallback_numeric_uses_id_match(self):
        base = MagicMock()
        fallback = _query_mock(all_result=[])
        base.filter.side_effect = [Exception("no name col"), fallback]
        base.order_by.return_value = fallback
        with (
            patch("services.tenant_service.Tenant.query", new=base),
            patch("services.tenant_service.db") as mock_db,
        ):
            mock_db.session.query.side_effect = [_count_mock([]), _count_mock([]), _count_mock([])]
            out = TenantService.get_tenants_list_context(search="42")
        assert out["tenants"] == []

    def test_search_fallback_non_numeric_uses_minus_one(self):
        base = MagicMock()
        fallback = _query_mock(all_result=[])
        base.filter.side_effect = [Exception("no name col"), fallback]
        base.order_by.return_value = fallback
        with (
            patch("services.tenant_service.Tenant.query", new=base),
            patch("services.tenant_service.db") as mock_db,
        ):
            mock_db.session.query.side_effect = [_count_mock([]), _count_mock([]), _count_mock([])]
            out = TenantService.get_tenants_list_context(search="xyz")
        assert out["tenants"] == []


class TestCounts:
    def test_counts_mapped_per_tenant(self):
        tenants = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
        q = _query_mock(all_result=tenants)
        with (
            patch("services.tenant_service.Tenant.query", new=q),
            patch("services.tenant_service.db") as mock_db,
        ):
            mock_db.session.query.side_effect = [
                _count_mock([(1, 3)]),
                _count_mock([(1, 2), (2, 1)]),
                _count_mock([(2, 5)]),
            ]
            out = TenantService.get_tenants_list_context()
        assert out["tenants"] == tenants
        assert out["user_counts"] == {1: 3}
        assert out["branch_counts"] == {1: 2, 2: 1}
        assert out["store_counts"] == {2: 5}
