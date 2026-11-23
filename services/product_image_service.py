import os
from datetime import UTC, datetime

from flask import current_app

from extensions import db
from utils.static_asset_paths import tenant_upload_dir


class ProductImageService:
    @staticmethod
    def upload_image(product, file, image_type, caption_ar=None, caption_en=None):
        from models.product_image import ProductImage

        tenant_id = getattr(product, "tenant_id", None)
        if not tenant_id:
            raise ValueError("tenant_id required")
        rel_dir = tenant_upload_dir(tenant_id, "products")
        upload_dir = os.path.join(str(current_app.root_path), "static", rel_dir)
        os.makedirs(upload_dir, exist_ok=True)
        ext = str(file.filename or "").rsplit(".", 1)[-1].lower() or "png"
        filename = f"{product.id}_{image_type}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.{ext}"
        file.save(os.path.join(upload_dir, filename))
        image = ProductImage(
            tenant_id=tenant_id,
            product_id=product.id,
            image_url=f"/static/{rel_dir}/{filename}",
            image_type=image_type,
            caption_ar=caption_ar,
            caption_en=caption_en,
        )
        db.session.add(image)
        return image

    @staticmethod
    def get_images_for_product(product_id, image_type=None, tenant_id=None):
        from models.product import Product
        from models.product_image import ProductImage

        if tenant_id is None:
            product = Product.query.get(product_id)
            tenant_id = getattr(product, "tenant_id", None) if product is not None else None
        if tenant_id is None:
            return []
        query = ProductImage.query.filter_by(product_id=product_id, tenant_id=tenant_id, is_active=True)
        if image_type:
            query = query.filter_by(image_type=image_type)
        return query.order_by(ProductImage.sort_order).all()

    @staticmethod
    def reorder_images(product_id, ordered_ids, tenant_id=None):
        from models.product import Product
        from models.product_image import ProductImage

        if tenant_id is None:
            product = Product.query.get(product_id)
            tenant_id = getattr(product, "tenant_id", None) if product is not None else None
        if tenant_id is None:
            return
        for idx, img_id in enumerate(ordered_ids):
            img = ProductImage.query.get(img_id)
            if img and img.product_id == product_id and img.tenant_id == tenant_id:
                img.sort_order = idx

    @staticmethod
    def delete_image(image_id, tenant_id=None):
        from models.product_image import ProductImage

        img = ProductImage.query.get(image_id)
        if not img:
            return None
        if tenant_id is not None and img.tenant_id != tenant_id:
            return None
        img.is_active = False
        return img
