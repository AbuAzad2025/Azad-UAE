"""The scenario catalogue - the single index of what a real scenario is.

Why this exists
---------------
Coverage of a system this size cannot be tracked in prose, and "no duplication"
cannot be enforced by remembering. Both claims rot silently. So the catalogue is
data: every scenario has an identifier, identifiers are unique by construction,
and ``tests/unit/test_scenario_catalog.py`` fails if a test claims an identifier
twice, if an identifier has no test, or if a wave falls short of its budget.

The numbers below are not aspiration. Each wave's budget is derived from the
route inventory measured against the tree (748 ``@route`` decorators across 65
blueprints), then given a depth multiplier - a CRUD screen is not one scenario,
it is: read, write, reject, authorise, boundary. A blueprint whose routes are
barely reachable earns a smaller budget; one that moves money earns more.

Identifier scheme
-----------------
``S-NN``          the original wave 0-6 scenarios, kept as-is
``<PREFIX>-NN``   everything after, where PREFIX names the domain

A prefix is unique to one domain, so ``POS-07`` and ``GL-07`` can coexist and a
duplicated identifier is a typo rather than a collision. Scenarios declare their
identifier with ``@scenario("POS-07")``; the pre-existing S-NN scenarios are
read out of their docstrings instead, so those files stay untouched.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Domain:
    """One functional area and the depth each of its screens gets tested at."""

    prefix: str
    title: str
    blueprints: tuple[str, ...]
    #: how many scenarios per covered route on average, after the fixed wave budget
    depth: float
    #: what the scenarios are actually asserting - used to keep the budget honest
    intent: str = ""

    @property
    def routes(self) -> int:
        """Route count, filled in by measure_routes() at import time."""
        return sum(_ROUTE_COUNTS.get(b, 0) for b in self.blueprints)


@dataclass(frozen=True)
class Wave:
    """A batch of domains that can be reviewed and landed together.

    ``fixed_scenarios`` is only for waves 0-6, which predate the catalogue and are
    counted by their S-NN identifiers. From wave 7 the number is *derived* from the
    domains' budgets, so a blueprint added to a domain moves the wave's total with
    it instead of leaving a stale hand-written figure behind.
    """

    number: int
    title: str
    domains: tuple[Domain, ...]
    fixed_scenarios: int = 0

    @property
    def prefixes(self) -> tuple[str, ...]:
        return tuple(d.prefix for d in self.domains)

    @property
    def scenarios(self) -> int:
        derived = sum(domain_budget(d) for d in self.domains)
        return derived + self.fixed_scenarios


# ── measured route inventory, keyed by path under routes/ ──
#
# Keyed by path, not by module stem: routes/tenants.py and routes/owner/tenants.py
# are different surfaces that a stem-keyed inventory silently collapsed into one,
# which is how 23 routes went missing from the first version of this table.
_ROUTE_COUNTS: dict[str, int] = {
    "admin_ledger": 16,
    "advanced_ledger": 22,
    "ai_routes/analytics": 10,
    "ai_routes/assistant": 3,
    "ai_routes/chat": 7,
    "ai_routes/knowledge": 14,
    "ai_routes/specialized": 7,
    "ai_routes/system": 9,
    "api": 20,
    "api_analytics": 5,
    "api_docs": 3,
    "api_enhanced": 6,
    "assets": 7,
    "auth": 12,
    "billing_webhooks": 3,
    "branches": 4,
    "budget": 10,
    "cheques": 16,
    "crm": 8,
    "customers": 11,
    "email_marketing": 8,
    "expenses": 12,
    "gamification": 3,
    "graphql": 2,
    "hr": 17,
    "language": 1,
    "ledger": 32,
    "main": 10,
    "monitoring": 3,
    "owner/ai_training": 4,
    "owner/ai_training_advanced": 8,
    "owner/backups": 10,
    "owner/core": 8,
    "owner/database": 16,
    "owner/maintenance": 6,
    "owner/monitoring": 14,
    "owner/settings": 26,
    "owner/tenants": 14,
    "owner/users": 6,
    "owner_admin": 3,
    "partners": 11,
    "payment_vault": 42,
    "payments": 20,
    "payroll": 6,
    "pos": 59,
    "printing": 11,
    "products": 17,
    "projects": 9,
    "public": 14,
    "purchases": 18,
    "quotations": 9,
    "reports": 20,
    "returns": 5,
    "sales": 12,
    "shipments": 10,
    "shop": 37,
    "stock_sync": 2,
    "store": 11,
    "suppliers": 8,
    "tenant_backups": 5,
    "tenants": 1,
    "tickets": 8,
    "transfers": 7,
    "treasury": 4,
    "unified_inventory": 6,
    "users": 6,
    "warehouse": 14,
    "whatsapp": 3,
}
ORIGINAL_SCENARIO_COUNT = 76
TARGET_SCENARIO_COUNT = 1000


WAVES: tuple[Wave, ...] = (
    Wave(
        number=0,
        title="Foundations - tenant, branch, user, and the permission boundary",
        domains=(),
        fixed_scenarios=9,
    ),
    Wave(
        number=1,
        title="Sales desk - one cash sale across every surface",
        domains=(),
        fixed_scenarios=10,
    ),
    Wave(
        number=2,
        title="Cheques, returns and receipt vouchers",
        domains=(),
        fixed_scenarios=13,
    ),
    Wave(
        number=3,
        title="Online store - publication gates and deferred fulfilment",
        domains=(),
        fixed_scenarios=11,
    ),
    Wave(
        number=4,
        title="Purchasing, transfers and cost-valued adjustments",
        domains=(),
        fixed_scenarios=12,
    ),
    Wave(
        number=5,
        title="Budgets and quotations",
        domains=(),
        fixed_scenarios=7,
    ),
    Wave(
        number=6,
        title="Accounting spine - balance, periods, reversal",
        domains=(),
        fixed_scenarios=14,
    ),
    Wave(
        number=7,
        title="Owner and platform - tenant lifecycle, packages, backups",
        domains=(
            Domain(
                "OWN",
                "Owner panel and platform administration",
                ("owner/tenants", "owner/core", "owner/maintenance", "owner_admin", "tenants"),
                3.0,
                "owner-only reachability and the blast radius of a platform action",
            ),
            Domain(
                "PKG",
                "SaaS packages, plans and subscription billing",
                ("payment_vault", "billing_webhooks"),
                1.6,
                "pricing is owner-set; a tenant may read but never write it",
            ),
            Domain(
                "BAK",
                "Backups, restore and tenant data portability",
                ("owner/backups", "owner/database", "tenant_backups"),
                2.2,
                "a restore that is not byte-exact is not a backup",
            ),
            Domain(
                "MON",
                "Monitoring, health and maintenance windows",
                ("owner/monitoring", "monitoring"),
                2.2,
                "health endpoints must not leak internals to an unauthenticated caller",
            ),
        ),
    ),
    Wave(
        number=8,
        title="Accounting II - the full ledger surface and money movement",
        domains=(
            Domain(
                "LED",
                "General ledger - journals, accounts, period close",
                ("ledger", "admin_ledger"),
                2.4,
                "every posting balanced, tenant-scoped and inside an open period",
            ),
            Domain(
                "ADV",
                "Advanced ledger - consolidation, FX, revaluation, budgets",
                ("advanced_ledger", "treasury"),
                2.2,
                "the paths where a wrong account is still arithmetically balanced",
            ),
            Domain(
                "EXP",
                "Expenses, payroll runs and statutory deduction",
                ("expenses", "payroll"),
                2.4,
                "an expense deletes to archive; a payroll run does not go negative",
            ),
            Domain(
                "RPT",
                "Financial and operational reporting",
                ("reports", "api_analytics"),
                1.5,
                "a report that aggregates across tenants is a data breach",
            ),
            Domain(
                "BUD",
                "Budgets, envelopes and enforcement",
                ("budget",),
                2.4,
                "budget.create and budget.approve are separate permissions and must stay so",
            ),
        ),
    ),
    Wave(
        number=9,
        title="Sales, CRM and the customer ledger",
        domains=(
            Domain(
                "SAL",
                "Sales orders, invoices and receipts",
                ("sales", "shipments", "returns"),
                2.4,
                "paid means paid - the direction bug that shipped here cost real money",
            ),
            Domain(
                "CRM",
                "CRM pipeline, stages and activities",
                ("crm", "tickets"),
                2.0,
                "stage transitions and their authorisation, not just the create",
            ),
            Domain(
                "CUS",
                "Customers, suppliers and partners",
                ("customers", "suppliers", "partners"),
                2.2,
                "a customer balance may never be silently overwritten",
            ),
            Domain(
                "QOT",
                "Quotations and conversion to order",
                ("quotations",),
                2.2,
                "conversion is a money path that must be idempotent",
            ),
        ),
    ),
    Wave(
        number=10,
        title="Inventory and warehousing",
        domains=(
            Domain(
                "WHS",
                "Warehouses, stock and movements",
                ("warehouse", "transfers", "unified_inventory", "stock_sync"),
                2.4,
                "stock cannot go negative and cannot be moved silently",
            ),
            Domain(
                "PRD",
                "Products, categories, import and export",
                ("products", "assets"),
                1.8,
                "import is a write path with no undo",
            ),
            Domain(
                "PUR",
                "Purchase orders, receipts and supplier settlement",
                ("purchases",),
                2.2,
                "a purchase received twice is inventory that does not exist",
            ),
        ),
    ),
    Wave(
        number=11,
        title="Point of sale - the largest single surface",
        domains=(
            Domain(
                "POS",
                "POS carts, checkout, shifts and hardware",
                ("pos",),
                1.5,
                "money in the drawer, and the two screens that disagree",
            ),
        ),
    ),
    Wave(
        number=12,
        title="Payments, cheques and treasury",
        domains=(
            Domain(
                "PAY",
                "Payments, refunds and allocation",
                ("payments", "whatsapp", "auth"),
                2.2,
                "a refund must not exceed the captured amount",
            ),
            Domain(
                "CHQ",
                "Cheque lifecycle and reconciliation",
                ("cheques",),
                2.4,
                "an unreconcilable instrument is worse than a missing one",
            ),
        ),
    ),
    Wave(
        number=13,
        title="People - employees, attendance, leave and payroll input",
        domains=(
            Domain(
                "HR",
                "Employees, attendance, leave and documents",
                ("hr",),
                2.2,
                "an employee record is personal data with an audit trail",
            ),
        ),
    ),
    Wave(
        number=14,
        title="Marketing, engagement and knowledge",
        domains=(
            Domain(
                "MKT",
                "Email marketing, campaigns and gamification",
                ("email_marketing", "gamification"),
                2.0,
                "sending on a customer's behalf needs an explicit opt-in record",
            ),
            Domain(
                "AI",
                "AI training, assistant, chat and knowledge base",
                (
                    "ai_routes/system",
                    "ai_routes/assistant",
                    "ai_routes/chat",
                    "ai_routes/knowledge",
                    "ai_routes/specialized",
                    "ai_routes/analytics",
                    "owner/ai_training",
                    "owner/ai_training_advanced",
                ),
                1.6,
                "AI output must never bypass the permission model",
            ),
            Domain(
                "PRJ",
                "Projects and service delivery",
                ("projects",),
                2.0,
                "project time and money roll up to the right tenant",
            ),
        ),
    ),
    Wave(
        number=15,
        title="Storefront and public surface",
        domains=(
            Domain(
                "SHOP",
                "Storefront catalogue, cart and checkout",
                ("shop", "store"),
                1.8,
                "the public catalogue is the only unauthenticated money path",
            ),
            Domain(
                "PUB",
                "Public pages, donations and packages",
                ("public",),
                1.6,
                "a public donation must never be creditable to the wrong tenant",
            ),
        ),
    ),
    Wave(
        number=16,
        title="Settings, users, roles, localisation and the API surface",
        domains=(
            Domain(
                "SET",
                "Tenant settings and configuration",
                ("owner/settings",),
                1.8,
                "a setting that changes money handling is not a preference",
            ),
            Domain(
                "USR",
                "Users, roles and permissions",
                ("owner/users", "users", "branches", "language"),
                2.2,
                "privilege escalation through a role edit",
            ),
            Domain(
                "API",
                "API surface, docs and GraphQL",
                ("api", "api_enhanced", "api_docs", "graphql", "printing"),
                1.2,
                "the documented contract has to match the running code",
            ),
            Domain(
                "HOM",
                "Dashboard, home and navigation shell",
                ("main",),
                1.5,
                "the first screen every operator sees, and its tenant scope",
            ),
        ),
    ),
)


ALL_DOMAINS: tuple[Domain, ...] = tuple(d for w in WAVES for d in w.domains)
PREFIXES: frozenset[str] = frozenset(d.prefix for d in ALL_DOMAINS)


def scenario_id(prefix: str, n: int) -> str:
    """``("POS", 7)`` -> ``"POS-07"``."""
    if prefix not in PREFIXES:
        raise KeyError(f"{prefix!r} is not a catalogued domain prefix; known: {sorted(PREFIXES)}")
    return f"{prefix}-{n:02d}"


def allocated_scenarios() -> int:
    """How many scenarios the plan commits to, catalogue plus originals."""
    return ORIGINAL_SCENARIO_COUNT + sum(w.scenarios for w in WAVES)


def coverage_gap() -> int:
    return TARGET_SCENARIO_COUNT - allocated_scenarios()


def domain_budget(dom: Domain) -> int:
    """Scenarios this domain owes, spread across its routes."""
    return max(1, round(dom.routes * dom.depth))


def domain_budgets() -> dict[str, int]:
    out: dict[str, int] = {}
    for d in ALL_DOMAINS:
        out[d.prefix] = domain_budget(d)
    return out


def wave_domains(wave_number: int) -> tuple[Domain, ...]:
    for w in WAVES:
        if w.number == wave_number:
            return w.domains
    raise KeyError(f"no wave {wave_number}")
