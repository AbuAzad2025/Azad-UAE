"""Industry service — sector field maps, validation, extra-field persistence."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.industry_service import VALID_BUSINESS_TYPES, IndustryService


class TestIndustryValidation:
    """validate_industry_code / business type choices."""

    @pytest.mark.parametrize('code,valid', [
        ('pharmacy', True),
        ('mobile_parts', True),
        ('general', True),
        ('unknown_sector', False),
        ('', False),
    ])
    def test_validate_industry_code(self, code, valid):
        assert IndustryService.validate_industry_code(code) is valid

    def test_business_type_choices_include_ar_en_labels(self):
        choices = IndustryService.get_business_type_choices()
        codes = {c[0] for c in choices}
        assert codes == set(VALID_BUSINESS_TYPES)
        assert any(' / ' in label for _, label in choices)


class TestFieldDefinitions:
    """get_fields_for — per-sector active field mapping."""

    @staticmethod
    def _mock_field_query(mocker, app, rows):
        with app.app_context():
            from models.industry_field_definition import IndustryFieldDefinition

            mock_q = MagicMock()
            mock_q.filter_by.return_value.order_by.return_value.all.return_value = rows
            mocker.patch.object(
                IndustryFieldDefinition, 'query',
                new_callable=mocker.PropertyMock, return_value=mock_q,
            )
        return mock_q

    def test_get_fields_for_industry_filters_active_sorted(self, app, mocker):
        f1 = MagicMock(field_code='vin', sort_order=1)
        f2 = MagicMock(field_code='year', sort_order=2)
        mock_q = self._mock_field_query(mocker, app, [f1, f2])

        with app.app_context():
            result = IndustryService.get_fields_for('automotive', applies_to='product')
        assert result == [f1, f2]
        mock_q.filter_by.assert_called_once_with(
            industry_code='automotive', applies_to='product', is_active=True,
        )

    def test_get_core_fields_delegates_to_core_code(self, app, mocker):
        mock_q = self._mock_field_query(mocker, app, [])
        with app.app_context():
            IndustryService.get_core_fields()
        mock_q.filter_by.assert_called_with(
            industry_code='core', applies_to='product', is_active=True,
        )

    def test_get_all_field_names_extracts_codes(self, app, mocker):
        fields = [MagicMock(field_code='batch_no'), MagicMock(field_code='expiry')]
        self._mock_field_query(mocker, app, fields)
        with app.app_context():
            assert IndustryService.get_all_field_names_for('pharmacy') == ['batch_no', 'expiry']

    def test_empty_sector_returns_empty_field_list(self, app, mocker):
        self._mock_field_query(mocker, app, [])
        with app.app_context():
            assert IndustryService.get_all_field_names_for('jewelry') == []


class TestEffectiveIndustry:
    """get_product_effective_industry — product override vs tenant fallback."""

    def test_product_industry_wins(self):
        product = MagicMock(industry='electronics')
        tenant = MagicMock(business_type='pharmacy')
        assert IndustryService.get_product_effective_industry(product, tenant) == 'electronics'

    def test_tenant_fallback_when_product_blank(self):
        product = MagicMock(industry=None)
        tenant = MagicMock(business_type='restaurant')
        assert IndustryService.get_product_effective_industry(product, tenant) == 'restaurant'

    def test_general_fallback_when_tenant_type_missing(self):
        product = MagicMock(industry=None)
        tenant = MagicMock(spec=[])
        assert IndustryService.get_product_effective_industry(product, tenant) == 'general'


class TestSaveExtraFields:
    """save_extra_fields — skip blanks, persist non-empty values."""

    def test_saves_only_non_empty_form_values(self, mocker):
        field_a = MagicMock(field_code='lot_number')
        field_b = MagicMock(field_code='dosage')
        mocker.patch(
            'services.industry_service.IndustryService.get_fields_for',
            return_value=[field_a, field_b],
        )
        entity = MagicMock()
        form = {'lot_number': '  LOT-9  ', 'dosage': '', 'ignored': 'x'}

        IndustryService.save_extra_fields(entity, form, 'pharmacy')
        assert entity.extra_fields == {'lot_number': '  LOT-9  '}

    def test_no_matching_fields_yields_empty_dict(self, mocker):
        mocker.patch(
            'services.industry_service.IndustryService.get_fields_for',
            return_value=[],
        )
        entity = MagicMock()
        IndustryService.save_extra_fields(entity, {'a': '1'}, 'general')
        assert entity.extra_fields == {}
