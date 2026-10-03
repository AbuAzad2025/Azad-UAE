"""Tests for upload content validation.

The extension allowlist is a filename check. These cover the part that was
missing: proving the bytes match the declared type, so a .png that is really
HTML cannot be stored and later served back as executable script.
"""

from __future__ import annotations

import io

import pytest

from utils.validators import ValidationError, validate_file_signature

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
GIF87 = b"GIF87a" + b"\x00" * 16
GIF89 = b"GIF89a" + b"\x00" * 16
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 8
PDF = b"%PDF-1.7\n" + b"\x00" * 16
XLSX = b"PK\x03\x04" + b"\x00" * 16

HTML_PAYLOAD = b"<html><script>alert(1)</script></html>"
PHP_PAYLOAD = b"<?php system($_GET['c']); ?>"
ELF_PAYLOAD = b"\x7fELF\x02\x01\x01" + b"\x00" * 16


class TestGenuineFilesAreAccepted:
    @pytest.mark.parametrize(
        ("name", "header"),
        [
            ("photo.png", PNG),
            ("photo.jpg", JPG),
            ("photo.jpeg", JPG),
            ("anim.gif", GIF87),
            ("anim2.gif", GIF89),
            ("pic.webp", WEBP),
            ("doc.pdf", PDF),
            ("sheet.xlsx", XLSX),
        ],
    )
    def test_real_files_pass(self, name, header):
        validate_file_signature(name, header)

    def test_uppercase_extension_is_accepted(self):
        validate_file_signature("PHOTO.PNG", PNG)

    def test_no_extension_is_left_to_the_allowlist(self):
        # save_uploaded_file's own extension check is what rejects these; the
        # signature check must not be the thing that raises a confusing error.
        validate_file_signature("noextension", PNG)


class TestMismatchedContentIsRejected:
    @pytest.mark.parametrize(
        ("name", "header"),
        [
            ("evil.png", HTML_PAYLOAD),
            ("evil.png", PHP_PAYLOAD),
            ("evil.png", ELF_PAYLOAD),
            ("evil.jpg", HTML_PAYLOAD),
            ("evil.gif", b"<html></html>"),
            ("evil.pdf", HTML_PAYLOAD),
            ("evil.xlsx", HTML_PAYLOAD),
            ("evil.webp", b"RIFF____NOPE"),
        ],
    )
    def test_content_contradicting_extension_is_rejected(self, name, header):
        with pytest.raises(ValidationError):
            validate_file_signature(name, header)

    def test_webp_requires_the_riff_type_marker(self):
        # RIFF alone is not enough: WAV/AVI share the container. The WEBP tag
        # lives at offset 8, which is why the signature table carries offsets.
        assert len(WEBP) > 12
        with pytest.raises(ValidationError):
            validate_file_signature("x.webp", b"RIFF" + b"\x00" * 20)

    def test_png_signature_must_be_exact(self):
        # A single flipped byte in the 8-byte PNG signature must not pass.
        broken = b"\x89PNH\r\n\x1a\n" + b"\x00" * 16
        with pytest.raises(ValidationError):
            validate_file_signature("x.png", broken)

    def test_truncated_header_is_rejected(self):
        # Shorter than the signature: the slice comparison fails rather than
        # raising IndexError.
        with pytest.raises(ValidationError):
            validate_file_signature("x.png", b"\x89")


class TestUnsignedFormats:
    @pytest.mark.parametrize("name", ["data.csv", "notes.txt", "conf.xml", "payload.json"])
    def test_text_formats_have_no_signature_to_check(self, name):
        # Accepted by design - they are text, and the extension allowlist plus
        # downstream parsing are the controls. Any prefix is plausible here.
        validate_file_signature(name, b"\x00\x01\x02nonsense")

    def test_unknown_binary_extension_is_rejected(self):
        with pytest.raises(ValidationError):
            validate_file_signature("tool.exe", b"MZ\x90\x00")


class TestErrorIsCatchableAsValueError:
    def test_validation_error_is_a_value_error(self):
        # helpers.save_uploaded_file callers (routes/warehouse.py) already catch
        # ValueError to return 400. If this were a bare Exception it would escape
        # as a 500 and turn a client-side rejection into a server error.
        assert issubclass(ValidationError, ValueError)
        with pytest.raises(ValueError):
            validate_file_signature("evil.png", HTML_PAYLOAD)


class TestSaveUploadedFileEnforcesIt:
    def _storage(self, tmp_path, app):
        app.static_folder = str(tmp_path)
        return tmp_path

    def test_html_disguised_as_png_is_rejected_before_disk(self, app, tmp_path, monkeypatch):
        """The end-to-end contract: nothing is written when bytes disagree."""
        from utils.helpers import save_uploaded_file

        self._storage(tmp_path, app)

        class FakeUpload:
            filename = "avatar.png"

            def __init__(self, data):
                self._stream = io.BytesIO(data)

            def seek(self, *a):
                return self._stream.seek(*a)

            def tell(self):
                return self._stream.tell()

            def read(self, *a):
                return self._stream.read(*a)

            def save(self, path):
                raise AssertionError("save() must not be reached")

        monkeypatch.setattr("utils.helpers.current_app", app, raising=False)
        with pytest.raises(ValueError):
            save_uploaded_file(FakeUpload(HTML_PAYLOAD), "uploads/avatars", {"png", "jpg"})

    def test_real_png_is_accepted(self, app, tmp_path, monkeypatch):
        from utils.helpers import save_uploaded_file

        self._storage(tmp_path, app)
        written = {}

        class FakeUpload:
            filename = "avatar.png"

            def __init__(self, data):
                self._stream = io.BytesIO(data)

            def seek(self, *a):
                return self._stream.seek(*a)

            def tell(self):
                return self._stream.tell()

            def read(self, *a):
                return self._stream.read(*a)

            def save(self, path):
                written["path"] = path
                with open(path, "wb") as fh:
                    fh.write(PNG)

        monkeypatch.setattr("utils.helpers.current_app", app, raising=False)
        result = save_uploaded_file(FakeUpload(PNG), "uploads/avatars", {"png"})
        assert result and result.endswith(".png")
        assert written["path"].endswith(".png")


class TestAllowedExtensionForm:
    """Both spellings of an extension must be honoured.

    Callers are inconsistent: routes/warehouse.py and routes/store.py pass
    {"png", "jpg"}, while services/training_importer.py passes {".json",
    ".xlsx"}. Comparing only the dotted form silently rejected every product
    image and store logo upload with a 400.
    """

    def test_undotted_set_accepts_the_file(self, app, monkeypatch):
        from utils.helpers import allowed_file

        monkeypatch.setattr("utils.helpers.current_app", app, raising=False)
        assert allowed_file("photo.png", {"png", "jpg"}) is True

    def test_dotted_set_accepts_the_file(self, app, monkeypatch):
        from utils.helpers import allowed_file

        monkeypatch.setattr("utils.helpers.current_app", app, raising=False)
        assert allowed_file("data.json", {".json", ".xlsx"}) is True

    def test_a_genuinely_disallowed_extension_is_still_refused(self, app, monkeypatch):
        from utils.helpers import allowed_file

        monkeypatch.setattr("utils.helpers.current_app", app, raising=False)
        assert allowed_file("payload.exe", {"png", "jpg"}) is False
        assert allowed_file("archive.zip", {"png", "jpg"}) is False

    def test_extension_matching_is_case_insensitive(self, app, monkeypatch):
        from utils.helpers import allowed_file

        monkeypatch.setattr("utils.helpers.current_app", app, raising=False)
        assert allowed_file("PHOTO.PNG", {"png"}) is True
        assert allowed_file("photo.PNG", {".PNG"}) is True
