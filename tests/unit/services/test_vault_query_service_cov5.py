"""Cov5: vault_query_service — unfiltered list, 404 lookup, bad sort arcs."""

from __future__ import annotations

import pytest
from werkzeug.exceptions import NotFound


def test_list_platform_records_unfiltered(sample_tenant):
    from services.vault_query_service import VaultQueryService

    assert VaultQueryService.list_platform_records(sample_tenant.id) == []


def test_get_any_donation_missing_raises():
    from services.vault_query_service import VaultQueryService

    with pytest.raises(NotFound):
        VaultQueryService.get_any_donation_or_404(999999999)


def test_purchases_paginated_bad_sort():
    from services.vault_query_service import VaultQueryService

    out = VaultQueryService.purchases_paginated_v2(1, 10, sort_by="nope")
    assert out.total == 0
