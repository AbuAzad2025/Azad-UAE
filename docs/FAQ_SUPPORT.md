# FAQ — Technical Support

## 1. Access and Authentication

**Q: I forgot my password.**
A: Click "Forgot Password" on the login page. Enter your email. A reset link will be sent within 2 minutes. If you do not receive it, check spam or contact support.

**Q: My account is locked.**
A: Accounts lock after 5 failed login attempts. Wait 15 minutes or contact your admin to unlock. If you are the owner, contact support with proof of identity.

**Q: How do I enable two-factor authentication?**
A: 2FA is available for owner and admin accounts. Go to Settings → Security → Enable 2FA. Scan the QR code with Google Authenticator or Authy.

## 2. Data and Display

**Q: My data is not showing.**
A: Check the following:
1. Ensure you are in the correct branch (top-right selector).
2. Check date filters on the report or list.
3. Clear browser cache (Ctrl+Shift+R).
4. If still missing, verify the data was saved successfully (check audit logs).

**Q: Numbers look wrong (e.g., 1,000 shown as 1).**
A: Check your browser locale and the system's decimal separator setting (Settings → Regional). Arabic locales use comma as decimal separator.

## 3. Sales and Invoices

**Q: I created a sale but the stock did not deduct.**
A: Stock deducts when the sale status is "Confirmed" or "Paid". If the sale is still "Draft", confirm it. If the product is a service (non-stock), no deduction occurs.

**Q: Can I edit an invoice after printing?**
A: Invoices marked as "Finalized" cannot be edited. You must create a credit note or return. Go to Sales → Returns.

**Q: How do I add a discount to an invoice?**
A: In the sale form, click "Discount" and enter percentage or fixed amount. Ensure you have permission `apply_discount`.

## 4. Inventory

**Q: How do I add a new warehouse?**
A: Go to Warehouses → New. Enter name, code, and branch. Only users with `manage_warehouses` permission can add warehouses.

**Q: How do I transfer stock between branches?**
A: Go to Inventory → Transfer. Select source and destination warehouses, add products and quantities. The transfer creates two movements: deduct from source, add to destination.

**Q: My physical count does not match the system.**
A: Go to Inventory → Reconciliation. Select the warehouse and product. Enter the actual count. The system calculates the difference and suggests an adjustment journal entry.

**Q: What is WAC and why did my cost price change?**
A: WAC (Weighted Average Cost) recalculates after every purchase receipt. This ensures your cost of goods sold reflects the average price paid. It is the default method. You can switch to FIFO in Settings → Inventory (Enterprise plan only).

## 5. Payments and Cheques

**Q: How do I record a bounced cheque?**
A: Go to Cheques → select the cheque → Bounce. The system creates a reversal journal entry and updates the customer balance.

**Q: Can I accept partial payment for an invoice?**
A: Yes. In the payment screen, enter the partial amount. The invoice will show "Partially Paid" with the remaining balance.

**Q: How do I reconcile my bank account?**
A: Go to Banking → Reconciliation. Import your bank statement (CSV/Excel). The system matches transactions automatically. Unmatched items appear for manual review.

## 6. POS

**Q: The POS is slow.**
A: Check internet connectivity. The POS caches product data locally. If the issue persists, contact support with the branch ID and timestamp.

**Q: Can I use POS offline?**
A: Critical operations (create sale, print receipt) work offline for up to 2 hours. Data syncs automatically when connectivity returns. Full offline mode is on the roadmap.

**Q: How do I apply a promotion at POS?**
A: The promotion engine applies eligible promotions automatically at checkout. To force apply, click "Promotions" and select manually.

## 7. HR and Payroll

**Q: How do I calculate payroll?**
A: Go to Payroll → Process. Select the month and employees. The system calculates basic salary, allowances, deductions, tax, and insurance. Review and confirm.

**Q: Can I export payroll to WPS?**
A: WPS export is on the roadmap (Q4 2026). Currently, export to Excel and upload manually.

**Q: How do I record attendance?**
A: Employees check in via the attendance screen or biometric integration (roadmap). Manual entry is available for admins.

## 8. Reports

**Q: How do I export a report to Excel?**
A: On any report page, click the "Export" button (top-right). Choose Excel or PDF.

**Q: Can I schedule reports to email automatically?**
A: Scheduled reports are available on Professional and Enterprise plans. Go to Reports → Scheduled → New.

**Q: My trial balance does not balance.**
A: This indicates a data integrity issue. Do not ignore it. Contact support immediately with the period and branch. We will run a diagnostic.

## 9. AI Assistant

**Q: The AI gave a wrong answer.**
A: The AI recommendations are based on your data patterns and are advisory. Always verify critical decisions (pricing, orders) with a human manager. Report incorrect answers to improve the model.

**Q: Can the AI delete data?**
A: No. The AI cannot create, edit, or delete records without explicit human confirmation. Sensitive actions are gated by `confirm_required` in the ActionDispatcher.

## 10. Integrations

**Q: How do I connect my external POS?**
A: Generate an API key in Settings → API Keys. Use the key with `POST /api/v2/stock/sync`. See `docs/INTEGRATION_GUIDE.md`.

**Q: Can I connect Shopify?**
A: Shopify integration is on the roadmap (Q4 2026). Currently, use the API for custom integrations.

## 11. Billing and Account

**Q: How do I upgrade my plan?**
A: Contact your account manager or email billing@azadsystems.com.

**Q: How do I cancel?**
A: Submit a cancellation request 30 days in advance via email. You have 30 days to export data after cancellation.

## 12. Contact Support

| Channel | Detail | Hours |
|---------|--------|-------|
| Email | support@azadsystems.com | 24/7 |
| WhatsApp | +972 56 215 0193 | 08:00–20:00 GST |
| Phone | +972 56 215 0193 | 08:00–20:00 GST |
| Ticket | In-app Support → New Ticket | 24/7 |

**Severity levels:**
- P1 (System down): Call or WhatsApp immediately.
- P2 (Major feature broken): Email or WhatsApp.
- P3 (Question / Minor issue): Ticket or email.
