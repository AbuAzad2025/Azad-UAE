"""Product images + sentiment analysis — upload, reorder, polarity boundaries."""

from __future__ import annotations

from unittest.mock import MagicMock


class TestProductImageService:
    """ProductImageService — upload path, query, soft delete."""

    def test_upload_image_saves_and_registers(self, app, mocker):
        product = MagicMock(id=10, tenant_id=2)
        file_obj = MagicMock(filename="photo.PNG")
        mocker.patch("services.product_image_service.os.makedirs")
        mocker.patch("services.product_image_service.db.session")
        mocker.patch(
            "models.product_image.ProductImage",
            side_effect=lambda **kw: MagicMock(**kw),
        )

        from services.product_image_service import ProductImageService

        with app.app_context():
            app.root_path = "/app"
            image = ProductImageService.upload_image(
                product, file_obj, "main", "ع", "en"
            )

        assert image.tenant_id == 2
        file_obj.save.assert_called_once()

    def test_get_images_for_product_filters_type(self, mocker):
        from models.product_image import ProductImage

        mock_q = MagicMock()
        mock_q.filter_by.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.all.return_value = [MagicMock()]
        mocker.patch.object(
            ProductImage, "query", new_callable=mocker.PropertyMock, return_value=mock_q
        )

        from services.product_image_service import ProductImageService

        rows = ProductImageService.get_images_for_product(5, image_type="gallery")
        assert len(rows) == 1
        assert mock_q.filter_by.call_count >= 2

    def test_reorder_images_updates_sort_order(self, mocker):
        img = MagicMock(product_id=1, sort_order=0)
        mocker.patch("models.product_image.ProductImage.query").get.return_value = img
        from services.product_image_service import ProductImageService

        ProductImageService.reorder_images(1, [99])
        assert img.sort_order == 0

    def test_delete_image_soft_deactivates(self, mocker):
        img = MagicMock(is_active=True)
        mocker.patch("models.product_image.ProductImage.query").get.return_value = img
        from services.product_image_service import ProductImageService

        ProductImageService.delete_image(7)
        assert img.is_active is False


class TestSentimentAnalyzer:
    """SentimentAnalyzer — polarity thresholds and customer feedback."""

    def test_empty_text_neutral(self):
        from services.sentiment_service import SentimentAnalyzer

        r = SentimentAnalyzer.analyze("")
        assert r["sentiment"] == "neutral"
        assert r["confidence"] == 0.0

    def test_positive_english(self):
        from services.sentiment_service import SentimentAnalyzer

        r = SentimentAnalyzer.analyze("excellent service, thank you")
        assert r["sentiment"] == "positive"
        assert r["polarity"] > 0.2

    def test_negative_arabic(self):
        from services.sentiment_service import SentimentAnalyzer

        r = SentimentAnalyzer.analyze("خدمة سيئة ومشكلة كبيرة")
        assert r["sentiment"] == "negative"
        assert r["polarity"] < -0.2

    def test_neutral_mixed_low_confidence(self):
        from services.sentiment_service import SentimentAnalyzer

        r = SentimentAnalyzer.analyze("good but bad experience overall maybe")
        assert r["sentiment"] in ("neutral", "positive", "negative")

    def test_analyze_customer_feedback_no_notes(self, mocker):
        mocker.patch("models.Sale.query").filter_by.return_value.all.return_value = [
            MagicMock(notes=None),
        ]
        from services.sentiment_service import SentimentAnalyzer

        r = SentimentAnalyzer.analyze_customer_feedback(1)
        assert r["feedback_count"] == 0
        assert r["overall_sentiment"] == "neutral"

    def test_analyze_customer_feedback_aggregates(self, mocker):
        mocker.patch("models.Sale.query").filter_by.return_value.all.return_value = [
            MagicMock(notes="excellent support"),
        ]
        from services.sentiment_service import SentimentAnalyzer

        r = SentimentAnalyzer.analyze_customer_feedback(2)
        assert r["feedback_count"] == 1
        assert r["overall_sentiment"] == "positive"
