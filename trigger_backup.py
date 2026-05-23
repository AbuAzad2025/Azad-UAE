import os
import sys
import logging
from datetime import datetime

# Set path to pg_dump
os.environ['PG_DUMP_PATH'] = r"C:\Program Files\PostgreSQL\18\bin\pg_dump.exe"

# Add project root to path
sys.path.append(os.getcwd())

from app import create_app
from services.backup_service import BackupService
from export_json_db import export_db_to_json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    app = create_app()
    with app.app_context():
        print("1. Starting SQL Backup using pg_dump...")
        try:
            backup = BackupService.create_backup(manual=True, description="User requested backup")
            if backup:
                print(f"✅ SQL Backup created successfully: {backup['filename']}")
                print(f"   Path: {backup['path']}")
                print(f"   Size: {backup['size_mb']} MB")
            else:
                print("❌ SQL Backup failed. Check logs.")
        except Exception as e:
            print(f"❌ Error during SQL backup: {e}")

        print("\n2. Starting JSON Export...")
        try:
            json_file = export_db_to_json()
            if json_file:
                print(f"✅ JSON Export created successfully: {json_file}")
        except Exception as e:
            print(f"❌ Error during JSON export: {e}")

if __name__ == "__main__":
    main()
