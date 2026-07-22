"""
Lean inbound stock-sync route for external POS systems.

Security:  X-API-Key + X-API-Secret headers via @api_key_required.
Business logic is delegated to StockSyncService; this module contains
HTTP-layer code only (validation, JSON response, status mapping).
"""

from flask import Blueprint, request, jsonify
from extensions import csrf
from utils.decorators import api_key_required
from services.stock_sync_service import StockSyncService

stock_sync_bp = Blueprint("stock_sync", __name__, url_prefix="/api/v2/stock")


@stock_sync_bp.route("/sync", methods=["POST"])
@csrf.exempt
@api_key_required(scope="write")
def sync_stock():
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({"ok": False, "error": "Empty payload"}), 400

    try:
        result = StockSyncService.process_sync_payload(data)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 422
    except Exception:
        # Log the full error server-side; return generic message client-side
        import logging

        logging.getLogger(__name__).exception("Stock sync failed")
        return jsonify({"ok": False, "error": "Sync processing failed"}), 500

    if result.get("cached"):
        return jsonify(result), 409

    return jsonify(result), 200


@stock_sync_bp.route("/sync/status/<int:batch_id>", methods=["GET"])
@csrf.exempt
@api_key_required(scope="read")
def sync_status(batch_id):
    status = StockSyncService.get_sync_status(batch_id)
    if not status:
        return jsonify({"ok": False, "error": "Batch not found"}), 404
    return jsonify({"ok": True, "data": status}), 200
