import os
from datetime import datetime, timezone
from extensions import db
from flask import current_app


class ProductImageService:
    @staticmethod
    def upload_image(product, file, image_type, caption_ar=None, caption_en=None):
        from models.product_image import ProductImage

        upload_dir: str = os.path.join(
            str(current_app.root_path),
            "static",
            "uploads",
            "products",
            str(product.tenant_id),
        )
        os.makedirs(upload_dir, exist_ok=True)
        filename: str = (
            f"{product.id}_{image_type}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.{str(file.filename or '').rsplit('.', 1)[-1].lower()}"
        )
        filepath: str = os.path.join(upload_dir, filename)
        file.save(filepath)
        image_url = f"/static/uploads/products/{product.tenant_id}/{filename}"
        image = ProductImage(
            tenant_id=product.tenant_id,
            product_id=product.id,
            image_url=image_url,
            image_type=image_type,
            caption_ar=caption_ar,
            caption_en=caption_en,
        )
        db.session.add(image)
        return image

    @staticmethod
    def get_images_for_product(product_id, image_type=None):
        from models.product_image import ProductImage

        query = ProductImage.query.filter_by(product_id=product_id, is_active=True)
        if image_type:
            query = query.filter_by(image_type=image_type)
        return query.order_by(ProductImage.sort_order).all()

    @staticmethod
    def reorder_images(product_id, ordered_ids):
        from models.product_image import ProductImage

        for idx, img_id in enumerate(ordered_ids):
            img = ProductImage.query.get(img_id)
            if img and img.product_id == product_id:
                img.sort_order = idx

    @staticmethod
    def delete_image(image_id):
        from models.product_image import ProductImage

        img = ProductImage.query.get(image_id)
        if img:
            img.is_active = False
