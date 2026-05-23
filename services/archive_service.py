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
            
            archived = ArchivedRecord(
                table_name=table_name,
                record_id=record.id,
                data=data,
                archived_by=current_user.id if current_user.is_authenticated else None,
                reason=reason
            )
            
            db.session.add(archived)
            
            if commit:
                db.session.commit()
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
        db.session.commit()
    
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
    
    @staticmethod
    def restore_record(archived_record):
        try:
            model_class = db.Model.registry._class_registry.get(archived_record.table_name)
            
            if not model_class:
                raise ValueError(f'Model not found: {archived_record.table_name}')
            
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
        
        db.session.commit()
        
        current_app.logger.info(f'Cleaned up {count} old archives')
        
        return count

