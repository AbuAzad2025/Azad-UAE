from flask import Blueprint
import logging

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
