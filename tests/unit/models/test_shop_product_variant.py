from __future__ import annotations

from models.shop_product_variant import ShopProductVariant


class TestShopProductVariantDisplay:
    def test_get_display_name_arabic(self):
        variant = ShopProductVariant(
            tenant_id=1, product_id=1, name='Red', name_ar='أحمر',
        )
        assert variant.get_display_name('ar') == 'أحمر'

    def test_get_display_name_fallback_english(self):
        variant = ShopProductVariant(
            tenant_id=1, product_id=1, name='Blue', name_ar=None,
        )
        assert variant.get_display_name('ar') == 'Blue'

    def test_get_display_name_en(self):
        variant = ShopProductVariant(
            tenant_id=1, product_id=1, name='Large', name_ar='كبير',
        )
        assert variant.get_display_name('en') == 'Large'
