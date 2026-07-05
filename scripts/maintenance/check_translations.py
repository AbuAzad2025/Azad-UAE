import sys, os
sys.path.insert(0, r'D:\Data\karaj\UAE\Azad-UAE')
from utils.i18n import TRANSLATIONS

keys = ['Users', 'User', 'Customers', 'Customer', 'Sales', 'Sale', 'Purchases', 'Purchase', 'Products', 'Product', 'Reports', 'Report', 'Settings', 'Dashboard', 'View', 'All', 'Show', 'List', 'Backups', 'Warehouse', 'Inventory', 'Expenses', 'Expense', 'Payments', 'Payment', 'Cheques', 'Cheque', 'Ledger', 'Branches', 'Branch', 'Store', 'Company', 'System', 'Health', 'Performance', 'Security', 'Alert', 'Log', 'Action', 'Add', 'New', 'Edit', 'Delete', 'Save', 'Cancel', 'Search', 'Filter', 'Export', 'Print', 'Status', 'Active', 'Inactive', 'Pending', 'Confirmed', 'Rejected', 'Yes', 'No', 'Name', 'Email', 'Phone', 'Address', 'Date', 'Amount', 'Quantity', 'Price', 'Total', 'Discount', 'Tax', 'Balance', 'Code', 'Today', 'Loading', 'Details', 'Update', 'Submit', 'Confirm', 'Close']

with open('translation_keys.txt', 'w', encoding='utf-8') as f:
    for k in keys:
        if k in TRANSLATIONS:
            ar = TRANSLATIONS[k]['ar']
            f.write(f'{k}: {ar}\n')

print('Wrote translation_keys.txt')
