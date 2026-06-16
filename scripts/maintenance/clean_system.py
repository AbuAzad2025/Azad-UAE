"""
System cleanup: cache, old logs, and temporary files.
Run this periodically to keep the project clean.
"""

import os
import sys
import shutil
from datetime import datetime

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), '..', '..')
PROJECT_ROOT = os.path.abspath(PROJECT_ROOT)

def log(msg):
    print(f"  {msg}")

def delete_directory(path):
    """Delete a directory and all its contents."""
    try:
        shutil.rmtree(path)
        return True
    except Exception as e:
        print(f"    ERROR deleting {path}: {e}")
        return False

def truncate_file(path):
    """Truncate a file to zero bytes."""
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(f"# Truncated by cleanup script on {datetime.now().isoformat()}\n")
        return True
    except Exception as e:
        print(f"    ERROR truncating {path}: {e}")
        return False

def delete_file(path):
    """Delete a file."""
    try:
        os.remove(path)
        return True
    except Exception as e:
        print(f"    ERROR deleting {path}: {e}")
        return False

def main():
    print("=" * 60)
    print("SYSTEM CLEANUP")
    print("=" * 60)
    print(f"Project root: {PROJECT_ROOT}")
    print()

    total_freed = 0
    deleted_dirs = 0
    deleted_files = 0
    truncated_files = 0

    # ── 1. Delete __pycache__ directories ──
    print("[1] Deleting __pycache__ directories...")
    pycache_dirs = []
    for root, dirs, files in os.walk(PROJECT_ROOT):
        for d in dirs:
            if d == '__pycache__':
                pycache_dirs.append(os.path.join(root, d))

    for path in pycache_dirs:
        size = sum(os.path.getsize(os.path.join(dirpath, f)) for dirpath, _, filenames in os.walk(path) for f in filenames)
        if delete_directory(path):
            total_freed += size
            deleted_dirs += 1
            log(f"Deleted: {os.path.relpath(path, PROJECT_ROOT)} ({size:,} bytes)")

    print(f"  Deleted {deleted_dirs} __pycache__ directories")
    print()

    # ── 2. Delete .pytest_cache ──
    print("[2] Deleting .pytest_cache...")
    pytest_cache = os.path.join(PROJECT_ROOT, '.pytest_cache')
    if os.path.exists(pytest_cache):
        if delete_directory(pytest_cache):
            log(f"Deleted: .pytest_cache")
            deleted_dirs += 1
    else:
        log("Not found")
    print()

    # ── 3. Truncate large log files in logs/ ──
    print("[3] Truncating large log files...")
    logs_dir = os.path.join(PROJECT_ROOT, 'logs')
    log_files = {
        'app.log': 'Application log',
        'performance.log': 'Performance log',
        'security.log': 'Security log',
    }

    for filename, desc in log_files.items():
        path = os.path.join(logs_dir, filename)
        if os.path.exists(path):
            size = os.path.getsize(path)
            if truncate_file(path):
                total_freed += size
                truncated_files += 1
                log(f"Truncated: {filename} ({size:,} bytes) — {desc}")

    # errors.log is small, keep it
    errors_log = os.path.join(logs_dir, 'errors.log')
    if os.path.exists(errors_log):
        size = os.path.getsize(errors_log)
        log(f"Kept: errors.log ({size:,} bytes) — too small to clean")

    print(f"  Truncated {truncated_files} log files")
    print()

    # ── 4. Delete old instance/ log files ──
    print("[4] Cleaning old instance/ log files...")
    instance_logs = [
        '.security_audit.log',
        'flask_err.log',
        'flask_out.log',
        'flask_server.log',
    ]
    instance_dir = os.path.join(PROJECT_ROOT, 'instance')

    for filename in instance_logs:
        path = os.path.join(instance_dir, filename)
        if os.path.exists(path):
            size = os.path.getsize(path)
            if delete_file(path):
                total_freed += size
                deleted_files += 1
                log(f"Deleted: instance/{filename} ({size:,} bytes)")

    print(f"  Deleted {deleted_files} old instance log files")
    print()

    # ── 5. Clean .codegraph/ cache ──
    print("[5] Cleaning .codegraph/ cache...")
    codegraph_dir = os.path.join(PROJECT_ROOT, '.codegraph')
    daemon_log = os.path.join(codegraph_dir, 'daemon.log')
    codegraph_db = os.path.join(codegraph_dir, 'codegraph.db')

    if os.path.exists(daemon_log):
        size = os.path.getsize(daemon_log)
        if truncate_file(daemon_log):
            total_freed += size
            truncated_files += 1
            log(f"Truncated: .codegraph/daemon.log ({size:,} bytes)")

    if os.path.exists(codegraph_db):
        size = os.path.getsize(codegraph_db)
        if delete_file(codegraph_db):
            total_freed += size
            deleted_files += 1
            log(f"Deleted: .codegraph/codegraph.db ({size:,} bytes) — IDE analysis cache")

    print()

    # ── Summary ──
    print("=" * 60)
    print("CLEANUP SUMMARY")
    print("=" * 60)
    print(f"  Directories deleted:  {deleted_dirs}")
    print(f"  Files deleted:        {deleted_files}")
    print(f"  Files truncated:      {truncated_files}")
    print(f"  Total space freed:    {total_freed / (1024*1024):.1f} MB")
    print("=" * 60)

if __name__ == '__main__':
    main()
