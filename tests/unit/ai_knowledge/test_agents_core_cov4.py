"""Coverage for ai_knowledge/agents_core.py line 124 (_env_mtime cache-miss hit)."""

from __future__ import annotations

import os
from unittest.mock import patch

from ai_knowledge.agents_core import _env_mtime


class TestCov4EnvMtime:
    def test_returns_real_mtime_when_env_exists(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("GROQ_API_KEY=dummy\n", encoding="utf-8")
        with patch("dotenv.find_dotenv", return_value=str(env_file)):
            assert _env_mtime() == os.path.getmtime(str(env_file))

    def test_returns_none_when_env_missing(self, tmp_path):
        missing = tmp_path / "no-such.env"
        with patch("dotenv.find_dotenv", return_value=str(missing)):
            assert _env_mtime() is None
