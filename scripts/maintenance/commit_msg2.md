Fix exchange rate resolution priority and add manual rate management

- Update ExchangeRateService.resolve_exchange_rate_for_transaction():
  Priority: 1) fixed_rate (frozen), 2) user_rate (form input),
  3) admin_rate (manager-stored in exchange_rate_records),
  4) online_rate (API, auto-saved to records),
  5) last_record (any previous record), 6) needs_input (modal)
- Add _get_admin_rate(), _fetch_and_store_online_rate(),
  _get_last_known_rate(), _save_rate_record(), save_manual_rate()
  to actually use the ExchangeRateRecord table (was dead before)
- Add owner route /exchange-rates with full CRUD for manual rates
- Add owner/exchange_rates.html template with rate entry form + history table
- Update currency_settings.html to link to the new exchange rates page
- Update SaleService, PurchaseService, PaymentService to pass tenant_id
  and handle needs_input with clear user-facing error messages

Tests: 327 passed, 1 failed (pre-existing CSRF in support.js unrelated).

Generated with Devin (https://cli.devin.ai/docs)
Co-Authored-By: Devin <158243242+devin-ai-integration[bot]@users.noreply.github.com>
