"""Tests for specialized and knowledge domain modules."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ai_knowledge.knowledge.automotive_ecu_knowledge import AutomotiveECUKnowledge, get_automotive_ecu_knowledge
from ai_knowledge.knowledge.company_info import COMPANY_INFO, get_welcome_message
from ai_knowledge.knowledge.customs import CUSTOMS_CLEARANCE, get_customs_advice
from ai_knowledge.knowledge.parts_knowledge import PARTS_DATABASE, get_compatible_parts, get_part_info, search_parts
from ai_knowledge.specialized.customer_service import CUSTOMER_SERVICE, get_customer_service_tip
from ai_knowledge.specialized.security_rules import SecurityRules, security_rules
from ai_knowledge.specialized.tax_system import UAE_TAX_SYSTEM, get_tax_advice
from ai_knowledge.specialized.user_guide import USER_GUIDE, get_guide, get_help_for_task


class TestTaxSystem:
    def test_vat_rate(self):
        assert UAE_TAX_SYSTEM['vat']['rate'] == 5

    def test_tax_advice_rate_question(self):
        assert '5%' in get_tax_advice('كم نسبة الضريبة VAT؟')


class TestSecurityRules:
    def test_unauthenticated(self):
        with patch('ai_knowledge.specialized.security_rules.current_user', MagicMock(is_authenticated=False)):
            assert SecurityRules.is_owner() is False

    def test_filter_sensitive_non_owner(self):
        user = MagicMock(is_authenticated=True, is_owner=False)
        with patch('ai_knowledge.specialized.security_rules.current_user', user), \
             patch.object(SecurityRules, 'can_access_sensitive_info', return_value=False):
            filtered = SecurityRules.filter_sensitive_data({'password': 'secret'})
            assert filtered['password'] == '*** محمي ***'

    def test_sanitize_script(self):
        assert '<script>' not in SecurityRules.sanitize_input('<script>alert(1)</script>')

    def test_singleton(self):
        assert security_rules is not None


class TestCustomerService:
    def test_principles_exist(self):
        assert len(CUSTOMER_SERVICE['principles']) > 0

    def test_tip(self):
        with patch('secrets.choice', return_value='نصيحة'):
            assert get_customer_service_tip() == 'نصيحة'


class TestUserGuide:
    def test_get_guide_known(self):
        assert get_guide('quick_start') != 'الموضوع غير موجود'

    def test_get_guide_missing(self):
        assert get_guide('not_a_topic') == 'الموضوع غير موجود'

    def test_guide_keys(self):
        assert 'quick_start' in USER_GUIDE


class TestPartsKnowledge:
    def test_invalid_category(self):
        assert get_part_info('invalid_cat') == 'معلومات غير متوفرة'

    def test_search_parts(self):
        assert isinstance(search_parts('محرك'), list)

    def test_database_keys(self):
        assert 'heavy_equipment' in PARTS_DATABASE


class TestAutomotiveECU:
    def test_diagnose_known_code(self):
        assert AutomotiveECUKnowledge().diagnose_code('P0300')['found'] is True

    def test_singleton(self):
        assert get_automotive_ecu_knowledge() is get_automotive_ecu_knowledge()


class TestCompanyInfo:
    def test_company_info_fields(self):
        assert 'name_ar' in COMPANY_INFO

    def test_welcome_message(self):
        assert 'أزاد' in get_welcome_message() or COMPANY_INFO['name_en'] in get_welcome_message()


class TestCustoms:
    def test_customs_advice(self):
        assert isinstance(get_customs_advice('جمارك'), str)

    def test_clearance_rates(self):
        assert '5%' in CUSTOMS_CLEARANCE['general_info']['rates']
