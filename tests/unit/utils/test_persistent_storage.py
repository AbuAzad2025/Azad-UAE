"""The persistent root: the backups and the uploads must survive a redeploy.

On a container platform (Render, Docker) the application directory is
EPHEMERAL: everything written there is gone on the next deploy and on every
restart. Two things must therefore live on the attached disk instead - the
daily backups (they are the only copy of the database) and every uploaded
file (tenant logos, product photos, store logos).

These tests pin the resolution of that root, the write side and the read
side: the URL of an uploaded file must keep working while the bytes live on
the disk.
"""

import io
import os

from werkzeug.datastructures import FileStorage


class TestPersistentRootResolution:
    def test_data_dir_follows_the_environment(self):
        import config

        assert config.resolve_data_dir({"DATA_DIR": "/data"}) == "/data"
        assert config.resolve_data_dir({"DATA_DIR": "  /data  "}) == "/data"
        assert config.resolve_data_dir({}) == config.instance_dir

    def test_upload_root_follows_the_persistent_root(self):
        import config

        assert config.resolve_upload_root({"DATA_DIR": "/data"}) == "/data"
        assert config.resolve_upload_root({"UPLOAD_ROOT": "/mnt/x", "DATA_DIR": "/data"}) == "/mnt/x"

    def test_upload_root_stays_in_the_static_folder_without_a_disk(self):
        import config

        assert config.resolve_upload_root({}) == os.path.join(config.basedir, "static")

    def test_backups_live_under_the_data_dir(self):
        import config
        from services.backup_service import BackupService

        assert os.path.join(config.DATA_DIR, "backups") == config.BACKUP_DIR
        # The service and the configuration must not drift: one directory.
        assert BackupService.BACKUP_DIR == config.BACKUP_DIR


class TestMasterSeedOnThePersistentRoot:
    def test_the_master_seed_file_is_on_the_persistent_root(self):
        """The daily owner key is "<seed>@YYYY@MM@DD" - the seed decides it.

        The seed file lives in the persistent root, so a redeploy does not
        regenerate it and invalidate the key the operator already holds.
        """
        import config
        from utils.master_login import _master_seed_file_path

        assert _master_seed_file_path().startswith(config.DATA_DIR)


class TestUploadsGoToThePersistentRoot:
    def test_uploaded_file_is_written_to_the_configured_root(self, app, tmp_path):
        from utils.helpers import save_uploaded_file

        with app.app_context():
            app.config["UPLOAD_ROOT"] = str(tmp_path)
            storage = FileStorage(io.BytesIO(b"hello"), filename="note.txt")
            relative = save_uploaded_file(storage, "uploads/products", allowed_extensions={"txt"})

        assert relative.endswith(".txt")
        written = tmp_path / relative
        assert written.exists(), f"{written} was not written to the persistent root"
        assert written.read_bytes() == b"hello"

    def test_the_stored_path_still_points_at_the_static_url(self, app, tmp_path):
        """The database keeps the relative path, so no URL has to change."""
        from utils.helpers import save_uploaded_file

        with app.app_context():
            app.config["UPLOAD_ROOT"] = str(tmp_path)
            storage = FileStorage(io.BytesIO(b"hello"), filename="note.txt")
            relative = save_uploaded_file(storage, "uploads/products", allowed_extensions={"txt"})

        assert not relative.startswith("/")
        assert ".." not in relative.split("/")


class TestPersistentUploadServing:
    def test_static_url_serves_from_the_persistent_root(self, tmp_path):
        from flask import Flask

        from app.factory import _install_persistent_upload_serving

        static_dir = tmp_path / "static"
        (static_dir / "uploads" / "tenants" / "5").mkdir(parents=True)
        (static_dir / "app.css").write_text("body{}")

        persistent = tmp_path / "data"
        (persistent / "uploads" / "tenants" / "5").mkdir(parents=True)
        (persistent / "uploads" / "tenants" / "5" / "logo.png").write_bytes(b"\x89PNG\r\n")

        app = Flask(__name__, static_folder=str(static_dir))
        app.config["UPLOAD_ROOT"] = str(persistent)
        _install_persistent_upload_serving(app)

        client = app.test_client()
        resp = client.get("/static/uploads/tenants/5/logo.png")
        assert resp.status_code == 200
        assert resp.data == b"\x89PNG\r\n"

        # The application's own assets still come from the static folder.
        assert client.get("/static/app.css").status_code == 200

    def test_a_missing_upload_still_404s(self, tmp_path):
        from flask import Flask

        from app.factory import _install_persistent_upload_serving

        static_dir = tmp_path / "static"
        (static_dir / "uploads").mkdir(parents=True)
        persistent = tmp_path / "data"
        persistent.mkdir()

        app = Flask(__name__, static_folder=str(static_dir))
        app.config["UPLOAD_ROOT"] = str(persistent)
        _install_persistent_upload_serving(app)

        assert app.test_client().get("/static/uploads/nope.png").status_code == 404

    def test_without_a_persistent_root_nothing_changes(self, tmp_path):
        from flask import Flask

        from app.factory import _install_persistent_upload_serving

        static_dir = tmp_path / "static"
        (static_dir / "uploads").mkdir(parents=True)
        (static_dir / "uploads" / "x.txt").write_text("local")

        app = Flask(__name__, static_folder=str(static_dir))
        app.config["UPLOAD_ROOT"] = str(static_dir)
        _install_persistent_upload_serving(app)

        resp = app.test_client().get("/static/uploads/x.txt")
        assert resp.status_code == 200
        assert resp.data == b"local"
