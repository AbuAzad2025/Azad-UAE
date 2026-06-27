"""QR generator — payload encoding and failure fallbacks."""
from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestGenerateQrDataUrl:
    def test_returns_empty_when_qrcode_missing(self):
        with patch.dict('sys.modules', {'qrcode': None}):
            import importlib
            import utils.qr_generator as mod
            importlib.reload(mod)
            assert mod.generate_qr_data_url('hello') == ''

    def test_returns_empty_for_none_or_blank(self):
        from utils.qr_generator import generate_qr_data_url
        assert generate_qr_data_url(None) == ''
        assert generate_qr_data_url('   ') == ''

    def test_serializes_dict_payload(self, mocker):
        fake_img = MagicMock()
        fake_img.save = MagicMock()
        fake_qr = MagicMock()
        fake_qr.make_image.return_value = fake_img
        fake_qrcode = MagicMock()
        fake_qrcode.QRCode.return_value = fake_qr
        fake_qrcode.constants.ERROR_CORRECT_M = 'M'
        mocker.patch.dict('sys.modules', {'qrcode': fake_qrcode})

        from utils.qr_generator import generate_qr_data_url
        result = generate_qr_data_url({'a': 1, 'b': 'x'}, size=80)
        assert result.startswith('data:image/png;base64,')

    def test_string_payload(self, mocker):
        fake_img = MagicMock()
        fake_img.save = MagicMock()
        fake_qr = MagicMock()
        fake_qr.make_image.return_value = fake_img
        fake_qrcode = MagicMock()
        fake_qrcode.QRCode.return_value = fake_qr
        fake_qrcode.constants.ERROR_CORRECT_M = 'M'
        mocker.patch.dict('sys.modules', {'qrcode': fake_qrcode})

        from utils.qr_generator import generate_qr_data_url
        result = generate_qr_data_url('plain-text')
        assert result.startswith('data:image/png;base64,')

    def test_json_dump_failure_falls_back_to_str(self, mocker):
        class BadDict(dict):
            def __iter__(self):
                raise TypeError('bad')

        fake_img = MagicMock()
        fake_img.save = MagicMock()
        fake_qr = MagicMock()
        fake_qr.make_image.return_value = fake_img
        fake_qrcode = MagicMock()
        fake_qrcode.QRCode.return_value = fake_qr
        fake_qrcode.constants.ERROR_CORRECT_M = 'M'
        mocker.patch.dict('sys.modules', {'qrcode': fake_qrcode})

        from utils.qr_generator import generate_qr_data_url
        result = generate_qr_data_url(BadDict())
        assert result.startswith('data:image/png;base64,')

    def test_generation_exception_returns_empty(self, mocker):
        fake_qrcode = MagicMock()
        fake_qrcode.QRCode.side_effect = RuntimeError('fail')
        fake_qrcode.constants.ERROR_CORRECT_M = 'M'
        mocker.patch.dict('sys.modules', {'qrcode': fake_qrcode})
        from utils.qr_generator import generate_qr_data_url
        assert generate_qr_data_url('x') == ''

    def test_json_encode_failure_on_dict(self, mocker):
        fake_img = MagicMock()
        fake_img.save = MagicMock()
        fake_qr = MagicMock()
        fake_qr.make_image.return_value = fake_img
        fake_qrcode = MagicMock()
        fake_qrcode.QRCode.return_value = fake_qr
        fake_qrcode.constants.ERROR_CORRECT_M = 'M'
        mocker.patch.dict('sys.modules', {'qrcode': fake_qrcode})
        mocker.patch('utils.qr_generator.json.dumps', side_effect=TypeError('bad'))
        from utils.qr_generator import generate_qr_data_url
        assert generate_qr_data_url({'k': 1}).startswith('data:image/png;base64,')

    def test_resizes_when_image_supports_resize(self, mocker):
        fake_img = MagicMock()
        fake_img.save = MagicMock()
        fake_qr = MagicMock()
        fake_qr.make_image.return_value = fake_img
        fake_qrcode = MagicMock()
        fake_qrcode.QRCode.return_value = fake_qr
        fake_qrcode.constants.ERROR_CORRECT_M = 'M'
        mocker.patch.dict('sys.modules', {'qrcode': fake_qrcode})

        from utils.qr_generator import generate_qr_data_url
        generate_qr_data_url('data', size=200)
        fake_img.resize.assert_called_once_with((200, 200))
