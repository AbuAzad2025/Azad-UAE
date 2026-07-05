"""Owner blueprint package — routes split into sub-modules for maintainability."""

# ── Re-exports (for testing + shared access across sub-modules) ──────────────
# These are defined here before sub-module imports so sub-modules can import
# from `routes.owner` instead of importing directly from flask/models/utils.
# This allows the test suite's `patch("routes.owner.X")` to intercept calls
# made inside any sub-module.

from flask import (
    Blueprint, render_template, request, jsonify, flash, redirect,
    url_for, current_app, abort,
)
from flask_login import login_required, current_user
from sqlalchemy import func, desc, text, inspect
from extensions import db, limiter

from models import (
    User, Customer, Product, Sale, SaleLine, Purchase, Payment, Receipt,
    StockMovement, AuditLog, ArchivedRecord, ProductReturn, CardVault,
    InvoiceSettings, Tenant, SystemSettings, IntegrationSettings,
    Expense, Branch, Warehouse, Role, Donation,
)
from models.login_history import LoginHistory
from models.security_alert import SecurityAlert
from models.api_key import APIKey
from models.tenant_store import TenantStore
from models.exchange_rate_record import ExchangeRateRecord
from models.payment_vault import PaymentVault
from models.product_warehouse_cost import ProductWarehouseCost
from models.store_payment_method import StorePaymentMethod

from utils.decorators import owner_required, permission_required, company_admin_required, owner_or_company_admin
from utils.branching import role_requires_branch, get_visible_products_query
from utils.auth_helpers import (
    role_level_for, role_level_for_user, is_global_owner_user,
    user_may_have_null_tenant, enforce_company_user_tenant,
)
from utils.tenanting import get_active_tenant_id
from utils.currency_utils import get_system_default_currency, resolve_default_currency
from utils.ai_access import get_tenant_ai_level, set_tenant_ai_level
from utils.safe_redirect import safe_redirect_target
from utils.sanitizer import InputSanitizer

# Re-export shared helpers that tests patch via "routes.owner.*"
from .shared import _known_tables_map  # noqa: E402 — used by test_owner_routes patches

import logging
import os

logger = logging.getLogger(__name__)

owner_bp = Blueprint('owner', __name__, url_prefix='/owner')


@owner_bp.before_request
def _owner_ip_guard():
    from utils.security_helpers import enforce_owner_ip_if_needed
    enforce_owner_ip_if_needed()


# Import sub-modules so they register their routes on the shared owner_bp.
# Each sub-module is loaded here to ensure all @owner_bp.route decorators fire.
from . import shared          # noqa: E402 — shared helpers (loaded first)
from . import core            # noqa: E402 — dashboard, landing, config, cards
from . import tenants         # noqa: E402
from . import users           # noqa: E402
from . import backups         # noqa: E402
from . import database        # noqa: E402
from . import settings        # noqa: E402 — configurations, tax, currency, invoices, comms
from . import monitoring      # noqa: E402 — health, security, analytics, error audit
