"""Owner database console — table browser / editor rendering and tenant isolation.

These two routes are the only templates in the repository with no render
coverage, and they are also the surface the platform plane uses to read raw
tables. Both properties are asserted here at once: the templates really render
for a platform-only table, and a tenant-scoped table is refused.

Why ``packages`` specifically: it is a platform table with no ``tenant_id``
column and no credential column, so it is one of the handful that survive the
schema-derived block set in routes/owner/shared.py. ``audit_logs`` would not -
it carries a ``tenant_id``.
"""

from __future__ import annotations

import pytest

# Platform-only table: no tenant_id, no credential columns.
PLATFORM_TABLE = "packages"

# Tenant-owned tables, in the two shapes the block set has to catch.
TENANT_TABLES = [
    "sales",  # has its own tenant_id
    "gl_journal_lines",  # plural name; the old hand-written denylist held "gl_journal_entry"
    "shipment_lines",  # no tenant_id of its own - tenant-owned via shipment_id
    "shop_customer_accounts",  # carries password_hash
    "card_payments",
    "employees",
    "pos_sessions",
    "purchase_orders",
]


class TestOwnerTableBrowserRenders:
    """The browser and editor must actually render, not redirect."""

    def test_browse_table_renders(self, owner_client):
        resp = owner_client.get(f"/owner/browse-table/{PLATFORM_TABLE}")
        assert resp.status_code == 200, f"browse-table returned {resp.status_code}"

    def test_edit_table_renders(self, owner_client):
        resp = owner_client.get(f"/owner/edit-table-data/{PLATFORM_TABLE}")
        assert resp.status_code == 200, f"edit-table-data returned {resp.status_code}"


class TestOwnerTableBrowserRefusesTenantData:
    """Tenant business data must stay unreachable from the platform plane.

    Every one of these redirects to the database-tools page, which is how a
    refusal is signalled in this blueprint. The list is deliberately the exact
    set that the old singular-name denylist let through.
    """

    @pytest.mark.parametrize("table", TENANT_TABLES)
    def test_browse_refuses_tenant_table(self, owner_client, table):
        resp = owner_client.get(f"/owner/browse-table/{table}")
        assert resp.status_code == 302, f"browse-table exposed {table} (status {resp.status_code})"

    @pytest.mark.parametrize("table", TENANT_TABLES)
    def test_edit_refuses_tenant_table(self, owner_client, table):
        resp = owner_client.get(f"/owner/edit-table-data/{table}")
        assert resp.status_code == 302, f"edit-table-data exposed {table} (status {resp.status_code})"
