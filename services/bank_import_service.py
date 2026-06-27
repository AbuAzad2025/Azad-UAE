import hashlib
from datetime import datetime, timezone
from extensions import db
from models.bank_reconciliation import BankStatementLine
import io

class BankImportService:
    @staticmethod
    def _generate_hash(tenant_id, bank_account_id, date, amount, reference, description):
        data = f"{tenant_id}:{bank_account_id}:{date}:{amount}:{reference}:{description}"
        return hashlib.sha256(data.encode('utf-8')).hexdigest()

    @staticmethod
    def import_bank_statement(tenant_id, bank_account_id, user_id, filename, file_content, format='ofx'):
        """
        Parse and import bank statement lines
        """
        # This is a foundation - actual parsing needs robust libraries
        # In a real scenario, use libraries like `ofxtools` or `mt940`
        lines = []
        
        # Placeholder for actual parser logic
        # For this foundation, we simulate parsing by creating a single line
        parsed_data = [{'date': datetime.now().date(), 'amount': 100, 'ref': 'test', 'desc': 'test'}]
        
        for item in parsed_data:
            line_hash = BankImportService._generate_hash(
                tenant_id, bank_account_id, item['date'], item['amount'], item['ref'], item['desc']
            )
            
            # Check for duplicates
            exists = BankStatementLine.query.filter_by(
                tenant_id=tenant_id,
                bank_account_id=bank_account_id,
                reference=item['ref']
                # In production, also use the hash if you store it
            ).first()
            
            if exists:
                continue
                
            line = BankStatementLine(
                tenant_id=tenant_id,
                bank_account_id=bank_account_id,
                statement_date=datetime.now().date(),
                transaction_date=item['date'],
                reference=item['ref'],
                description=item['desc'],
                amount=item['amount'],
                source_filename=filename,
                created_by=user_id,
                status='imported'
            )
            db.session.add(line)
            lines.append(line)
            
        db.session.commit()
        return lines

    @staticmethod
    def suggest_matches(tenant_id, bank_account_id):
        """
        Logic to suggest matches against existing receipts/payments
        """
        # Placeholder for matching logic
        pass

    @staticmethod
    def confirm_match(line_id, journal_entry_id, user_id, tenant_id=None):
        """
        Manually confirm a match. When tenant_id is supplied, enforces tenant isolation.
        """
        line = BankStatementLine.query.get(line_id)
        if not line:
            return False
        if tenant_id is not None and int(line.tenant_id) != int(tenant_id):
            return False
        line.status = 'matched'
        line.matched_journal_entry_id = journal_entry_id
        line.matched_at = datetime.now(timezone.utc)
        line.matched_by = user_id
        db.session.commit()
        return True
