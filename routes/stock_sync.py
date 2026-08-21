"""
Lean inbound stock-sync route for external POS systems.

Security:  X-API-Key + X-API-Secret headers via @api_key_required.
Business logic is delegated to StockSyncService; this module contains
HTTP-layer code only (validation, JSON response, status mapping).
"""

from flask import Blueprint, request

from extensions import csrf
from services.stock_sync_service import StockSyncService
from utils.api_response import error_response, success_response
from utils.decorators import api_key_required

stock_sync_bp = Blueprint("stock_sync", __name__, url_prefix="/api/v2/stock")


@stock_sync_bp.route("/sync", methods=["POST"])
@csrf.exempt
@api_key_required(scope="write")
def sync_stock():
    data = request.get_json(silent=True) or {}
    if not data:
        return error_response(message="Empty payload", status_code=400)

    try:
        result = StockSyncService.process_sync_payload(data)
    except ValueError as exc:
        return error_response(message=str(exc), status_code=422)
    except Exception:
        # Log the full error server-side; return generic message client-side
        import logging

        logging.getLogger(__name__).exception("Stock sync failed")
        return error_response(message="Sync processing failed", status_code=500)

    if result.get("cached"):
        return success_response(data=result, status_code=409)

    return success_response(data=result)


@stock_sync_bp.route("/sync/status/<int:batch_id>", methods=["GET"])
@csrf.exempt
@api_key_required(scope="read")
def sync_status(batch_id):
    status = StockSyncService.get_sync_status(batch_id)
    if not status:
        return error_response(message="Batch not found", status_code=404)
    return success_response(data=status)
