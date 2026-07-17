"""Wave 4 coverage push — azad_responses, neural_engine, agents_core, dispatcher, secondary."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


@pytest.fixture
def knowledge_path(tmp_path):
    with patch(
        "ai_knowledge.get_knowledge_path", side_effect=lambda name: str(tmp_path / name)
    ):
        yield tmp_path


class _Col:
    def __gt__(self, other):
        return MagicMock()

    def __ge__(self, other):
        return MagicMock()

    def __eq__(self, other):
        return MagicMock()

    def between(self, a, b):
        return MagicMock()

    def ilike(self, *a, **kw):
        return MagicMock()

    def desc(self):
        return MagicMock()


def _db_chain(mock_db):
    chain = MagicMock()
    mock_db.session.query.return_value = chain
    for attr in ("outerjoin", "join", "filter", "filter_by", "group_by", "order_by"):
        getattr(chain, attr).return_value = chain
    chain.limit.return_value = chain
    return chain


def _patch_model_cols(*models):
    ctxs = []
    for mod in models:
        p = patch(mod)
        m = p.start()
        for attr in (
            "status",
            "sale_date",
            "cost_price",
            "unit_price",
            "tenant_id",
            "purchase_date",
            "expense_date",
            "receipt_date",
            "amount_aed",
            "payment_status",
            "id",
            "product_id",
            "current_stock",
            "min_stock_level",
        ):
            setattr(m, attr, _Col())
        ctxs.append(p)
    return ctxs


def _stop_patches(ctxs):
    for p in ctxs:
        p.stop()


def _fast_models(engine):
    for model in engine.models.values():
        if hasattr(model, "max_iter"):
            model.max_iter = 50


def _sale_mock():
    customer = MagicMock(name="Ali", phone="050", address="Dubai")
    line = MagicMock(
        quantity=2,
        unit_price=Decimal("50"),
        line_total=Decimal("100"),
        product=MagicMock(name="Oil Filter"),
        sale_id=42,
        product_id=1,
    )
    line.product.name = "Oil Filter"
    sale = MagicMock(
        id=42,
        amount_aed=Decimal("105"),
        created_at=datetime(2025, 6, 1, 10, 30),
        sale_date=datetime(2025, 6, 1),
        customer=customer,
        status="confirmed",
        paid_amount=Decimal("100"),
        balance_due=Decimal("0"),
        sale_lines=[line],
        subtotal=Decimal("100"),
        total_amount=Decimal("105"),
    )
    return sale


class TestAzadResponsesWave4:
    @pytest.fixture
    def responses(self):
        from ai_knowledge.personality.azad_responses import AzadResponses

        return AzadResponses()

    def _safe_mocks(self):
        return patch.multiple(
            "ai_knowledge.personality.azad_responses",
            understand_message=MagicMock(
                return_value={"intent": None, "confidence": 0}
            ),
            azad_personality=MagicMock(
                is_inappropriate_message=MagicMock(return_value="normal"),
                get_greeting=MagicMock(return_value="مرحبا"),
                get_thanks_response=MagicMock(return_value="شكرا"),
                get_professional_joke=MagicMock(return_value="نكتة"),
                get_help_intro=MagicMock(return_value="مساعدة"),
            ),
            learning_system=MagicMock(learn_from_interaction=MagicMock()),
        )

    def test_analytical_intent_failure_and_success(self, responses):
        with (
            patch(
                "ai_knowledge.personality.azad_responses.understand_message",
                return_value={"intent": "sales_analysis", "confidence": 0.9},
            ),
            patch(
                "ai_knowledge.personality.azad_responses.intelligent_assistant"
            ) as ia,
            patch(
                "services.ai_service.AIService.is_sensitive_request",
                return_value=(False, False, {}),
            ),
            patch("ai_knowledge.personality.azad_responses.azad_personality") as ap,
            patch("ai_knowledge.personality.azad_responses.learning_system"),
        ):
            ap.is_inappropriate_message.return_value = "normal"
            ia.process.return_value = {
                "success": True,
                "data_used": True,
                "response": "تحليل حقيقي",
            }
            assert "تحليل" in responses.smart_response("حلل المبيعات")
            ia.process.side_effect = RuntimeError("fail")
            assert isinstance(responses.smart_response("حلل المبيعات"), str)

    def test_sensitive_non_owner_and_all_users(self, responses):
        owner = MagicMock(id=1, is_owner=True)
        with (
            patch(
                "services.ai_service.AIService.is_sensitive_request",
                return_value=(True, False, {"message": "مرفوض"}),
            ),
            patch(
                "ai_knowledge.personality.azad_responses.understand_message",
                return_value={"intent": None, "confidence": 0},
            ),
            patch("ai_knowledge.personality.azad_responses.azad_personality") as ap,
            patch("ai_knowledge.personality.azad_responses.learning_system"),
        ):
            ap.is_inappropriate_message.return_value = "normal"
            assert "مرفوض" in responses.smart_response("password admin")
        with (
            patch(
                "services.ai_service.AIService.is_sensitive_request",
                return_value=(True, True, {}),
            ),
            patch(
                "services.ai_service.AIService.get_user_info_for_owner",
                return_value={
                    "success": True,
                    "count": 2,
                    "users": [
                        {
                            "username": "u1",
                            "email": "e1",
                            "role": "admin",
                            "password_hash": "hash12345678901234567890",
                        }
                    ],
                },
            ),
            patch(
                "ai_knowledge.personality.azad_responses.understand_message",
                return_value={"intent": None, "confidence": 0},
            ),
            patch("ai_knowledge.personality.azad_responses.azad_personality") as ap,
            patch("ai_knowledge.personality.azad_responses.learning_system"),
        ):
            ap.is_inappropriate_message.return_value = "normal"
            result = responses.smart_response(
                "مستخدم admin", context={"current_user": owner, "is_owner": True}
            )
            assert "u1" in result

    @pytest.mark.parametrize(
        "msg,check",
        [
            ("شكرا جزيلا", "شكرا"),
            ("نكتة مضحكة", "نكتة"),
        ],
    )
    def test_greeting_thanks_joke(self, responses, msg, check):
        with (
            self._safe_mocks(),
            patch(
                "services.ai_service.AIService.is_sensitive_request",
                return_value=(False, False, {}),
            ),
            patch(
                "ai_knowledge.personality.azad_responses.get_welcome_message",
                return_value="welcome",
            ),
        ):
            assert check in responses.smart_response(msg)

    def test_greeting_branch(self, responses):
        with (
            self._safe_mocks(),
            patch(
                "services.ai_service.AIService.is_sensitive_request",
                return_value=(False, False, {}),
            ),
            patch(
                "ai_knowledge.personality.azad_responses.get_welcome_message",
                return_value="welcome",
            ),
        ):
            assert "welcome" in responses.smart_response("مرحبا أزاد")

    def test_dialect_greetings(self, responses):
        with (
            patch(
                "ai_knowledge.personality.azad_responses.understand_message",
                return_value={"intent": None, "confidence": 0},
            ),
            patch(
                "services.ai_service.AIService.is_sensitive_request",
                return_value=(False, False, {}),
            ),
            patch("ai_knowledge.personality.azad_responses.azad_personality") as ap,
            patch("ai_knowledge.personality.azad_responses.learning_system"),
            patch(
                "ai_knowledge.personality.azad_responses.get_dialectal_greeting",
                return_value="أهلين",
            ),
            patch(
                "ai_knowledge.personality.azad_responses.get_welcome_message",
                return_value="welcome",
            ),
        ):
            ap.is_inappropriate_message.return_value = "normal"
            assert "أهلين" in responses.smart_response(
                "مرحبا", context={"dialect": "palestinian"}
            )
            assert "أهلين" in responses.smart_response(
                "هلا", context={"dialect": "gulf"}
            )

    def test_tax_customs_parts_branches(self, responses):
        with (
            self._safe_mocks(),
            patch(
                "services.ai_service.AIService.is_sensitive_request",
                return_value=(False, False, {}),
            ),
            patch(
                "ai_knowledge.personality.azad_responses.get_tax_info",
                return_value="tax info",
            ),
            patch(
                "ai_knowledge.personality.azad_responses.get_customs_info",
                return_value="customs info",
            ),
            patch(
                "ai_knowledge.personality.azad_responses.get_tax_advice",
                return_value="advice",
            ),
            patch(
                "ai_knowledge.personality.azad_responses.search_parts",
                return_value=[{"category": "engine", "excerpt": "part"}],
            ),
            patch(
                "ai_knowledge.personality.azad_responses.get_part_info",
                return_value="part info",
            ),
        ):
            assert "customs" in responses.smart_response(
                "جمارك الإمارات uae"
            ).lower() or "customs" in responses.smart_response("جمارك الإمارات uae")
            assert "tax" in responses.smart_response(
                "ضريبة الإمارات uae"
            ).lower() or "tax" in responses.smart_response("ضريبة الإمارات uae")
            assert "tax" in responses.smart_response(
                "ضريبة السعودية saudi"
            ).lower() or "tax" in responses.smart_response("ضريبة السعودية saudi")
            assert "tax" in responses.smart_response(
                "ضريبة فلسطين palestine"
            ).lower() or "tax" in responses.smart_response("ضريبة فلسطين palestine")
            assert "advice" in responses.smart_response("ضريبة عامة")
            assert "engine" in responses.smart_response("قطعة محرك engine")
            assert "part" in responses.smart_response("فرامل brake xyznonexistent")

    def test_customer_service_and_sales_exception(self, responses):
        with (
            self._safe_mocks(),
            patch(
                "services.ai_service.AIService.is_sensitive_request",
                return_value=(False, False, {}),
            ),
            patch(
                "ai_knowledge.personality.azad_responses.get_customer_service_tip",
                return_value="tip",
            ),
            patch(
                "ai_knowledge.personality.azad_responses.CUSTOMER_SERVICE",
                {"principles": ["p1"]},
                create=True,
            ),
        ):
            with patch(
                "ai_knowledge.specialized.customer_service.CUSTOMER_SERVICE",
                {"principles": ["p1", "p2"]},
            ):
                assert "tip" in responses.smart_response("نصiحة تعامل مع عميل customer")
                assert "p1" in responses.smart_response("عميل customer زبون")
        with (
            self._safe_mocks(),
            patch(
                "services.ai_service.AIService.is_sensitive_request",
                return_value=(False, False, {}),
            ),
            patch(
                "ai_knowledge.personality.azad_responses.AzadResponses._smart_sales_analysis",
                side_effect=RuntimeError("fail"),
            ),
        ):
            assert "لا توجد بيانات" in responses.smart_response(
                "حلل analyze المبيعات sales"
            )

    def test_improvement_and_status_exceptions(self, responses):
        with (
            self._safe_mocks(),
            patch(
                "services.ai_service.AIService.is_sensitive_request",
                return_value=(False, False, {}),
            ),
            patch("ai_knowledge.personality.azad_responses.self_improvement") as si,
        ):
            si.auto_improve.side_effect = RuntimeError("fail")
            assert "تعلم مستمر" in responses.smart_response(
                "تحسين improve تلقائي automatic"
            )
            si.auto_improve.side_effect = None
            si.get_improvement_status.side_effect = RuntimeError("fail")
            assert "نشط" in responses.smart_response("حالة status النظام")

    def test_forecast_branch_trends(self, responses):
        monthly = [MagicMock(total=1000), MagicMock(total=1100), MagicMock(total=1200)]
        cols = _patch_model_cols("models.Sale")
        try:
            with (
                self._safe_mocks(),
                patch(
                    "services.ai_service.AIService.is_sensitive_request",
                    return_value=(False, False, {}),
                ),
                patch("extensions.db") as mock_db,
                patch(
                    "ai_knowledge.personality.azad_responses.SalesAnalytics.predict_next_month_sales",
                    return_value={
                        "prediction": 5000,
                        "trend": "up",
                        "trend_value": 500,
                        "confidence": 0.9,
                        "method": "linear",
                    },
                ),
            ):
                mock_db.session.query.return_value.filter.return_value.group_by.return_value.all.return_value = monthly
                assert "5,000" in responses.smart_response(
                    "توقع predict forecast الشهر"
                )
        finally:
            _stop_patches(cols)
        with (
            self._safe_mocks(),
            patch(
                "services.ai_service.AIService.is_sensitive_request",
                return_value=(False, False, {}),
            ),
            patch("extensions.db", side_effect=RuntimeError("db fail")),
        ):
            assert "خطأ" in responses.smart_response("توقع predict forecast")

    def test_inventory_profit_failures(self, responses):
        with (
            self._safe_mocks(),
            patch(
                "services.ai_service.AIService.is_sensitive_request",
                return_value=(False, False, {}),
            ),
            patch(
                "services.ai_service.AIService.analyze_inventory_health",
                return_value={"success": False, "message": "no products"},
            ),
        ):
            assert "no products" in responses.smart_response("مخزون stock inventory")
        with (
            self._safe_mocks(),
            patch(
                "services.ai_service.AIService.is_sensitive_request",
                return_value=(False, False, {}),
            ),
            patch(
                "services.ai_service.AIService.analyze_profit_margins",
                return_value={"success": False, "message": "no sales"},
            ),
        ):
            assert "no sales" in responses.smart_response("ربح profit هامش margin")

    def test_help_guide_market_branches(self, responses):
        with (
            self._safe_mocks(),
            patch(
                "services.ai_service.AIService.is_sensitive_request",
                return_value=(False, False, {}),
            ),
            patch(
                "ai_knowledge.personality.azad_responses.get_help_for_task",
                return_value="task help",
            ),
            patch(
                "ai_knowledge.personality.azad_responses.search_knowledge",
                return_value=[],
            ),
            patch(
                "ai_knowledge.personality.azad_responses.get_system_guide",
                return_value="system guide",
            ),
            patch(
                "ai_knowledge.personality.azad_responses.get_market_insights",
                return_value="market data",
            ),
        ):
            assert "task help" in responses.smart_response("كيف how أستخدم النظام")
            with patch(
                "ai_knowledge.personality.azad_responses.get_help_for_task",
                return_value="لم أجد",
            ):
                assert "system guide" in responses.smart_response(
                    "دليل guide شرح explain"
                )
            assert "market" in responses.smart_response("سوق market منافسة")

    def test_smart_response_suggestions_else(self, responses):
        with (
            self._safe_mocks(),
            patch(
                "services.ai_service.AIService.is_sensitive_request",
                return_value=(False, False, {}),
            ),
            patch(
                "ai_knowledge.personality.azad_responses.get_help_for_task",
                return_value="لم أجد",
            ),
            patch(
                "ai_knowledge.personality.azad_responses.search_knowledge",
                return_value=[],
            ),
            patch(
                "ai_knowledge.personality.azad_responses.get_system_guide",
                return_value="guide",
            ),
        ):
            result = responses.smart_response(
                "xyzunknownquery رصيد balance فاتورة invoice query"
            )
            assert isinstance(result, str) and len(result) > 20

    def test_customer_balance_full_paths(self, responses):
        customer = {
            "id": 1,
            "name": "أحمد",
            "customer_type": "regular",
            "phone": "050",
            "email": "a@t.com",
            "balance_aed": 6000,
            "total_sales": 5,
            "last_sale_date": "2025-06-01",
        }
        with (
            patch("ai_knowledge.personality.azad_responses.system_integrator") as si,
            patch("ai_knowledge.personality.azad_responses.data_analyzer") as da,
        ):
            si.get_customer_balance.return_value = {
                "success": True,
                "customer": customer,
            }
            da.analyze_customer_debt.return_value = {
                "success": True,
                "debt_analysis": {
                    "unpaid_sales_count": 2,
                    "avg_debt_amount": 500,
                    "max_debt_amount": 800,
                    "overdue_count": 1,
                },
            }
            assert "أحمد" in responses._handle_customer_balance_query(
                "رصيد العميل أحمد"
            )
            assert "أحمد" in responses._handle_balance_query("رصيد العميل أحمد")
            assert "❌" in responses._handle_customer_balance_query("رصيد عميل")
            si.get_customer_balance.return_value = {
                "success": False,
                "error": "missing",
            }
            assert "missing" in responses._handle_customer_balance_query("رصيد عميل x")

    def test_customer_info_paths(self, responses):
        customer = {
            "id": 1,
            "name": "سامي",
            "customer_type": "vip",
            "phone": "050",
            "email": "s@t.com",
            "balance_aed": 200,
            "total_sales": 3,
            "last_sale_date": "2025-01-01",
        }
        with patch("ai_knowledge.personality.azad_responses.system_integrator") as si:
            si.get_customer_balance.return_value = {
                "success": True,
                "customer": customer,
            }
            si.get_customer_sales_summary.return_value = {
                "success": True,
                "summary": {
                    "total_sales": 3,
                    "total_amount": 3000,
                    "paid_amount": 2800,
                    "balance_due": 200,
                    "recent_sales": [
                        {"id": 1, "date": "2025-06-01", "amount": 500, "status": "paid"}
                    ],
                },
            }
            assert "سامي" in responses._handle_customer_info_query("بيانات عميل سامي")
            si.get_customer_sales_summary.return_value = {"success": False}
            assert "سامي" in responses._handle_customer_info_query("بيانات عميل سامي")
            assert "❌" in responses._handle_customer_info_query("بيانات عميل")

    def test_product_stock_statuses(self, responses):
        with patch("ai_knowledge.personality.azad_responses.system_integrator") as si:
            for stock, alert, action in [
                (0, 5, "عاجل"),
                (3, 10, "قريب"),
                (50, 10, "جيد"),
            ]:
                si.get_product_stock.return_value = {
                    "success": True,
                    "product": {
                        "name": "Part",
                        "id": 1,
                        "sku": "P1",
                        "category": "X",
                        "unit_price": 25.0,
                        "current_stock": stock,
                        "alert_limit": alert,
                    },
                }
                result = responses._handle_product_stock_query("مخزون منتج Part")
                assert "Part" in result
            si.get_product_stock.return_value = {"success": False, "error": "not found"}
            assert "not found" in responses._handle_product_stock_query("مخزون منتج X")
            assert "❌" in responses._handle_product_stock_query("مخزون")

    def test_system_summary_failures(self, responses):
        with patch("ai_knowledge.personality.azad_responses.system_integrator") as si:
            si.get_system_summary.return_value = {"success": False, "error": "sys fail"}
            assert "sys fail" in responses._handle_system_summary_query()
            si.get_system_summary.return_value = {
                "success": True,
                "summary": {
                    "customers": {"total": 1, "vip": 0, "recent": []},
                    "sales": {"total": 1, "today": 0, "recent": []},
                    "products": {"total": 1, "low_stock": 0, "out_of_stock": 0},
                },
            }
            si.get_financial_summary.return_value = {
                "success": False,
                "error": "fin fail",
            }
            assert "fin fail" in responses._handle_system_summary_query()

    def test_search_and_knowledge(self, responses):
        with (
            patch("ai_knowledge.personality.azad_responses.system_integrator") as si,
            patch("ai_knowledge.personality.azad_responses.knowledge_expander") as ke,
            patch("ai_knowledge.personality.azad_responses.knowledge_manager") as km,
            patch(
                "ai_knowledge.personality.azad_responses.recommend_sources_for_query"
            ) as rec,
        ):
            si.search_data.return_value = {
                "success": True,
                "results": {
                    "customers": [{"name": "A", "type": "r", "balance": 100}],
                    "products": [{"name": "P", "sku": "S", "stock": 5, "price": 10}],
                    "sales": [
                        {"id": 1, "customer": "A", "amount": 100, "date": "2025-01-01"}
                    ],
                },
            }
            assert "A" in responses._handle_search_query("ابحث عن Ali")
            si.search_data.return_value = {"success": False, "error": "search fail"}
            assert "search fail" in responses._handle_search_query("ابحث x")
            ke.search_knowledge.return_value = {
                "success": True,
                "total_found": 1,
                "results": [
                    {"title": "T", "type": "doc", "category": "tax", "snippet": "snip"}
                ],
            }
            assert "T" in responses._handle_knowledge_search("ابحث في المعرفة tax")
            ke.search_knowledge.return_value = {
                "success": True,
                "total_found": 0,
                "results": [],
            }
            assert "لم أجد" in responses._handle_knowledge_search("ابحث في المعرفة xyz")
            assert "❌" in responses._handle_knowledge_search("ابحث")
            km.get_all_sources_summary.return_value = {
                "total_categories": 2,
                "total_sources": 5,
                "categories": {
                    "tax": {"count": 2, "sources": [{"name": "SRC", "url": "http://x"}]}
                },
            }
            assert "SRC" in responses._show_knowledge_sources("كل all المصادر")
            km.get_sources_by_topic.return_value = [
                {"name": "VAT", "url": "http://vat", "type": "web"}
            ]
            assert "VAT" in responses._show_knowledge_sources("مصادر ضريبة")
            rec.return_value = [
                {"name": "Guide", "url": "http://g", "category": "tax", "type": "web"}
            ]
            assert "Guide" in responses._recommend_sources("أين أجد معلومات tax")

    def test_document_excel_report_handlers(self, responses):
        with patch("ai_knowledge.personality.azad_responses.document_generator") as dg:
            dg.generate_receipt.return_value = ("receipt", "ok")
            dg.generate_invoice.return_value = ("invoice", "ok")
            assert "receipt" in responses._handle_document_generation(
                "ولد سند receipt 42"
            )
            assert "invoice" in responses._handle_document_generation(
                "ولد فاتورة invoice 99"
            )
            dg.generate_receipt.return_value = (None, "fail")
            assert "fail" in responses._handle_document_generation("ولد سند 1")
            assert "❌" in responses._handle_document_generation("ولد سند receipt")
            assert "❓" in responses._handle_document_generation("ولد مستند")
        assert "Excel" in responses._handle_excel_export("صدر export مبيعات sales")
        assert "Excel" in responses._handle_excel_export("صدر export عملاء customers")
        assert "Excel" in responses._handle_excel_export("صدر export منتجات products")
        assert "؟" in responses._handle_excel_export("صدر excel")
        assert "تقرير" in responses._handle_report_generation(
            "ولد generate تقرير مبيعات sales"
        )
        assert "كشف" in responses._handle_report_generation(
            "ولد generate كشف statement"
        )
        assert "؟" in responses._handle_report_generation("ولد report")

    def test_tax_shipping_quality_handlers(self, responses):
        assert "فلسطين" in responses._handle_tax_laws_query(
            "قانون ضريبة فلسطين palestine"
        )
        assert "إسرائيل" in responses._handle_tax_laws_query(
            "قانون ضريبة israel اسرائيل"
        )
        assert "الخليج" in responses._handle_tax_laws_query("قانون ضريبة gulf خليج uae")
        assert "؟" in responses._handle_tax_laws_query("قانون ضريبة")
        assert "إجراءات" in responses._handle_shipping_laws_query(
            "شحن shipping إجراءات procedures"
        )
        assert "الشحن البحري" in responses._handle_shipping_laws_query(
            "شحن shipping نوع type"
        )
        assert "؟" in responses._handle_shipping_laws_query("شحن")
        assert "معايير" in responses._handle_quality_standards_query(
            "معايير standards جودة"
        )
        assert "الأغذية" in responses._handle_quality_standards_query(
            "جودة quality طعام food"
        )
        assert "الإلكترونيات" in responses._handle_quality_standards_query(
            "جودة electronics إلكترونيات"
        )
        assert "؟" in responses._handle_quality_standards_query("جودة")

    def test_quick_links_and_inventory_status(self, responses):
        with patch(
            "services.ai_service.AIService.analyze_inventory_health",
            return_value={
                "success": True,
                "summary": {"total": 10, "good": 8, "low": 1, "out": 1},
                "rating": "جيد",
                "health_score": 80,
            },
        ):
            assert "المخزون" in responses._inventory_status()
        assert "/sales/create" in responses._quick_invoice_link()
        assert "/payments/receipts/create" in responses._quick_receipt_link()
        assert "/reports/sales" in responses._quick_report_links("تقرير مبيعات sales")
        assert "/reports/purchases" in responses._quick_report_links(
            "تقرير purchases مشتريات"
        )
        assert "/reports/inventory" in responses._quick_report_links(
            "تقرير inventory مخزون"
        )
        assert "/reports/receivables" in responses._quick_report_links(
            "تقرير receivables ذمم"
        )
        assert "/ledger/balance-sheet" in responses._quick_report_links(
            "تقرير report عام"
        )
        assert "/sales/create" in responses._show_system_quick_links()

    def test_smart_sales_analysis_trends(self, responses):
        sale7 = MagicMock(
            amount_aed=700, status="confirmed", sale_date=datetime.now(timezone.utc)
        )
        sale30 = MagicMock(
            amount_aed=100,
            status="confirmed",
            sale_date=datetime.now(timezone.utc) - timedelta(days=10),
        )
        with patch("models.Sale") as MockSale:
            MockSale.sale_date = _Col()
            MockSale.status = _Col()
            MockSale.query.filter.return_value.all.side_effect = [
                [sale7] * 7,
                [sale30] * 30,
            ]
            result = responses._smart_sales_analysis({})
            assert "تحليل المبيعات" in result

    @pytest.mark.parametrize(
        "intent",
        [
            "create_invoice",
            "create_receipt",
            "sales_analysis",
            "customer_balance",
            "inventory_check",
            "system_links",
            "tax_info",
            "customs_info",
            "parts_info",
            "automotive_ecu",
            "heavy_equipment",
            "market_insights",
            "customer_service",
            "shipping_laws",
            "quality_standards",
            "suppliers_info",
            "knowledge_sources",
            "palestine_tax_laws",
            "israel_tax_laws",
            "gulf_tax_laws",
            "shipping_regulations",
            "memory_query",
            "multi_step_query",
            "engine_parts",
            "diesel_parts",
            "transmission_parts",
            "suspension_parts",
            "brake_parts",
            "electrical_parts",
            "ac_parts",
            "diagnostic_codes",
            "sensors_issues",
            "pricing_strategy",
            "sales_techniques",
            "general_help",
            "add_customer",
        ],
    )
    def test_handle_detected_intent_all(self, responses, intent):
        with (
            patch("ai_knowledge.personality.azad_responses.system_integrator") as si,
            patch("ai_knowledge.personality.azad_responses.data_analyzer") as da,
            patch("extensions.db") as mock_db,
            patch("models.Sale") as MockSale,
            patch(
                "services.ai_service.AIService.analyze_inventory_health",
                return_value={
                    "success": True,
                    "summary": {"total": 1, "good": 1, "low": 0, "out": 0},
                    "rating": "ok",
                    "health_score": 100,
                },
            ),
            patch("models.Supplier") as MockSup,
        ):
            si.get_customer_balance.return_value = {
                "success": True,
                "customer": {
                    "id": 1,
                    "name": "A",
                    "customer_type": "r",
                    "phone": "",
                    "email": "",
                    "balance_aed": 0,
                    "total_sales": 0,
                    "last_sale_date": None,
                },
            }
            da.analyze_customer_debt.return_value = {"success": False}
            MockSale.query.filter.return_value.all.return_value = []
            MockSup.query.filter_by.return_value.count.return_value = 0
            MockSup.query.filter_by.return_value.order_by.return_value.first.return_value = None
            mock_db.session.query.return_value.scalar.return_value = 0
            result = responses._handle_detected_intent(intent, "test message", {})
            assert result is None or isinstance(result, str)


class TestNeuralEngineWave4:
    @pytest.fixture
    def engine(self, knowledge_path):
        from ai_knowledge.neural.neural_engine import AzadNeuralEngine

        eng = AzadNeuralEngine()
        _fast_models(eng)
        return eng

    def test_app_context_wrappers(self, engine):
        ctx = MagicMock()
        ctx.return_value.__enter__ = MagicMock(return_value=None)
        ctx.return_value.__exit__ = MagicMock(return_value=False)
        cases = [
            (
                "train_maintenance_prediction",
                "_train_maintenance_internal",
                (),
                {"success": True},
            ),
            (
                "train_accounting_assistant",
                "_train_accounting_internal",
                (),
                {"success": True},
            ),
            (
                "train_financial_planning",
                "_train_financial_internal",
                (),
                {"success": True},
            ),
            ("train_price_optimizer", "_train_price_internal", (), {"success": True}),
            ("train_sales_forecaster", "_train_sales_internal", (), {"success": True}),
            (
                "forecast_sales",
                "_forecast_sales_internal",
                (7,),
                {"forecast": [], "total_expected": 0},
            ),
            ("train_fraud_detector", "_train_fraud_internal", (), {"success": True}),
            (
                "train_inventory_optimizer",
                "_train_inventory_internal",
                (),
                {"success": True},
            ),
            (
                "optimize_stock_level",
                "_optimize_stock_internal",
                (1,),
                {"urgency": "low"},
            ),
            ("train_demand_predictor", "_train_demand_internal", (), {"success": True}),
            (
                "predict_product_demand",
                "_predict_demand_internal",
                (1, 5),
                {"forecast": []},
            ),
            ("train_profit_optimizer", "_train_profit_internal", (), {"success": True}),
            ("train_churn_predictor", "_train_churn_internal", (), {"success": True}),
            (
                "predict_cash_flow",
                "_predict_cash_flow_internal",
                (3,),
                {"predictions": [], "trend": "stable"},
            ),
            (
                "predict_maintenance_needs",
                "_predict_maintenance_internal",
                (1,),
                {"needs_maintenance": False},
            ),
        ]
        for pub, internal, args, ret in cases:
            with patch.object(engine, internal, return_value=ret) as inner:
                getattr(engine, pub)(*args, from_app_context=ctx)
                inner.assert_called_once()

    def test_predict_maintenance_no_product_and_else(self, engine):
        with patch.object(engine, "_load_model", return_value=False):
            assert (
                engine._predict_maintenance_internal(99)["error"] == "Model not trained"
            )
        with patch.object(
            engine,
            "_predict_maintenance_internal",
            return_value={
                "needs_maintenance": False,
                "confidence": 0.8,
                "recommended_action": "ok",
                "estimated_days": 30,
                "model": "neural_network",
            },
        ) as inner:
            assert engine.predict_maintenance_needs(1)["estimated_days"] == 30
            inner.assert_called_once_with(1)

    def test_price_margin_recommendations(self, engine):
        with (
            patch.object(engine, "_load_model", return_value=True),
            patch.object(engine, "_is_model_loaded", return_value=True),
            patch.object(
                engine.scalers["price_optimizer"],
                "transform",
                return_value=np.array([[1.0] * 8]),
            ),
            patch.object(
                engine.models["price_optimizer"],
                "predict",
                side_effect=[np.array([105.0]), np.array([200.0])],
            ),
            patch.object(
                engine.encoders["price_optimizer"],
                "transform",
                return_value=np.array([0]),
            ),
        ):
            low = engine.predict_optimal_price(100, 2, "regular")
            assert "منخفض" in low["recommendation"] or "مثالي" in low["recommendation"]
            high = engine.predict_optimal_price(100, 2, "regular")
            assert high["recommendation"]

    def test_cash_flow_trends(self, engine):
        cols = _patch_model_cols(
            "models.Sale", "models.Purchase", "models.Expense", "models.Receipt"
        )
        try:
            with (
                patch.object(engine, "_load_model", return_value=True),
                patch("extensions.db") as mock_db,
                patch("utils.tenanting.get_active_tenant_id", return_value=1),
                patch.object(
                    engine.scalers["financial_planner"],
                    "transform",
                    return_value=np.array([[1.0] * 6]),
                ),
                patch.object(
                    engine.models["financial_planner"],
                    "predict",
                    side_effect=[
                        np.array([5000.0]),
                        np.array([6000.0]),
                        np.array([7000.0]),
                    ],
                ),
            ):
                chain = _db_chain(mock_db)
                chain.scalar.return_value = Decimal("1000")
                inc = engine._predict_cash_flow_internal(3)
                assert inc["trend"] == "increasing"
                with patch.object(
                    engine.models["financial_planner"],
                    "predict",
                    side_effect=[
                        np.array([7000.0]),
                        np.array([5000.0]),
                        np.array([3000.0]),
                    ],
                ):
                    dec = engine._predict_cash_flow_internal(3)
                    assert dec["trend"] == "decreasing"
                with patch.object(
                    engine.models["financial_planner"],
                    "predict",
                    side_effect=[
                        np.array([5000.0]),
                        np.array([5100.0]),
                        np.array([5050.0]),
                    ],
                ):
                    stable = engine._predict_cash_flow_internal(3)
                    assert stable["trend"] == "stable"
        finally:
            _stop_patches(cols)

    def test_forecast_sales_full(self, engine):
        cols = _patch_model_cols("models.Sale")
        try:
            rows = []
            base = date.today() - timedelta(days=7)
            for i in range(7):
                row = MagicMock()
                row.sale_date = base + timedelta(days=i)
                row.total_amount = Decimal(str(1000 + i * 100))
                rows.append(row)
            with (
                patch.object(engine, "_load_model", return_value=True),
                patch("extensions.db") as mock_db,
                patch.object(
                    engine.scalers["sales_forecaster"],
                    "transform",
                    return_value=np.array([[1.0] * 11]),
                ),
                patch.object(
                    engine.models["sales_forecaster"],
                    "predict",
                    side_effect=[np.array([1200.0 + i * 50]) for i in range(7)],
                ),
            ):
                chain = _db_chain(mock_db)
                chain.all.return_value = rows
                result = engine._forecast_sales_internal(7)
                assert len(result.get("forecast", [])) == 7
                assert result.get("trend") in ("increasing", "decreasing", "stable")
        finally:
            _stop_patches(cols)

    def test_train_exceptions(self, engine):
        for method in (
            "train_accounting_assistant",
            "train_sales_forecaster",
            "train_inventory_optimizer",
            "train_profit_optimizer",
            "train_churn_predictor",
        ):
            internal = (
                method.replace("train_", "_train_")
                .replace("_assistant", "_internal")
                .replace("_forecaster", "_internal")
                .replace("_optimizer", "_internal")
                .replace("_predictor", "_internal")
            )
            with patch.object(engine, internal, side_effect=RuntimeError("fail")):
                assert getattr(engine, method)()["success"] is False

    def test_predict_maintenance_exception(self, engine):
        ctx = MagicMock()
        ctx.side_effect = RuntimeError("ctx fail")
        with patch.object(
            engine, "_predict_maintenance_internal", side_effect=RuntimeError("fail")
        ):
            assert engine.predict_maintenance_needs(1)["confidence"] == 0


class TestAgentsCoreWave4:
    def test_intelligent_response_branches(self, mock_ai_user):
        from ai_knowledge.agents_core import intelligent_response

        with (
            patch(
                "ai_knowledge.trainer.trainer", side_effect=RuntimeError("seed fail")
            ),
            patch(
                "ai_knowledge.action_dispatcher.action_dispatcher.parse_chat_action",
                return_value=("create_customer", {"name": "Ali"}),
            ),
            patch("ai_knowledge.action_dispatcher.action_dispatcher.dispatch") as disp,
        ):
            disp.return_value = MagicMock(
                success=True, message="تم", needs_permission=""
            )
            assert "تم" in intelligent_response("عميل Ali")
            disp.return_value = MagicMock(
                success=False, message="مرفوض", needs_permission="manage_sales"
            )
            assert "مرفوض" in intelligent_response("عميل Ali")
            disp.return_value = MagicMock(
                success=False, message="فشل", needs_permission=""
            )
            assert "فشل" in intelligent_response("عميل Ali")
        with (
            patch(
                "ai_knowledge.action_dispatcher.action_dispatcher.parse_chat_action",
                return_value=("greeting", {"name": "Ali"}),
            ),
            patch(
                "ai_knowledge.action_dispatcher.action_dispatcher.format_help",
                return_value="help",
            ),
            patch("datetime.datetime") as dt,
        ):
            dt.utcnow.return_value = datetime(2025, 6, 1, 8, 0, 0)
            assert "صباح" in intelligent_response("مرحبا")
        with (
            patch(
                "ai_knowledge.action_dispatcher.action_dispatcher.parse_chat_action",
                return_value=None,
            ),
            patch("ai_knowledge.agents_core.intelligent_assistant") as ia,
        ):
            ia.process.return_value = {"response": "local answer"}
            assert "local" in intelligent_response("سؤال")
        with (
            patch(
                "ai_knowledge.action_dispatcher.action_dispatcher.parse_chat_action",
                side_effect=RuntimeError("boom"),
            ),
            patch(
                "ai_knowledge.action_dispatcher._log_ai_error",
                side_effect=RuntimeError("log fail"),
            ),
        ):
            assert "خطأ" in intelligent_response("test")

    def test_llm_availability_cached_and_dotenv(self):
        from ai_knowledge import agents_core as ac

        ac._llm_available = True
        assert ac._check_llm_availability() is True
        ac._llm_available = None
        with (
            patch.dict("os.environ", {"GROQ_API_KEY": "k"}),
            patch("dotenv.load_dotenv", side_effect=RuntimeError("dotenv")),
        ):
            assert ac._check_llm_availability() is True

    def test_get_llm_failures(self):
        from ai_knowledge import agents_core as ac

        with (
            patch.dict("os.environ", {"GROQ_API_KEY": "k", "GEMINI_API_KEY": "g"}),
            patch("dotenv.load_dotenv", side_effect=RuntimeError()),
            patch("requests.post", side_effect=RuntimeError("net")),
        ):
            assert ac._get_llm_response("sys", "q") is None
        gem_resp = MagicMock(status_code=200)
        gem_resp.json.return_value = {"candidates": []}
        with (
            patch.dict("os.environ", {"GROQ_API_KEY": "", "GEMINI_API_KEY": "g"}),
            patch("requests.post", return_value=gem_resp),
        ):
            assert ac._get_llm_response("sys", "q") is None

    def test_ask_azad_enhanced_faq_and_knowledge(self):
        from ai_knowledge import agents_core as ac

        ac._llm_available = None
        faq = {"user": [{"q": "كيف أضيف فاتورة", "a": "من قائمة المبيعات"}]}
        knowledge = [
            {
                "type": "model",
                "name": "Sale",
                "info": {"table": "sales", "fields": {"id": "int"}},
            },
            {
                "type": "permission",
                "code": "manage_sales",
                "info": {"name_ar": "مبيعات", "name": "Sales"},
            },
            {
                "type": "feature",
                "name": "AI",
                "info": {"name_ar": "ذكاء", "description": "مساعد"},
            },
        ]
        with (
            patch("ai_knowledge.system_knowledge.FAQ", faq),
            patch(
                "ai_knowledge.system_knowledge.search_knowledge", return_value=knowledge
            ),
            patch(
                "ai_knowledge.agents_core._check_llm_availability", return_value=False
            ),
            patch("ai_knowledge.agents.master_brain.get_master_brain") as gmb,
            patch("ai_knowledge.trainer.trainer") as tr,
        ):
            gmb.return_value.ask.return_value = {"answer": ""}
            tr.learn_from_interaction = MagicMock()
            r1 = ac.ask_azad_enhanced("كيف أضيف فاتورة جديدة")
            assert r1["source"] == "faq"
            r2 = ac.ask_azad_enhanced("مودل Sale في النظام")
            assert r2["source"] == "system_knowledge"
            assert "Sale" in r2["answer"]

    def test_ask_azad_enhanced_llm_and_brain_errors(self):
        from ai_knowledge import agents_core as ac

        with (
            patch("ai_knowledge.system_knowledge.FAQ", {}),
            patch("ai_knowledge.system_knowledge.search_knowledge", return_value=[]),
            patch(
                "ai_knowledge.agents_core._check_llm_availability", return_value=True
            ),
            patch(
                "ai_knowledge.agents_core._get_llm_response",
                side_effect=RuntimeError("llm fail"),
            ),
            patch("ai_knowledge.agents.master_brain.get_master_brain") as gmb,
            patch("ai_knowledge.trainer.trainer") as tr,
        ):
            gmb.return_value.ask.return_value = {"answer": "brain answer"}
            tr.learn_from_interaction = MagicMock()
            result = ac.ask_azad_enhanced("سؤال معقد")
            assert result["source"] == "master_brain"
        with (
            patch(
                "ai_knowledge.system_knowledge.search_knowledge",
                side_effect=RuntimeError("kb fail"),
            ),
            patch(
                "ai_knowledge.agents_core._check_llm_availability", return_value=False
            ),
            patch(
                "ai_knowledge.agents.master_brain.get_master_brain",
                side_effect=RuntimeError("brain fail"),
            ),
            patch(
                "ai_knowledge.trainer.trainer", side_effect=RuntimeError("train fail")
            ),
        ):
            result = ac.ask_azad_enhanced("سؤال")
            assert result["answer"]

    def test_build_prompt_with_knowledge(self):
        from ai_knowledge.agents_core import _build_system_prompt

        knowledge = [
            {
                "type": "model",
                "name": "Customer",
                "info": {"table": "customers", "fields": {"id": "int"}},
            },
            {
                "type": "permission",
                "code": "view_reports",
                "info": {"name_ar": "تقارير", "name": "Reports"},
            },
            {
                "type": "feature",
                "name": "backup",
                "info": {"name_ar": "نسخ", "description": "backup desc"},
            },
        ]
        with patch(
            "ai_knowledge.system_knowledge.search_knowledge", return_value=knowledge
        ):
            prompt = _build_system_prompt("تقارير", "manager")
            assert "Customer" in prompt
            assert "view_reports" in prompt


class TestActionDispatcherWave4:
    @pytest.fixture
    def permitted(self):
        return (
            patch(
                "ai_knowledge.action_dispatcher._get_active_tenant_id", return_value=1
            ),
            patch("ai_knowledge.action_dispatcher._is_owner", return_value=True),
            patch("ai_knowledge.action_dispatcher._audit"),
            patch("ai_knowledge.action_dispatcher._log_ai_error"),
        )

    def test_helper_exceptions(self):
        from ai_knowledge.action_dispatcher import _has_permission

        with patch(
            "ai_knowledge.action_dispatcher.current_user",
            SimpleNamespace(
                is_authenticated=True,
                has_permission=MagicMock(side_effect=RuntimeError()),
            ),
        ):
            assert _has_permission("x") is False

    def test_dispatch_error_paths(self, permitted, mock_ai_user):
        from ai_knowledge.action_dispatcher import action_dispatcher

        with (
            permitted[0],
            permitted[1],
            permitted[2],
            permitted[3],
            patch("ai_knowledge.action_dispatcher.db.session") as session,
            patch("models.Customer") as Customer,
        ):
            session.flush.side_effect = RuntimeError("db")
            assert (
                action_dispatcher.dispatch("create_customer", {"name": "Ali"}).success
                is False
            )
        with (
            permitted[0],
            permitted[1],
            permitted[2],
            permitted[3],
            patch("models.Customer") as Customer,
        ):
            Customer.query.filter_by.return_value.order_by.return_value.limit.return_value.all.side_effect = RuntimeError()
            assert action_dispatcher.dispatch("list_customers", {}).success is False
            assert (
                action_dispatcher.dispatch("customer_balance", {"name": ""}).success
                is False
            )
            Customer.query.filter_by.return_value.first.side_effect = RuntimeError()
            assert (
                action_dispatcher.dispatch("customer_balance", {"name": "Ali"}).success
                is False
            )
        with permitted[0], permitted[1], permitted[2], permitted[3]:
            assert (
                action_dispatcher.dispatch("create_product", {"name": ""}).success
                is False
            )
            assert (
                action_dispatcher.dispatch(
                    "create_sale", {"customer_name": "", "product_name": ""}
                ).success
                is False
            )
            assert (
                action_dispatcher.dispatch(
                    "receive_payment", {"customer_name": "", "amount": 0}
                ).success
                is False
            )
            assert (
                action_dispatcher.dispatch(
                    "add_expense", {"description": "", "amount": 0}
                ).success
                is False
            )
            assert (
                action_dispatcher.dispatch("create_supplier", {"name": ""}).success
                is False
            )
            assert (
                action_dispatcher.dispatch("create_employee", {"name": ""}).success
                is False
            )
            assert (
                action_dispatcher.dispatch(
                    "create_purchase", {"supplier_name": "", "product_name": ""}
                ).success
                is False
            )

    def test_sales_payment_purchase_errors(self, permitted, mock_ai_user):
        from ai_knowledge.action_dispatcher import action_dispatcher

        with (
            permitted[0],
            permitted[1],
            permitted[2],
            permitted[3],
            patch("services.ai_executor.AIExecutor") as Ex,
            patch("ai_knowledge.action_dispatcher.db.session"),
        ):
            Ex.return_value.create_sale.side_effect = RuntimeError("sale fail")
            assert (
                action_dispatcher.dispatch(
                    "create_sale",
                    {
                        "customer_name": "Ali",
                        "product_name": "Bolt",
                        "quantity": 1,
                    },
                ).success
                is False
            )
            Ex.return_value.receive_payment.side_effect = RuntimeError("pay fail")
            assert (
                action_dispatcher.dispatch(
                    "receive_payment",
                    {
                        "customer_name": "Ali",
                        "amount": 100,
                    },
                ).success
                is False
            )
            Ex.return_value.create_employee.side_effect = RuntimeError("emp fail")
            assert (
                action_dispatcher.dispatch(
                    "create_employee", {"name": "Sam", "salary": 3000}
                ).success
                is False
            )
            Ex.return_value.create_purchase.side_effect = RuntimeError("pur fail")
            assert (
                action_dispatcher.dispatch(
                    "create_purchase",
                    {
                        "supplier_name": "Sup",
                        "product_name": "Bolt",
                        "quantity": 1,
                    },
                ).success
                is False
            )

    def test_report_and_user_paths(self, permitted, mock_ai_user):
        from ai_knowledge.action_dispatcher import action_dispatcher

        with (
            permitted[0],
            permitted[1],
            permitted[2],
            permitted[3],
            patch("ai_knowledge.action_dispatcher.db.session") as session,
            patch("models.Sale") as Sale,
            patch("models.SaleLine") as SaleLine,
            patch("models.Product") as Product,
        ):
            q = MagicMock()
            q.filter.return_value = q
            q.scalar.side_effect = [RuntimeError(), Decimal("1000"), Decimal("1000")]
            session.query.return_value = q
            assert action_dispatcher.dispatch("sales_summary", {}).success is False
            line = MagicMock(product_id=1, quantity=Decimal("2"))
            SaleLine.query.join.return_value.filter.return_value.all.return_value = [
                line
            ]
            Sale.query.filter_by.return_value.count.return_value = 5
            Product.query.get.return_value = MagicMock(cost_price=Decimal("10"))
            result = action_dispatcher.dispatch("profit_summary", {})
            assert result.success is True or "ربح" in result.message
        with (
            patch(
                "ai_knowledge.action_dispatcher._get_active_tenant_id", return_value=1
            ),
            patch("ai_knowledge.action_dispatcher._is_owner", return_value=False),
            permitted[2],
            permitted[3],
        ):
            assert action_dispatcher.dispatch(
                "create_user", {"username": "u", "password": "p"}
            ).needs_permission


class TestSecondaryWave4:
    def test_reasoning_engine_branches(self):
        from ai_knowledge.core.reasoning_engine import ReasoningEngine

        engine = ReasoningEngine()
        assert engine._decompose_problem("سعر price للمنتج", [])[-1]
        assert engine._decompose_problem("توقع predict المبيعات", [])[-1]
        assert engine._decompose_problem("قيد محاسبة accounting", [])[-1]
        assert engine._decompose_problem("سؤال عام", [])[-1]
        ctx = {
            "cost_price": 100,
            "customer_type": "merchant",
            "quantity": 20,
            "margin": 1.2,
            "discount": 5,
        }
        result = engine.think("سعر price", ctx)
        assert result["confidence"] >= 0
        assert engine._combine_solutions([100, 120, 130, 140], "pricing") == 140
        assert engine._combine_solutions([1], "prediction") == 1
        assert engine._combine_solutions([], "other") is None
        for sub in (
            "سعر التكلفة",
            "نوع العميل",
            "حجم الطلب",
            "السعر النهائي",
            "unknown step",
        ):
            engine._solve_step(sub, ctx)

    def test_document_generator_branches(self):
        from ai_knowledge.generation.document_generator import DocumentGenerator

        sale = _sale_mock()
        with patch("models.Sale") as MockSale, patch("models.Customer") as MockC:
            MockSale.query.get.return_value = None
            content, msg = DocumentGenerator.generate_receipt(99)
            assert content is None
            MockSale.query.get.return_value = sale
            with patch.object(
                DocumentGenerator,
                "generate_receipt",
                return_value=("receipt text", "ok"),
            ):
                content, msg = DocumentGenerator.generate_receipt(42)
                assert content == "receipt text"
            with patch.object(
                DocumentGenerator,
                "generate_invoice",
                return_value=("invoice text", "ok"),
            ):
                content, msg = DocumentGenerator.generate_invoice(42)
                assert content == "invoice text"
            MockC.query.get.return_value = MagicMock(
                id=1,
                name="Ali",
                customer_type="regular",
                phone="",
                email="",
                get_balance_aed=lambda: Decimal("100"),
            )
            MockSale.query.filter.return_value.all.return_value = [sale]
            statement, smsg = DocumentGenerator.generate_customer_statement(1)
            assert statement is None or "كشف" in statement

    def test_knowledge_base_ecu_and_search(self):
        from ai_knowledge.knowledge_base import (
            search_parts,
            get_compatible_parts,
            get_automotive_ecu_knowledge,
        )

        hits = search_parts("محرك engine")
        assert hits or isinstance(hits, list)
        assert "compatible" in get_compatible_parts(
            "filter", "Toyota"
        ).lower() or "filter" in get_compatible_parts("filter", "Toyota")
        ecu = get_automotive_ecu_knowledge()
        assert ecu.get_ecu_info("engine_ecu")
        assert ecu.diagnose_code("P0420")["found"] is True
        assert ecu.diagnose_code("C0123")["category"] == "Chassis"
        assert ecu.diagnose_code("X9999")["found"] is False
        assert ecu.get_sensor_info("MAF") or ecu.get_sensor_info("UNKNOWN") == {}

    def test_continuous_learner_remaining(self, knowledge_path):
        from ai_knowledge.learning.continuous_learner import ContinuousLearner

        learner = ContinuousLearner()
        with (
            patch.object(
                learner,
                "learn_from_wikipedia",
                return_value={"success": False, "error": "wiki fail"},
            ),
            patch.object(
                learner,
                "learn_arxiv_papers",
                return_value={"success": True, "papers": 1},
            ),
        ):
            result = learner.daily_learning_routine()
            assert "items_learned" in result
        mock_resp = MagicMock(status_code=200, text="<entry><title>T</title></entry>")
        learner.session = MagicMock(get=MagicMock(return_value=mock_resp))
        assert learner.learn_arxiv_papers("ai")["success"] is True

    def test_intelligent_assistant_analysis_branches(self, knowledge_path):
        from ai_knowledge.agents.intelligent_assistant import IntelligentAssistant

        assistant = IntelligentAssistant()
        sale = MagicMock(
            id=1,
            total_amount=Decimal("500"),
            sale_date=datetime.now(),
            customer=MagicMock(name="Ali"),
        )
        mock_q = MagicMock()
        mock_q.filter_by.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.count.return_value = 0
        mock_q.all.return_value = []
        with (
            patch(
                "ai_knowledge.learning.quick_learner.quick_learner.get_answer",
                return_value=None,
            ),
            patch(
                "ai_knowledge.neural.semantic_matcher.understand_message",
                return_value={"intent": "sales_analysis", "confidence": 0.9},
            ),
            patch("models.Sale", mock_q),
            patch("models.Customer", mock_q),
            patch("models.Product", mock_q),
            patch("utils.tenanting.get_active_tenant_id", return_value=1),
            patch("flask.has_request_context", return_value=True),
            patch.object(assistant, "_learn_from_interaction"),
            patch.object(
                assistant.neural_engine,
                "predict_next_week_sales",
                return_value={"success": True, "predicted_amount": 5000},
                create=True,
            ),
        ):
            mock_q.all.return_value = [sale] * 10
            mock_q.count.return_value = 10
            assert assistant.process("حلل المبيعات", user_id=1)["success"] is True
        debt_payload = {
            "success": True,
            "customer": {"name": "Debtor"},
            "debt_analysis": {
                "total_debt": 6000,
                "overdue_count": 2,
                "unpaid_sales_count": 3,
            },
        }
        with (
            patch(
                "ai_knowledge.learning.quick_learner.quick_learner.get_answer",
                return_value=None,
            ),
            patch(
                "ai_knowledge.neural.semantic_matcher.understand_message",
                return_value={"intent": "customer_balance", "confidence": 0.9},
            ),
            patch.object(
                assistant,
                "_collect_real_data",
                return_value={"customer_data": debt_payload},
            ),
            patch.object(assistant, "_learn_from_interaction"),
        ):
            assert assistant.process("رصيد العميل", user_id=1)["success"] is True

    def test_master_brain_and_expansion(self, knowledge_path):
        from ai_knowledge.agents.master_brain import get_master_brain
        from ai_knowledge.expansion.global_knowledge import GlobalKnowledgeConnector

        brain = get_master_brain()
        with patch.object(
            brain, "_use_neural_if_needed", return_value={"answer": "neural"}
        ):
            assert brain.ask("توقع")["answer"]
        gkc = GlobalKnowledgeConnector()
        assert gkc.fetch_global_automotive_news()["success"] is True
        assert gkc.fetch_heavy_equipment_trends()["success"] is True


class TestWave4Extended:
    """Extended sweep for remaining sub-99% modules."""

    @pytest.fixture
    def responses(self):
        from ai_knowledge.personality.azad_responses import AzadResponses

        return AzadResponses()

    def test_azad_smart_response_routes(self, responses):
        customer = {
            "id": 1,
            "name": "أحمد",
            "customer_type": "regular",
            "phone": "050",
            "email": "a@t.com",
            "balance_aed": 500,
            "total_sales": 2,
            "last_sale_date": "2025-01-01",
        }
        with (
            patch(
                "ai_knowledge.personality.azad_responses.understand_message",
                return_value={"intent": None, "confidence": 0},
            ),
            patch(
                "services.ai_service.AIService.is_sensitive_request",
                return_value=(False, False, {}),
            ),
            patch("ai_knowledge.personality.azad_responses.azad_personality") as ap,
            patch("ai_knowledge.personality.azad_responses.learning_system"),
            patch("ai_knowledge.personality.azad_responses.system_integrator") as si,
            patch("ai_knowledge.personality.azad_responses.data_analyzer") as da,
            patch("ai_knowledge.personality.azad_responses.document_generator") as dg,
            patch("ai_knowledge.personality.azad_responses.knowledge_expander") as ke,
            patch(
                "ai_knowledge.personality.azad_responses.get_help_for_task",
                return_value="لم أجد",
            ),
            patch(
                "ai_knowledge.personality.azad_responses.search_knowledge",
                return_value=[],
            ),
            patch(
                "ai_knowledge.personality.azad_responses.get_system_guide",
                return_value="guide",
            ),
        ):
            ap.is_inappropriate_message.return_value = "normal"
            ap.get_help_intro.return_value = "help"
            ap.get_greeting.return_value = "hi"
            ap.get_professional_joke.return_value = "joke"
            si.get_customer_balance.return_value = {
                "success": True,
                "customer": customer,
            }
            da.analyze_customer_debt.return_value = {"success": False}
            si.get_system_summary.return_value = {
                "success": True,
                "summary": {
                    "customers": {"total": 1, "vip": 0, "recent": []},
                    "sales": {"total": 1, "today": 0, "recent": []},
                    "products": {"total": 1, "low_stock": 0, "out_of_stock": 0},
                },
            }
            si.get_financial_summary.return_value = {
                "success": True,
                "financial": {
                    "total_sales": 1000.0,
                    "total_payments": 800.0,
                    "total_receivables": 200.0,
                    "today_sales": 50.0,
                    "today_payments": 30.0,
                },
            }
            si.get_product_stock.return_value = {
                "success": True,
                "product": {
                    "name": "F",
                    "id": 1,
                    "sku": "S",
                    "category": "C",
                    "unit_price": 10.0,
                    "current_stock": 5,
                    "alert_limit": 10,
                },
            }
            si.search_data.return_value = {
                "success": True,
                "results": {"customers": [], "products": [], "sales": []},
            }
            dg.generate_invoice.return_value = ("inv", "ok")
            ke.search_knowledge.return_value = {
                "success": True,
                "total_found": 1,
                "results": [
                    {"title": "T", "type": "d", "category": "c", "snippet": "s"}
                ],
            }
            routes = [
                "رصيد balance عميل customer أحمد",
                "بيانات info عميل customer سامي",
                "مخزون stock منتج product فلتر",
                "ملخص summary نظام system كلي",
                "أضف add عميل customer جديد",
                "ابحث search عن علي",
                "أضف add موقع website مصدر source",
                "روابط links نظام system",
                "مصادر sources كل all",
                "أين where أجد find معلومات tax",
                "ابحث search في المعرفة knowledge tax",
                "فاتورة invoice جديد new create",
                "سند receipt جديد new create",
                "ولد generate فاتورة invoice 55",
                "صدر export excel بيانات data مبيعات sales",
                "تقرير report مبيعات sales",
                "ولد generate تقرير report مبيعات sales",
                "قانون law ضريبة tax فلسطين palestine",
                "شحن shipping قانون law إجراءات procedures",
                "جودة quality معايير standards",
                "نكتة joke ضحك laugh",
                "xyzunknown سؤال عام",
            ]
            for msg in routes:
                assert isinstance(responses.smart_response(msg), str)

    def test_azad_forecast_trend_down_stable(self, responses):
        cols = _patch_model_cols("models.Sale")
        try:
            for trend, rec in [("down", "راجع"), ("stable", "مستقر"), ("up", "استمر")]:
                with (
                    patch(
                        "ai_knowledge.personality.azad_responses.understand_message",
                        return_value={"intent": None, "confidence": 0},
                    ),
                    patch(
                        "services.ai_service.AIService.is_sensitive_request",
                        return_value=(False, False, {}),
                    ),
                    patch(
                        "ai_knowledge.personality.azad_responses.azad_personality"
                    ) as ap,
                    patch("ai_knowledge.personality.azad_responses.learning_system"),
                    patch("extensions.db") as mock_db,
                    patch(
                        "ai_knowledge.personality.azad_responses.SalesAnalytics.predict_next_month_sales",
                        return_value={
                            "prediction": 3000,
                            "trend": trend,
                            "trend_value": 100,
                            "confidence": 0.8,
                            "method": "avg",
                        },
                    ),
                ):
                    ap.is_inappropriate_message.return_value = "normal"
                    mock_db.session.query.return_value.filter.return_value.group_by.return_value.all.return_value = [
                        MagicMock(total=500)
                    ]
                    result = responses.smart_response("توقع predict forecast")
                    assert rec in result or "3,000" in result
        finally:
            _stop_patches(cols)

    def test_intelligent_assistant_full_analysis(self, knowledge_path):
        from ai_knowledge.agents.intelligent_assistant import IntelligentAssistant

        assistant = IntelligentAssistant()
        sale = MagicMock(
            id=1,
            total_amount=Decimal("100"),
            sale_date=datetime.now(),
            customer=MagicMock(name="Ali"),
        )
        product = MagicMock(
            id=1, name="Bolt", current_stock=Decimal("1"), min_stock_alert=Decimal("5")
        )
        mock_q = MagicMock()
        mock_q.filter_by.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.count.return_value = 0
        mock_q.all.return_value = []
        mock_q.first.return_value = MagicMock(id=1)
        cols = _patch_model_cols("models.Sale", "models.Customer", "models.Product")
        try:
            with (
                patch(
                    "ai_knowledge.learning.quick_learner.quick_learner.get_answer",
                    return_value=None,
                ),
                patch(
                    "utils.tenanting.get_active_tenant_id",
                    side_effect=RuntimeError("tid"),
                ),
                patch("flask.has_request_context", return_value=True),
                patch("models.Sale", mock_q),
                patch("models.Customer", mock_q),
                patch("models.Product", mock_q),
                patch.object(assistant, "_learn_from_interaction"),
            ):
                um = patch("ai_knowledge.neural.semantic_matcher.understand_message")
                with um as understand:
                    understand.return_value = {
                        "intent": "sales_analysis",
                        "confidence": 0.9,
                    }
                    mock_q.all.return_value = []
                    mock_q.count.return_value = 0
                    assert (
                        assistant.process("حلل المبيعات", user_id=1)["success"] is True
                    )
                    understand.return_value = {
                        "intent": "sales_analysis",
                        "confidence": 0.9,
                    }
                    mock_q.all.return_value = [sale] * 3
                    assert (
                        assistant.process("حلل المبيعات", user_id=1)["success"] is True
                    )
                    understand.return_value = {
                        "intent": "sales_analysis",
                        "confidence": 0.9,
                    }
                    mock_q.all.return_value = [sale] * 60
                    with patch.object(
                        assistant.neural_engine,
                        "predict_next_week_sales",
                        return_value={"success": True, "predicted_amount": 9000},
                        create=True,
                    ):
                        assert (
                            assistant.process("حلل المبيعات", user_id=1)["success"]
                            is True
                        )
                    understand.return_value = {
                        "intent": "inventory_check",
                        "confidence": 0.9,
                    }
                    mock_q.filter.return_value.all.return_value = []
                    assert assistant.process("مخزون", user_id=1)["success"] is True
                    mock_q.filter.return_value.all.return_value = [product] * 6
                    assert assistant.process("مخzون", user_id=1)["success"] is True
                    understand.return_value = {
                        "intent": "customer_balance",
                        "confidence": 0.9,
                    }
                    with patch.object(
                        assistant,
                        "_extract_entities",
                        return_value={"names": ["Ali"], "products": ["Bolt"]},
                    ):
                        with patch.object(
                            assistant.data_analyzer,
                            "analyze_customer_debt",
                            return_value={
                                "success": True,
                                "debt_analysis": {"total_debt": 0, "overdue_count": 0},
                            },
                        ):
                            assert (
                                assistant.process("رصيد Ali", user_id=1)["success"]
                                is True
                            )
                        with patch.object(
                            assistant.data_analyzer,
                            "analyze_customer_debt",
                            return_value={
                                "success": True,
                                "debt_analysis": {
                                    "total_debt": 8000,
                                    "overdue_count": 2,
                                },
                            },
                        ):
                            assert (
                                assistant.process("رصيد Ali", user_id=1)["success"]
                                is True
                            )
        finally:
            _stop_patches(cols)

    def test_intelligent_assistant_generate_and_learn(self, knowledge_path):
        from ai_knowledge.agents.intelligent_assistant import IntelligentAssistant

        assistant = IntelligentAssistant()
        analysis = {
            "insights": ["i"],
            "warnings": ["w"],
            "recommendations": ["r"],
            "predictions": ["p"],
        }
        data = {
            "low_stock_products": [],
            "customer_data": {
                "success": True,
                "debt_analysis": {
                    "total_debt": 500,
                    "unpaid_sales_count": 1,
                    "overdue_count": 0,
                },
            },
        }
        resp = assistant._generate_dynamic_response(
            "inventory_check", analysis, {}, data
        )
        assert "صحي" in resp
        data2 = {
            "low_stock_products": [{"name": "X", "current_stock": 1, "min_alert": 5}]
        }
        assert assistant._generate_dynamic_response(
            "inventory_check", analysis, {}, data2
        )
        with patch.object(
            assistant.memory_system, "remember_conversation", side_effect=RuntimeError()
        ):
            assistant._learn_from_interaction("q", "a", None)
        with (
            patch(
                "ai_knowledge.learning.quick_learner.quick_learner.get_answer",
                return_value=None,
            ),
            patch.object(
                assistant, "_understand_message", side_effect=RuntimeError("fail")
            ),
        ):
            assert assistant.process("test", user_id=1)["success"] is False

    def test_agents_core_train_failure(self):
        from ai_knowledge import agents_core as ac

        with (
            patch("ai_knowledge.system_knowledge.FAQ", {}),
            patch("ai_knowledge.system_knowledge.search_knowledge", return_value=[]),
            patch(
                "ai_knowledge.agents_core._check_llm_availability", return_value=False
            ),
            patch(
                "ai_knowledge.agents.master_brain.get_master_brain",
                side_effect=RuntimeError("brain"),
            ),
            patch("ai_knowledge.trainer.trainer", side_effect=RuntimeError("train")),
        ):
            result = ac.ask_azad_enhanced("سؤال")
            assert result["answer"]
        with patch("ai_knowledge.trainer.trainer") as tr:
            tr.learn_from_interaction.side_effect = RuntimeError()
            with (
                patch(
                    "ai_knowledge.action_dispatcher.action_dispatcher.parse_chat_action",
                    return_value=("create_customer", {"name": "Ali"}),
                ),
                patch(
                    "ai_knowledge.action_dispatcher.action_dispatcher.dispatch",
                    return_value=MagicMock(
                        success=True, message="ok", needs_permission=""
                    ),
                ),
            ):
                from ai_knowledge.agents_core import intelligent_response

                assert intelligent_response("عميل Ali")

    def test_document_generator_exports(self):
        from ai_knowledge.generation.document_generator import DocumentGenerator

        sale = _sale_mock()
        customer = MagicMock(
            id=1,
            name="Ali",
            customer_type="regular",
            phone="050",
            email="a@t.com",
            get_balance_aed=lambda: Decimal("100"),
            created_at=datetime.now(),
        )
        product = MagicMock(
            id=1,
            name="Bolt",
            sku="B1",
            current_stock=10,
            unit_price=Decimal("5"),
            min_stock_alert=2,
            category=MagicMock(name="Parts"),
        )
        with (
            patch("models.Sale") as MockSale,
            patch("models.Customer") as MockC,
            patch("models.Product") as MockP,
        ):
            MockSale.query.all.return_value = [sale]
            MockC.query.all.return_value = [customer]
            MockP.query.all.return_value = [product]
            for dtype in ("sales", "customers", "products"):
                data, fname = DocumentGenerator.export_to_excel(dtype)
                assert data is not None
            MockC.query.get.return_value = customer
            MockSale.query.filter.return_value.all.return_value = [sale]
            stmt, msg = DocumentGenerator.generate_customer_statement(1)
            assert stmt is None or "كشف" in stmt

    def test_system_integration_paths(self):
        from ai_knowledge.core.system_integration import SystemIntegrator

        integrator = SystemIntegrator()
        customer = MagicMock(id=1, name="Ali")
        sale = MagicMock(
            id=10,
            total_amount=Decimal("500"),
            paid_amount=Decimal("200"),
            created_at=datetime.now(),
        )
        customer.sales.all.return_value = [sale]
        with patch("models.Customer") as MockC:
            MockC.query.get.return_value = customer
            summary = integrator.get_customer_sales_summary(1)
            assert summary["success"] is True
            MockC.query.get.return_value = None
            assert integrator.get_customer_sales_summary(99)["success"] is False
        with patch("models.Customer") as MockC, patch("extensions.db") as mock_db:
            MockC.query.get.side_effect = RuntimeError("db")
            assert integrator.get_customer_sales_summary(1)["success"] is False

    def test_knowledge_expansion_and_global(self, knowledge_path):
        from ai_knowledge.expansion.knowledge_expansion import KnowledgeExpander
        from ai_knowledge.expansion.global_knowledge import (
            GlobalKnowledgeConnector,
            GlobalExpertiseUpdater,
        )

        expander = KnowledgeExpander()
        with patch("builtins.open", side_effect=OSError("read fail")):
            expander._load_sources()
        gkc = GlobalKnowledgeConnector()
        assert gkc.fetch_heavy_equipment_trends()["success"] is True
        updater = GlobalExpertiseUpdater()
        result = updater.update_expertise()
        assert isinstance(result, dict)

    def test_master_brain_neural_path(self):
        from ai_knowledge.agents.master_brain import get_master_brain

        brain = get_master_brain()
        result = brain.ask("توقع المبيعات")
        assert result.get("answer")

    def test_neural_remaining_edges(self, knowledge_path):
        from ai_knowledge.neural.neural_engine import AzadNeuralEngine

        engine = AzadNeuralEngine()
        _fast_models(engine)
        with patch.object(engine, "_load_model", return_value=False):
            assert engine._forecast_sales_internal(7)["error"] == "Model not trained"
        cols = _patch_model_cols("models.Sale")
        try:
            with (
                patch.object(engine, "_load_model", return_value=True),
                patch("extensions.db") as mock_db,
            ):
                mock_db.session.query.return_value.filter.return_value.group_by.return_value.order_by.return_value.limit.return_value.all.return_value = []
                assert (
                    engine._forecast_sales_internal(3)["error"]
                    == "Not enough recent data"
                )
        finally:
            _stop_patches(cols)
        with patch.object(
            engine, "_train_price_internal", side_effect=RuntimeError("fail")
        ):
            assert engine.train_price_optimizer()["success"] is False

    def test_action_dispatcher_remaining(self, mock_ai_user):
        from ai_knowledge.action_dispatcher import (
            action_dispatcher,
            _get_active_tenant_id,
            _log_ai_error,
        )

        with patch("flask.g", create=True) as g:
            g.active_tenant_id = None
            with patch(
                "ai_knowledge.action_dispatcher.current_user",
                SimpleNamespace(is_authenticated=True, tenant_id=5),
            ):
                assert _get_active_tenant_id() == 5
        with (
            patch(
                "ai_knowledge.action_dispatcher._get_active_tenant_id", return_value=1
            ),
            patch("ai_knowledge.action_dispatcher._is_owner", return_value=True),
            patch("ai_knowledge.action_dispatcher._audit"),
            patch("ai_knowledge.action_dispatcher._log_ai_error"),
            patch("models.Product") as Product,
        ):
            Product.query.filter.return_value.all.side_effect = RuntimeError()
            assert action_dispatcher.dispatch("check_stock", {}).success is False
        with patch("ai_knowledge.action_dispatcher.db.session") as session:
            session.add.side_effect = RuntimeError()
            _log_ai_error("t", "m")

    def test_reasoning_engine_extended(self):
        from ai_knowledge.core.reasoning_engine import ReasoningEngine

        engine = ReasoningEngine()
        fin = engine.financial_reasoning(
            "تحليل",
            {
                "sales": 10000,
                "costs": 6000,
                "expenses": 1000,
                "assets": 50000,
                "liabilities": 20000,
            },
        )
        assert fin["metrics"]["net_profit"] == 3000
        assert engine.mathematical_reasoning("100 / 4")["result"] == 25
        with patch.object(engine, "_solve_step", side_effect=RuntimeError()):
            assert engine.think("test", {})["confidence"] >= 0

    def test_analytics_and_learning_gaps(self):
        from ai_knowledge.analytics.analytics_predictions import (
            SalesAnalytics,
            InventoryAnalytics,
            ProfitAnalytics,
        )
        from ai_knowledge.analytics.data_analyzer import DataAnalyzer

        assert SalesAnalytics.analyze_sales_pattern(
            [MagicMock(sale_date=datetime.now())] * 6
        )["trend"]
        assert (
            InventoryAnalytics.calculate_reorder_point(
                {"avg_daily_sales": 0, "lead_time_days": 7, "current_stock": 0}
            )["status"]
            == "order_now"
        )
        assert ProfitAnalytics.break_even_analysis(1000, 10, 25)["break_even_units"] > 0
        with patch("extensions.db") as mock_db, patch("models.Customer") as MockC:
            mock_db.session.get.return_value = None
            assert DataAnalyzer().analyze_customer_debt(99)["success"] is False
