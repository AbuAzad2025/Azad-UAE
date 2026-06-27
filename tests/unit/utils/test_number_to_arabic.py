from decimal import Decimal

import pytest

from utils.number_to_arabic import _to_words_under_1000, number_to_arabic_words


class TestNumberToArabicWords:
    def test_zero_under_1000_returns_empty(self):
        assert _to_words_under_1000(0) == ''

    def test_zero_major_only(self):
        result = number_to_arabic_words(0, 'AED')
        assert 'صفر' in result
        assert 'فقط لا غير' in result

    def test_negative_returns_empty(self):
        assert number_to_arabic_words(-5) == ''

    def test_with_minor_units(self):
        result = number_to_arabic_words('1500.75', 'AED')
        assert 'درهم إماراتي' in result
        assert 'فلس' in result

    def test_major_only_rounded(self):
        result = number_to_arabic_words('100.00', 'USD')
        assert 'دولار' in result
        assert 'سنت' not in result.split('فقط')[0].split('و')[-1]

    def test_unknown_currency_labels(self):
        result = number_to_arabic_words('10.05', 'XYZ')
        assert 'وحدة نقدية' in result
        assert 'جزء' in result

    def test_teens_and_tens(self):
        assert 'عشرة' in number_to_arabic_words(10, 'AED')
        assert 'خمسة عشر' in number_to_arabic_words(15, 'AED')
        assert 'عشرون' in number_to_arabic_words(20, 'AED')
        assert 'واحد و عشرون' in number_to_arabic_words(21, 'AED')

    def test_hundreds(self):
        result = number_to_arabic_words(300, 'AED')
        assert 'ثلاثمائة' in result

    def test_thousands_singular_and_dual(self):
        assert 'ألف' in number_to_arabic_words(1000, 'AED')
        assert 'ألفان' in number_to_arabic_words(2000, 'AED')

    def test_thousands_plural_range(self):
        result = number_to_arabic_words(5000, 'AED')
        assert 'آلاف' in result

    def test_thousands_large(self):
        result = number_to_arabic_words(11000, 'AED')
        assert 'ألف' in result

    def test_millions_singular_dual_plural(self):
        assert 'مليون' in number_to_arabic_words(1_000_000, 'AED')
        assert 'مليونان' in number_to_arabic_words(2_000_000, 'AED')
        assert 'ملايين' in number_to_arabic_words(5_000_000, 'AED')

    def test_millions_large(self):
        result = number_to_arabic_words(12_345_678, 'AED')
        assert 'مليون' in result

    def test_decimal_input_types(self):
        assert number_to_arabic_words(Decimal('42.50'), 'EUR')
        assert number_to_arabic_words(42, 'GBP')

    def test_currency_codes(self):
        for code, label in (
            ('ILS', 'شيقل'),
            ('SAR', 'ريال'),
            ('KWD', 'دينار'),
            ('QAR', 'ريال'),
            ('BHD', 'دينار'),
            ('OMR', 'ريال'),
            ('JOD', 'دينار'),
            ('EGP', 'جنيه'),
            ('GBP', 'جنيه'),
            ('EUR', 'يورو'),
        ):
            assert label in number_to_arabic_words('1.01', code)
