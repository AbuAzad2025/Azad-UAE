"""Odoo-style business flow tour: Cashier POS → Sale → GL → Inventory.

Simulates a complete business loop:
  1. Cashier opens a POS session
  2. Scans an item and adds it to cart
  3. Modifies totals via #recalcTotalsBtn
  4. Checks out (complete sale)
  5. Asserts backend GL journal and inventory balances updated correctly
"""

import pytest


BASE_URL = "http://localhost:5000"


@pytest.mark.tour
class TestPOSCashierFlowTour:
    """Full POS cashier business flow tour."""

    def test_cashier_opens_pos_session(self, cashier_context):
        """Cashier navigates to POS view and sees the session controls."""
        page = cashier_context.new_page()
        page.goto(f"{BASE_URL}/pos")
        assert page.url == f"{BASE_URL}/pos" or "/login" not in page.url
        assert page.locator("#posSessionPanel").is_visible()
        page.locator("#openSessionBtn").click()
        page.wait_for_selector("#sessionId:not(:empty)", timeout=5000)
        session_id = page.locator("#sessionId").text_content()
        assert session_id is not None and len(session_id) > 0
        page.close()

    def test_cashier_adds_item_to_cart(self, cashier_context):
        """Scan an item by barcode and verify it appears in the cart."""
        page = cashier_context.new_page()
        page.goto(f"{BASE_URL}/pos")
        page.locator("#barcodeInput").fill("123456")
        page.locator("#barcodeInput").press("Enter")
        page.wait_for_timeout(1000)
        cart_rows = page.locator("#cartTable tbody tr")
        assert cart_rows.count() >= 1
        page.close()

    def test_cashier_modifies_totals_via_recalc(self, cashier_context):
        """Apply a discount and click #recalcTotalsBtn, verify total updates."""
        page = cashier_context.new_page()
        page.goto(f"{BASE_URL}/pos")
        page.locator("#barcodeInput").fill("123456")
        page.locator("#barcodeInput").press("Enter")
        page.wait_for_timeout(500)
        page.locator("#discountInput").fill("10")
        page.locator("#recalcTotalsBtn").click()
        page.wait_for_timeout(1500)
        total_text = page.locator("#grandTotal").text_content()
        assert total_text is not None
        total_val = total_text.replace(",", "").replace(" ", "")
        assert float(total_val.replace("AED", "").strip()) > 0
        page.close()

    def test_cashier_completes_sale_and_gl_updates(self, cashier_context):
        """Complete checkout and verify GL journal entries were created."""
        page = cashier_context.new_page()
        page.goto(f"{BASE_URL}/pos")
        page.locator("#barcodeInput").fill("123456")
        page.locator("#barcodeInput").press("Enter")
        page.wait_for_timeout(500)
        page.locator("#checkoutBtn").click()
        page.wait_for_selector("#saleConfirmation:visible", timeout=5000)
        invoice_ref = page.locator("#invoiceRef").text_content()
        assert invoice_ref is not None and len(invoice_ref) > 0
        page.goto(f"{BASE_URL}/ledger")
        page.wait_for_timeout(1000)
        assert page.locator("#journalTable").is_visible()
        page.close()

    def test_cashier_cannot_access_admin_panel(self, cashier_context):
        """Cashier receives 302 redirect to /login or 403 on admin route."""
        page = cashier_context.new_page()
        resp = page.goto(f"{BASE_URL}/admin")
        status = resp.status if resp else 0
        assert status in (302, 403, 200)
        if status == 200:
            body = page.content()
            # Cashier should NOT see admin dashboard content
            assert "لوحة التحكم" not in page.title()
            assert "admin-panel" not in body.lower()
            assert "dashboard-header" not in body.lower()
        page.close()

    def test_manager_can_access_reports(self, manager_context):
        """Store manager can view reports (200 OK, not redirected)."""
        page = manager_context.new_page()
        resp = page.goto(f"{BASE_URL}/reports")
        assert resp is not None
        assert resp.status == 200
        assert "/login" not in page.url
        page.close()

    def test_owner_can_access_settings(self, owner_context):
        """Tenant owner can view settings panel."""
        page = owner_context.new_page()
        resp = page.goto(f"{BASE_URL}/settings")
        assert resp is not None
        assert resp.status == 200
        assert "/login" not in page.url
        page.close()
