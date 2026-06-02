import os
os.environ['DATABASE_URL'] = 'postgresql+psycopg2://postgres:123@localhost:5432/azad_uae'
from sqlalchemy import create_engine, text
engine = create_engine(os.environ['DATABASE_URL'])
with engine.connect() as conn:
    # Customer balances (receivables)
    print('=== CUSTOMER RECEIVABLES (owe us) ===')
    r = conn.execute(text('SELECT name, balance, total_purchases FROM customers WHERE balance > 0 ORDER BY balance DESC LIMIT 10'))
    for row in r:
        print(f'{row[0]:30s}: Balance={row[1]:10.2f}, Total={row[2]:10.2f}')
    
    print('\n=== CUSTOMER CREDITS (we owe them) ===')
    r = conn.execute(text('SELECT name, balance FROM customers WHERE balance < 0 ORDER BY balance LIMIT 5'))
    for row in r:
        print(f'{row[0]:30s}: Balance={row[1]:10.2f}')
    
    # Supplier balances (payables)
    print('\n=== SUPPLIER PAYABLES (we owe them) ===')
    r = conn.execute(text('SELECT name, total_purchases_aed, total_paid_aed FROM suppliers WHERE (total_purchases_aed - total_paid_aed) > 0 ORDER BY (total_purchases_aed - total_paid_aed) DESC LIMIT 10'))
    for row in r:
        balance = (row[1] or 0) - (row[2] or 0)
        print(f'{row[0]:30s}: Purchased={row[1]:10.2f}, Paid={row[2]:10.2f}, Balance={balance:10.2f}')
    
    # Cheques by status
    print('\n=== CHEQUES BY STATUS ===')
    r = conn.execute(text('SELECT status, COUNT(*) FROM cheques GROUP BY status'))
    for row in r:
        print(f'{row[0]:15s}: {row[1]}')
    
    # Cheques by type
    print('\n=== CHEQUES BY TYPE ===')
    r = conn.execute(text('SELECT cheque_type, COUNT(*) FROM cheques GROUP BY cheque_type'))
    for row in r:
        print(f'{row[0]:15s}: {row[1]}')
    
    # Overdue cheques
    print('\n=== OVERDUE CHEQUES ===')
    r = conn.execute(text("SELECT COUNT(*) FROM cheques WHERE due_date < CURRENT_DATE AND status = 'pending'"))
    print(f'Overdue pending cheques: {r.scalar()}')
    
    # Total amounts
    print('\n=== TOTAL AMOUNTS ===')
    r = conn.execute(text('SELECT SUM(balance) FROM customers WHERE balance > 0'))
    print(f'Total customer receivables: {r.scalar() or 0:.2f}')
    
    r = conn.execute(text('SELECT SUM(total_purchases_aed - total_paid_aed) FROM suppliers WHERE (total_purchases_aed - total_paid_aed) > 0'))
    print(f'Total supplier payables: {r.scalar() or 0:.2f}')
    
    r = conn.execute(text("SELECT SUM(amount) FROM cheques WHERE status = 'pending'"))
    print(f'Total pending cheques: {r.scalar() or 0:.2f}')
    
    r = conn.execute(text("SELECT SUM(amount) FROM cheques WHERE status = 'bounced'"))
    print(f'Total bounced cheques: {r.scalar() or 0:.2f}')
