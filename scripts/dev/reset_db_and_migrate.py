#!/usr/bin/env python3
"""Deprecated — use: flask reset-platform-db --yes"""
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
os.chdir(ROOT)
sys.exit(
    subprocess.call(
        [sys.executable, '-m', 'flask', 'reset-platform-db', '--yes'],
        cwd=ROOT,
        env={**os.environ, 'FLASK_APP': 'app:create_app', 'SKIP_SYSTEM_INTEGRITY': '1'},
    )
)
