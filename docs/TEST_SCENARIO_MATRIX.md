# Azadexa — Test Scenario Matrix (QA Lead)

Scenario catalogue across tenant roles. The status labels below were recorded
during earlier work and are **not** a verified execution report for the current
revision: some cases use mocks or parameter grids, and some runs were interrupted.
Do not add the rows or parameter values up as independent real-world workflows.
**P** means previously reported passing, **M** denotes a mocked boundary,
**R** means the implementation is under verification, and **O** is an open gap.
`scripts/run_5k_real_world_simulation.py` did not complete a verified run; its
direct execution is disabled because its database safety and counting are not
established.

Legend for vectors: IDOR = cross-tenant object reference, ESC = privilege
escalation, RCE = rollback/atomicity, CC = concurrency, FX = currency.

## 1. RBAC & Tenant Isolation

| ID | Scenario | Actors | Steps | Expected | Vec | St |
|---|---|---|---|---|---|---|
| RB-01 | Cross-tenant sale read via API | Sales agent (T1) vs sale of T2 | GET /api/sales/{foreign_id} | 404/403, no data leak | IDOR | P |
| RB-02 | Cross-tenant customer/supplier balance | T1 user probing T2 ids | balance endpoints | Zero / refused | IDOR | P |
| RB-03 | Cheque summary cross-tenant | T1 | GET cheque summary T2 | Blocked | IDOR | P |
| RB-04 | Foreign tenant untouched by scoped queries | T1 session | list sales/expenses/partners | Only T1 rows | IDOR | P |
| RB-05 | Seller cannot view another seller's sale | Seller A vs B | GET /sales/{B} | Redirect/denied | ESC | P |
| RB-06 | Permission hierarchy: view_reports ≠ manage_sales | Auditor role | POST sales routes | 403 | ESC | P |
| RB-07 | Warehouse keeper scoped to own warehouse | Keeper W1 | create expense W2 | Refused | ESC | P |
| RB-08 | Owner-only surfaces | Company admin | /owner/* | 403 | ESC | P |
| RB-09 | Partner unlink blocked by other partner | T1 | unlink customer of P2 | Refused | IDOR | P |
| RB-10 | Branch-scope enforcement on save | Branch user | edit other branch doc | 403 | ESC | P |

## 2. Financial & Accounting Integrity

| ID | Scenario | Steps | Expected (Dr=Cr) | St |
|---|---|---|---|---|
| FI-01 | Sale posts balanced journal; AR control = invoice total | create sale via service | Dr AR = Cr revenue+VAT | P |
| FI-02 | Return reverses revenue/COGS/tax proportionally | return 1 of 2 units | Legs balanced; GL parity with original | P |
| FI-03 | Partner distribution approve → commission Dr / partner Cr | approve warehouse dist | Entry balanced 50/50; balance synced | P |
| FI-04 | Distribution pay → cash leg; balance to zero | pay approved dist | Withdrawal recorded; balance 0 | P |
| FI-05 | Sequential allocation conserves profit | W50+B50+C50 on 1000 | 500+250+125, company keeps 125 | P |
| FI-06 | Fixed before %, actual days, sequential losses | golden grids | Hand-computed dues | P |
| FI-07 | Expense not deducted twice | expense_share 20% metadata | expense_share_amount = 0 | P |
| FI-08 | Scope P&L nets returns in return period | Jan sale, Feb return | Feb revenue −100, COGS −50 | P |
| FI-09 | VAT return equals journal | VAT legs 160/80/−16 | Output 144, input 80, net 64 | P |
| FI-10 | Journal invariants: every entry balanced, trial zero | post varied amounts | 0.001 tolerance | P |
| FI-11 | Atomic rollback on posting failure | flush failure mid-distribute | No partial rows | P |
| FI-12 | Unified statement net payable | draft 100 + approved 60 + commission 40−20 | combined 80, draft separate | P |
| FI-13 | Expense WHT chargeable leg | non-resident service 5% | Dr expense 100 / Cr cash 95 / Cr WHT 5 | P |
| FI-14 | Period close reconciles to the cent | 300 invoices via route | TB/AR/AP/VAT/inventory agree | P |

## 3. Tax & Compliance

| ID | Scenario | Expected | St |
|---|---|---|---|
| TX-01 | Inclusive VAT stripped from revenue | 116−16 = 100 revenue | P |
| TX-02 | Return VAT per line category (standard/zero/exempt) | zero line adds no VAT | P |
| TX-03 | VAT-inclusive refund = paid gross | refund 110 = 100 + 10 | P |
| TX-04 | Statutory VAT single source (PS16/IL18/AE5/SA15) | strategy == country_tax | P |
| TX-05 | E-invoice UBL persisted w/ hash; QR for KSA | artifact served under print guard | P |
| TX-06 | ITA payload carries all mandatory fields | IssuanceDate/BeforeDiscount/Discount present | P |
| TX-07 | ZATCA submission signature and responses | Local prototype; XML signature compliance and sandbox acceptance unverified | R/M |
| TX-08 | Import levies: customs default + excise on CIF+duty | AE tobacco 1050 etc. | P |
| TX-09 | Statutory payroll withholdings (PS/IL/SA/AE) | employee/employer per tables | P |
| TX-10 | Live authority round-trip (ZATCA/ITA) | credentials required | **O** |

## 4. Operational & Administrative

| ID | Scenario | Expected | St |
|---|---|---|---|
| OP-01 | Quotation draft→sent→accepted→converted | status guards each step | P |
| OP-02 | Expired quotation cannot be accepted/converted | Reject expired accepted quote using its expiry date | R |
| OP-03 | Conversion checks stock for a selected warehouse | Reject insufficient stock; the created draft does not reserve it | R |
| OP-04 | Double conversion refused | sale_id set → refused | P |
| OP-05 | Concurrent writers: no oversell/double charge | 30 writers, ledger balances | P |
| OP-06 | Sequence numbers row-locked | unique, no gaps/duplicates | P |
| OP-07 | Feature-flag blueprint 403 despite permission | flag off → 403 | P |
| OP-08 | Session switch requires logout first | second login no-op | P |
| OP-09 | Stock-sync / POS idempotency keys | no double posting | P |
| OP-10 | Cheque bounce/withholding integrity | balanced reversal | P |

The selected-warehouse check in OP-03 is only a point-in-time precheck. It is
not a reservation or a concurrency guarantee. With no warehouse selected, a
draft can be created without a stock check; fulfillment must enforce inventory.

## 5. Currency / FX

| ID | Scenario | Expected | St |
|---|---|---|---|
| FX-01 | Resolver priority: user > parity > cache > online > fallback | source metadata pinned | P |
| FX-02 | Online fetch failures degrade to fallback | 500/bad-JSON/timeout safe | P |
| FX-03 | Cache tenant-isolated; TTL refetch | 1 fetch per tenant | P |
| FX-04 | Non-AED base refuses AED fallback (D12) | needs_input, rate None | P |
| FX-05 | Commission margin FX-consistent | cost/rate before margin | P |
| FX-06 | Multi-currency revenue in base | amount_aed == amount×rate | P |
| FX-07 | Manual rate audit note below server rate | note appended | P |

## 6. Inventory / Purchasing

| ID | Scenario | Expected | St |
|---|---|---|---|
| IN-01 | MWAC receipt/sale invariants | qty/value/avg conserved | P |
| IN-02 | Stock movement posts balanced | inventory Dr/Cr | P |
| IN-03 | Negative inventory only if allowed | refused otherwise | P |
| PU-01 | Purchase posts AP+VAT balanced | Dr inventory/input VAT | P |
| PU-02 | Import default customs/excise | statutory defaults, explicit wins | P |

*This matrix is the index; the executable cases live in
`tests/unit/services/test_scenario_mega_*.py`,
`tests/integration/test_*scenarios*.py`, and the scenario catalog.*
