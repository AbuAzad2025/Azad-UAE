# Maintenance module: release status

**The maintenance module is live.** The blueprint is registered in
`bootstrap/blueprints.py`, the tenant flag `enable_maintenance` defaults to
on, and the module owns its own accounts, its own permissions and its own
sub-ledger.

What it does today:

* a maintenance order is received, diagnosed, worked on, and closed by the
  reception counter; every transition is recorded in an append-only status
  history;
* spare parts leave the maintenance warehouse at the warehouse's real
  moving-average cost, through the same locked stock path the sales module
  uses, with a `ProductCostHistory` audit row for every movement;
* closing an order issues one invoice and one receipt and posts three
  balanced journal entries (parts cost, revenue, receipt) in one atomic
  transaction;
* a deposit is a liability, not revenue: it is credited to the
  maintenance deposit account, and when the order closes it is applied
  against the invoice (Dr deposit / Cr receivable) so the sub-ledger
  reconciles with the order's balance due;
* a return reverses the revenue, the tax and the parts cost together, and
  puts the parts back on the shelf;
* three reports answer the workshop's own questions: the revenue report
  (invoices, tax, outstanding), the parts-issued report (which part went
  into which job, and at what cost) and the warranty report (how many
  devices are covered, expired, void or unknown);
* **five reports** in all — the three above plus the margin report (the
  revenue a job carried less the cost of the parts it consumed) and the
  engineer performance report (how many jobs each engineer worked, what
  they were worth, and the planned duration of the service lines);
* **the other half of the module: buying the parts.** A purchase order
  names the supplier and the maintenance warehouse; receiving it puts the
  goods on the shelf at the supplier's cost, rebuilds the warehouse's
  moving average, and posts the inventory against the supplier's payable
  with the recoverable tax on the input-tax account. The tax is never
  capitalised into the stock — that would inflate the moving average
  every part is later issued at;
* **the customer has one balance.** The maintenance receivable is its
  own account, but the customer's statement shows the maintenance charge
  and the maintenance receipt next to the trade ones, and the statement
  can be filtered to the maintenance movements alone;
* **the statutory document.** A maintenance job is a sale for the tax
  authority: the customer receives a service, pays a tax, and is
  entitled to the same UBL 2.1 document (and the same KSA TLV QR) the
  trade path issues. The artifact hangs off the maintenance invoice, so
  the two ledgers never share a key, and it is produced inside the close
  transaction — a broken document rolls the close back rather than
  committing an invoice the customer cannot download;
* the warranty is checked at reception, can be cancelled and restored under
  authorisation, and every change is written to an audit trail that the
  database refuses to let anyone edit or delete;
* the device registry is the module's memory of what it has seen: the
  reception counter registers the device on the order (serial number, IMEI
  or plate) with the warranty period it is entitled to, and a later order
  for the same device is recognised. Without a registration the check can
  only answer "unknown" — which is the honest answer, not a silent pass.

## The sub-ledger

The module never posts into the trade ledger's accounts:

| Concept | Account | What it carries |
|---|---|---|
| `MAINTENANCE_AR` | 1134 | Maintenance receivables (the trade receivable 1130 is untouched) |
| `MAINTENANCE_REVENUE` | 4119 | Maintenance revenue (the sales revenue 4100 is untouched) |
| `MAINTENANCE_COGS` | 5119 | The cost of the spare parts a job consumed |
| `MAINTENANCE_DEPOSIT` | 2171 | Deposits taken at reception |
| `MAINTENANCE_CASH_DIFFERENCE` | 6560 | The reception drawer's difference |
| `MAINTENANCE_AP` | 2110 | Payables to the spare-parts supplier (the tenant's own AP) |

The accounts are created for every tenant by the chart builder and by the
module's migration for tenants that already had a chart; the concept
mappings are provisioned by the `maintenance` GL module, which is gated on
the tenant's `enable_maintenance` flag.

## Permissions

`manage_maintenance`, `maintenance_receive`, `maintenance_work`,
`maintenance_close`, `maintenance_discount` and
`maintenance_override_discount` are seeded and grantable. The discount
limits live in the tenant's maintenance settings; a discount above the
limit needs the override permission.

The two discount permissions are enforced in the service layer, not at the
route, because only the service knows the amount: a line discount, the
order-level discount and a price override all check the tenant's caps
against the actor's permissions before the order is recalculated. The
order-level discount is allocated over the lines by the largest-remainder
method and each line keeps its share, so a return of one line reverses
exactly the share that line carried.

## Known limits

* Pricing is in the tenant's default currency. A foreign-currency order is
  refused rather than priced at a rate the module cannot defend.
* A cheque receipt is refused: a cheque is a receivable and belongs to the
  cheque module's lifecycle, not to a cash receipt here.
* The parts-cost entry assumes the tenant has mapped `MAINTENANCE_COGS` and
  `INVENTORY_ASSET`; an unmapped concept is refused by the resolver rather
  than posted somewhere approximate.
* Deleting a tenant that has maintenance records is refused by the
  archive-only triggers. The tenant lifecycle must account for that.
* A part's own serial number is not tracked through the maintenance
  issue: the module moves the quantity and the cost, and lot tracking is
  handled by the FEFO batch path. The core serial-tracking service is a
  warehouse-assignment concern that the trade path does not use on issue
  either, so the maintenance path stays consistent with it.
* **A return after the customer has paid leaves a credit balance, not a
  refund.** The return reverses the revenue, the tax and the parts cost
  and credits the maintenance receivable — which is right — but there is
  no refund voucher in the module, so a customer who paid in full and
  then returned a part ends up with a negative receivable that nobody can
  settle. A refund path (paying the credit back, or offsetting it
  against the next order) is not implemented; the credit balance is the
  honest representation of what is owed, and it has to be worked off by
  hand.

## What proves it

* `tests/integration/test_maintenance_money_path.py` — the money path,
  end to end against the database: the parts leave the shelf at the
  moving-average cost, the invoice and the receipt and the parts cost are
  posted as balanced entries, the maintenance sub-ledger stays separate
  from the trade ledger, a deposit is applied against the invoice, a
  return reverses the revenue, the tax and the cost together, the
  statutory document is produced, the customer's statement carries the
  maintenance movements, and one tenant's money never appears in
  another's ledger.
* `tests/integration/test_maintenance_purchase_path.py` — the purchase
  path: the goods arrive at the supplier's cost, the moving average moves
  with them, the inventory is debited net of the tax, and receiving the
  same order twice is refused.
* `tests/unit/services/test_maintenance_financial_safety.py` — the
  calculation rules, the append-only warranty audit, and the refusal of a
  posting that has no document behind it.
* `tests/unit/services/test_maintenance_order_service.py` — the order
  lifecycle, the state machine, the discount limits, the rule that
  only the close-and-collect path may close an order, the device
  registry round trip (register → check → the warranty is found), and
  the reports.
* `tests/unit/routes/test_maintenance_routes.py` — the HTTP surface: the
  guards, the tenant scope, and that a refused write writes nothing.
