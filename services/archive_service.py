from datetime import datetime, timezone
from flask import current_app
from flask_login import current_user
from extensions import db
from models import ArchivedRecord


class ArchiveService:

    @staticmethod
    def archive_record(table_name, record, reason=None, commit=True):
        try:
            if hasattr(record, 'to_dict'):
                data = record.to_dict()
            else:
                data = {c.name: getattr(record, c.name) for c in record.__table__.columns}

            tenant_id = getattr(record, 'tenant_id', None)
            if tenant_id is None:
                raise ValueError(f'Cannot archive {table_name} #{record.id}: record has no tenant_id')

            archived = ArchivedRecord(
                tenant_id=tenant_id,
                table_name=table_name,
                record_id=record.id,
                data=data,
                archived_by=current_user.id if current_user.is_authenticated else None,
                reason=reason
            )

            db.session.add(archived)

            if commit:
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                    raise

                current_app.logger.info(f'Archived: {table_name} #{record.id}')
            else:
                db.session.flush()
                current_app.logger.info(f'Archived (Pending Commit): {table_name} #{record.id}')

            return archived

        except Exception as e:
            if commit:
                db.session.rollback()
            current_app.logger.error(f'Archive failed: {e}')
            raise

    @staticmethod
    def soft_delete(record):
        record.is_active = False
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise


    @staticmethod
    def hard_delete(table_name, record, archive_first=True):
        try:
            if archive_first:
                ArchiveService.archive_record(table_name, record, reason='Hard Delete')

            db.session.delete(record)
            db.session.commit()

            current_app.logger.warning(f'Hard deleted: {table_name} #{record.id}')

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Hard delete failed: {e}')
            raise

    ARCHIVE_MODEL_MAP = {
        "sales": None,
        "purchases": None,
        "payments": None,
        "receipts": None,
        "cheques": None,
        "expenses": None,
    }

    @staticmethod
    def restore_record(archived_record):
        try:
            if ArchiveService.ARCHIVE_MODEL_MAP.get(archived_record.table_name) is None:
                ArchiveService._init_archive_model_map()

            model_class = ArchiveService.ARCHIVE_MODEL_MAP.get(archived_record.table_name)

            if not model_class:
                raise ValueError(f'Model not found for table: {archived_record.table_name}')

            # Tenant scope check
            from flask_login import current_user
            from utils.tenanting import get_active_tenant_id
            tid = get_active_tenant_id(current_user)
            if tid is not None and archived_record.tenant_id != tid:
                raise PermissionError(f'Cannot restore {archived_record.table_name} #{archived_record.record_id}: tenant mismatch')

            existing = model_class.query.get(archived_record.record_id)

            if existing:
                existing.is_active = True
                db.session.commit()
                current_app.logger.info(f'Restored: {archived_record.table_name} #{archived_record.record_id}')
                return existing

            raise ValueError('Cannot restore: Record not found in database')

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Restore failed: {e}')
            raise

    @staticmethod
    def _init_archive_model_map():
        from models import Sale, Purchase, Payment, Receipt, Cheque, Expense
        ArchiveService.ARCHIVE_MODEL_MAP.update({
            "sales": Sale,
            "purchases": Purchase,
            "payments": Payment,
            "receipts": Receipt,
            "cheques": Cheque,
            "expenses": Expense,
        })

    @staticmethod
    def get_archived_records_query(table_name=None):
        query = ArchivedRecord.query
        if table_name:
            query = query.filter_by(table_name=table_name)
        return query.order_by(ArchivedRecord.archived_at.desc())

    @staticmethod
    def get_archived_records(table_name=None, limit=100):
        query = ArchivedRecord.query

        if table_name:
            query = query.filter_by(table_name=table_name)

        return query.order_by(ArchivedRecord.archived_at.desc()).limit(limit).all()

    @staticmethod
    def cleanup_old_archives(days=365):
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        old_archives = ArchivedRecord.query.filter(
            ArchivedRecord.archived_at < cutoff,
            ArchivedRecord.can_restore == False
        ).all()

        count = 0
        for archive in old_archives:
            db.session.delete(archive)
            count += 1

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise


        current_app.logger.info(f'Cleaned up {count} old archives')

        return count

