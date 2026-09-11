"""Cov4: product_image_service — upload/get/reorder/delete arcs."""

from __future__ import annotations

from services.product_image_service import ProductImageService


class _File:
    filename = "Photo.JPG"

    def __init__(self):
        self.saved_to = None

    def save(self, path):
        self.saved_to = path
        with open(path, "w", encoding="utf-8") as f:
            f.write("img")


def test_upload_image(app, db_session, sample_product):
    f = _File()
    with app.app_context():
        img = ProductImageService.upload_image(sample_product, f, "main",
                                               caption_ar="ع", caption_en="en")
        assert img.image_url.startswith("/static/uploads/products/")
        assert img.image_url.endswith(".jpg")
        assert f.saved_to is not None
    db_session.flush()


def test_get_images_filter(app, db_session, sample_product):
    with app.app_context():
        # Upload an image to ensure it exists
        f = _File()
        img = ProductImageService.upload_image(sample_product, f, "main", caption_ar="ع", caption_en="en")
        db_session.flush()
        assert img.image_url.startswith("/static/uploads/products/")
        assert img.image_url.endswith(".jpg")
        assert f.saved_to is not None
        assert ProductImageService.get_images_for_product(sample_product.id) != []
        assert ProductImageService.get_images_for_product(sample_product.id, image_type="main") != []
        assert ProductImageService.get_images_for_product(sample_product.id, image_type="nope") == []
        assert ProductImageService.get_images_for_product(999999999) == []


def test_reorder_only_matching_product(app, db_session, sample_product):

    with app.app_context():
        f = _File()
        ProductImageService.upload_image(sample_product, f, "main", caption_ar="Test", caption_en="Test")
        db_session.flush()
        imgs = ProductImageService.get_images_for_product(sample_product.id)
        img = imgs[0]
        before = img.sort_order
        ProductImageService.reorder_images(sample_product.id + 999999, [img.id])
        db_session.refresh(img)
        assert img.sort_order == before  # wrong-product branch leaves order unchanged
        ProductImageService.reorder_images(sample_product.id, [img.id])
        assert img.sort_order == 0
        ProductImageService.reorder_images(sample_product.id, [999999999])  # missing -> skip


def test_delete_image(app, db_session, sample_product):
    from models.product_image import ProductImage

    with app.app_context():
        f = _File()
        ProductImageService.upload_image(sample_product, f, "main", caption_ar="Test", caption_en="Test")
        db_session.flush()
        imgs = ProductImage.query.filter_by(product_id=sample_product.id).all()
        ProductImageService.delete_image(imgs[0].id)
        assert imgs[0].is_active is False
        assert ProductImageService.delete_image(999999999) is None
