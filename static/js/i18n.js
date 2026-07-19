/**
 * 🌍 JavaScript Internationalization
 * نظام الترجمة في JavaScript
 */

/* global Swal */

// Get current language from session/cookie
function getCurrentLanguage() {
	// Try to get from body data attribute
	return document.documentElement.lang || "ar";
}

// Translation dictionary
const translations = {
	// Common
	Save: { ar: "حفظ", en: "Save" },
	Cancel: { ar: "إلغاء", en: "Cancel" },
	Delete: { ar: "حذف", en: "Delete" },
	Edit: { ar: "تعديل", en: "Edit" },
	View: { ar: "عرض", en: "View" },
	Back: { ar: "رجوع", en: "Back" },
	Search: { ar: "بحث", en: "Search" },
	Loading: { ar: "جاري التحميل...", en: "Loading..." },
	Processing: { ar: "جاري المعالجة...", en: "Processing..." },

	// Messages
	Success: { ar: "نجاح", en: "Success" },
	Error: { ar: "خطأ", en: "Error" },
	Warning: { ar: "تحذير", en: "Warning" },
	"Are you sure?": { ar: "هل أنت متأكد؟", en: "Are you sure?" },
	"This action cannot be undone": {
		ar: "لا يمكن التراجع عن هذا الإجراء",
		en: "This action cannot be undone",
	},
	"Saved successfully": { ar: "تم الحفظ بنجاح", en: "Saved successfully" },
	"Deleted successfully": { ar: "تم الحذف بنجاح", en: "Deleted successfully" },
	"Updated successfully": {
		ar: "تم التحديث بنجاح",
		en: "Updated successfully",
	},
	"An error occurred": { ar: "حدث خطأ", en: "An error occurred" },
	"Please try again": { ar: "يرجى المحاولة مرة أخرى", en: "Please try again" },

	// Actions
	Confirm: { ar: "تأكيد", en: "Confirm" },
	Yes: { ar: "نعم", en: "Yes" },
	No: { ar: "لا", en: "No" },
	OK: { ar: "موافق", en: "OK" },
	Close: { ar: "إغلاق", en: "Close" },

	// Validation
	"This field is required": {
		ar: "هذا الحقل مطلوب",
		en: "This field is required",
	},
	"Please enter a valid email": {
		ar: "يرجى إدخال بريد إلكتروني صحيح",
		en: "Please enter a valid email",
	},
	"Please enter a valid phone number": {
		ar: "يرجى إدخال رقم هاتف صحيح",
		en: "Please enter a valid phone number",
	},
	"Please select an option": {
		ar: "يرجى اختيار خيار",
		en: "Please select an option",
	},

	// DataTables
	Show: { ar: "عرض", en: "Show" },
	entries: { ar: "سجل", en: "entries" },
	"Search:": { ar: "بحث:", en: "Search:" },
	Showing: { ar: "عرض", en: "Showing" },
	to: { ar: "إلى", en: "to" },
	of: { ar: "من", en: "of" },
	"entries (filtered from": {
		ar: "سجل (تمت فلترته من",
		en: "entries (filtered from",
	},
	"total entries)": { ar: "إجمالي السجلات)", en: "total entries)" },
	"No data available": { ar: "لا توجد بيانات", en: "No data available" },
	"No records found": { ar: "لم يتم العثور على سجلات", en: "No records found" },
	First: { ar: "الأولى", en: "First" },
	Last: { ar: "الأخيرة", en: "Last" },
	Next: { ar: "التالي", en: "Next" },
	Previous: { ar: "السابق", en: "Previous" },

	// New clean keys
	"Save Changes": { ar: "حفظ التعديلات", en: "Save Changes" },
	Changes: { ar: "تعديلات", en: "Changes" },
	Totals: { ar: "الإجماليات", en: "Totals" },
	"Edit Account": { ar: "تعديل الحساب", en: "Edit Account" },
	"Account Code": { ar: "رمز الحساب", en: "Account Code" },
	"Account Name": { ar: "اسم الحساب", en: "Account Name" },
	"Account Type": { ar: "نوع الحساب", en: "Account Type" },
	"Parent Account": { ar: "الحساب الأب", en: "Parent Account" },
	"Header Account": { ar: "حساب رئيسي", en: "Header Account" },
	"Name in Arabic": { ar: "الاسم بالعربي", en: "Name in Arabic" },
	"Name in English": { ar: "الاسم بالإنجليزي", en: "Name in English" },
	"Cannot Change Account Code": {
		ar: "لا يمكن تغيير رمز الحساب",
		en: "Cannot Change Account Code",
	},
	"Back to Reports": { ar: "العودة للتقارير", en: "Back to Reports" },
	"Back to Dashboard": { ar: "العودة للوحة التحكم", en: "Back to Dashboard" },
	"Filter Date": { ar: "تصفية التاريخ", en: "Filter Date" },
	"Update Report": { ar: "تحديث التقرير", en: "Update Report" },
	"Summary Balance": { ar: "ملخص التوازن", en: "Summary Balance" },
	"Total Assets": { ar: "إجمالي الأصول", en: "Total Assets" },
	"Total Liabilities": { ar: "إجمالي الخصوم", en: "Total Liabilities" },
	"Assets and Liabilities": {
		ar: "الأصول والخصوم",
		en: "Assets and Liabilities",
	},
	"Balance Sheet": { ar: "الميزانية العمومية", en: "Balance Sheet" },
	"Page Not Found": {
		ar: "عذراً، الصفحة التي تبحث عنها غير موجودة أو تم نقلها.",
		en: "Sorry, the page you are looking for does not exist or has been moved.",
	},
	"Server Error": {
		ar: "يرجى المحاولة لاحقاً. إذا استمرت المشكلة اتصل بالدعم.",
		en: "Please try again later. If the problem persists, contact support.",
	},
	"Access Denied": {
		ar: "عذراً، ليس لديك صلاحيات كافية للوصول إلى هذه الصفحة.",
		en: "Sorry, you do not have sufficient permissions to access this page.",
	},
	"Entry Number": { ar: "رقم القيد", en: "Entry Number" },
	"Entry Details": { ar: "تفاصيل القيد", en: "Entry Details" },
	"Debit Total": { ar: "إجمالي المدين", en: "Debit Total" },
	"Credit Total": { ar: "إجمالي الدائن", en: "Credit Total" },
	"Account Statement": { ar: "كشف الحساب", en: "Account Statement" },
	"Opening Balance": { ar: "رصيد الافتتاح", en: "Opening Balance" },
	Description: { ar: "الوصف", en: "Description" },
	"Basic Info": { ar: "معلومات أساسية", en: "Basic Info" },
	"Additional Info": { ar: "معلومات إضافية", en: "Additional Info" },
	"User Name": { ar: "اسم المستخدم", en: "User Name" },
	"Full Name": { ar: "الاسم الكامل", en: "Full Name" },
	"Created Date": { ar: "تاريخ الإنشاء", en: "Created Date" },
	"Last Seen": { ar: "آخر ظهور", en: "Last Seen" },
	"Tax Number": { ar: "الرقم الضريبي", en: "Tax Number" },
	"System Info": { ar: "معلومات النظام", en: "System Info" },
	"Confirm Delete": { ar: "تأكيد الحذف", en: "Confirm Delete" },
	"Delete Account": { ar: "حذف الحساب", en: "Delete Account" },
	"Account Tree": { ar: "شجرة الحسابات", en: "Account Tree" },
	"New Account": { ar: "حساب جديد", en: "New Account" },
	"All Accounts": { ar: "جميع الحسابات", en: "All Accounts" },
	"No Data Available": { ar: "لا توجد بيانات", en: "No Data Available" },
	"Thank You": { ar: "شكراً لكم", en: "Thank You" },
	"Thank You For Your Business": {
		ar: "شكراً لتعاملكم الكريم معنا",
		en: "Thank You For Your Business",
	},
	"Income Statement": { ar: "قائمة الدخل", en: "Income Statement" },
	"Net Income": { ar: "صافي الدخل", en: "Net Income" },
	Revenue: { ar: "الإيرادات", en: "Revenue" },
	Expenses: { ar: "المصروفات", en: "Expenses" },
	"Cash Flow": { ar: "التدفقات النقدية", en: "Cash Flow" },
	"Operating Activities": {
		ar: "الأنشطة التشغيلية",
		en: "Operating Activities",
	},
	"Investing Activities": {
		ar: "الأنشطة الاستثمارية",
		en: "Investing Activities",
	},
	"Financing Activities": {
		ar: "الأنشطة التمويلية",
		en: "Financing Activities",
	},
	"Net Cash from Operating": {
		ar: "صافي التدفق من الأنشطة التشغيلية",
		en: "Net Cash from Operating",
	},
	"Net Cash from Investing": {
		ar: "صافي التدفق من الأنشطة الاستثمارية",
		en: "Net Cash from Investing",
	},
	"Net Cash from Financing": {
		ar: "صافي التدفق من الأنشطة التمويلية",
		en: "Net Cash from Financing",
	},
	"Net Change in Cash": {
		ar: "صافي التغير في النقد",
		en: "Net Change in Cash",
	},
	"Cash at Start": { ar: "النقد في بداية الفترة", en: "Cash at Start" },
	"Cash at End": { ar: "النقد في نهاية الفترة", en: "Cash at End" },
	"Aging Analysis": { ar: "تحليل الأعمار المدينة", en: "Aging Analysis" },
	"0-30 Days": { ar: "0-30 يوم", en: "0-30 Days" },
	"31-60 Days": { ar: "31-60 يوم", en: "31-60 Days" },
	"61-90 Days": { ar: "61-90 يوم", en: "61-90 Days" },
	"91-120 Days": { ar: "91-120 يوم", en: "91-120 Days" },
	"Over 120 Days": { ar: "+120 يوم", en: "Over 120 Days" },
	"Total Column": { ar: "الإجمالي", en: "Total Column" },
	"Code Column": { ar: "الرمز", en: "Code Column" },
	"Name Column": { ar: "الاسم", en: "Name Column" },
	"Type Column": { ar: "النوع", en: "Type Column" },
	"Level Column": { ar: "المستوى", en: "Level Column" },
	"Balance Column": { ar: "الرصيد", en: "Balance Column" },
	"Status Column": { ar: "الحالة", en: "Status Column" },
	"Actions Header": { ar: "الإجراءات", en: "Actions Header" },
	"Edit Action": { ar: "تعديل", en: "Edit Action" },
	"Delete Action": { ar: "حذف", en: "Delete Action" },
	"View Action": { ar: "عرض", en: "View Action" },
	"Active Status": { ar: "نشط", en: "Active Status" },
	"Inactive Status": { ar: "غير نشط", en: "Inactive Status" },
	"Main Account": { ar: "رئيسي", en: "Main Account" },
	"Sub Account": { ar: "فرعي", en: "Sub Account" },
	"Credit Memo": { ar: "إشعار دائن", en: "Credit Memo" },
	"Debit Memo": { ar: "إشعار مدين", en: "Debit Memo" },
	Refund: { ar: "مرتجع", en: "Refund" },
	"Payment Voucher": { ar: "سند دفع", en: "Payment Voucher" },
	"Receipt Voucher": { ar: "سند قبض", en: "Receipt Voucher" },
	"Exchange Voucher": { ar: "سند صرف", en: "Exchange Voucher" },
	"Voucher Number": { ar: "رقم السند", en: "Voucher Number" },
	"Voucher Date": { ar: "تاريخ السند", en: "Voucher Date" },
	"Voucher Type": { ar: "نوع السند", en: "Voucher Type" },
	"Voucher Details": { ar: "تفاصيل السند", en: "Voucher Details" },
	"Exchange Rate": { ar: "سعر الصرف", en: "Exchange Rate" },
	Currency: { ar: "العملة", en: "Currency" },
	Amount: { ar: "المبلغ", en: "Amount" },
	"Net Amount": { ar: "المبلغ الصافي", en: "Net Amount" },
	"Tax Amount": { ar: "مبلغ الضريبة", en: "Tax Amount" },
	"Discount Amount": { ar: "مبلغ الخصم", en: "Discount Amount" },
	"Total Amount": { ar: "المبلغ الإجمالي", en: "Total Amount" },
	"Payment Method": { ar: "طريقة الدفع", en: "Payment Method" },
	"Payment Date": { ar: "تاريخ الدفع", en: "Payment Date" },
	"Payment Status": { ar: "حالة الدفع", en: "Payment Status" },
	"Payment Details": { ar: "تفاصيل الدفع", en: "Payment Details" },
	"Payment Reference": { ar: "مرجع الدفع", en: "Payment Reference" },
	"Received From": { ar: "مستلم من", en: "Received From" },
	"Paid To": { ar: "مدفوع إلى", en: "Paid To" },
	"Received Amount": { ar: "المبلغ المستلم", en: "Received Amount" },
	"Paid Amount": { ar: "المبلغ المدفوع", en: "Paid Amount" },
	"Pending Amount": { ar: "المبلغ المعلق", en: "Pending Amount" },
	"Overdue Amount": { ar: "المبلغ المتأخر", en: "Overdue Amount" },
	"Invoice Number": { ar: "رقم الفاتورة", en: "Invoice Number" },
	"Invoice Date": { ar: "تاريخ الفاتورة", en: "Invoice Date" },
	"Invoice Type": { ar: "نوع الفاتورة", en: "Invoice Type" },
	"Invoice Details": { ar: "تفاصيل الفاتورة", en: "Invoice Details" },
	"Invoice Status": { ar: "حالة الفاتورة", en: "Invoice Status" },
	"Invoice Total": { ar: "إجمالي الفاتورة", en: "Invoice Total" },
	"Invoice Items": { ar: "أصناف الفاتورة", en: "Invoice Items" },
	"Item Name": { ar: "اسم الصنف", en: "Item Name" },
	"Item Code": { ar: "رمز الصنف", en: "Item Code" },
	"Unit Price": { ar: "سعر الوحدة", en: "Unit Price" },
	Quantity: { ar: "الكمية", en: "Quantity" },
	"Line Total": { ar: "إجمالي السطر", en: "Line Total" },
	"Line Discount": { ar: "خصم السطر", en: "Line Discount" },
	"Line Tax": { ar: "ضريبة السطر", en: "Line Tax" },
	"Sub Total": { ar: "المجموع الفرعي", en: "Sub Total" },
	"Grand Total": { ar: "المجموع الكلي", en: "Grand Total" },
	"Tax Total": { ar: "إجمالي الضريبة", en: "Tax Total" },
	"Discount Total": { ar: "إجمالي الخصم", en: "Discount Total" },
	"Shipping Cost": { ar: "تكلفة الشحن", en: "Shipping Cost" },
	"Additional Cost": { ar: "تكلفة إضافية", en: "Additional Cost" },
	"Customer Name": { ar: "اسم العميل", en: "Customer Name" },
	"Customer Code": { ar: "رمز العميل", en: "Customer Code" },
	"Customer Details": { ar: "تفاصيل العميل", en: "Customer Details" },
	"Supplier Name": { ar: "اسم المورد", en: "Supplier Name" },
	"Supplier Code": { ar: "رمز المورد", en: "Supplier Code" },
	"Supplier Details": { ar: "تفاصيل المورد", en: "Supplier Details" },
	"Product Name": { ar: "اسم المنتج", en: "Product Name" },
	"Product Code": { ar: "رمز المنتج", en: "Product Code" },
	"Product Details": { ar: "تفاصيل المنتج", en: "Product Details" },
	"Warehouse Name": { ar: "اسم المستودع", en: "Warehouse Name" },
	"Warehouse Details": { ar: "تفاصيل المستودع", en: "Warehouse Details" },
	"Stock Quantity": { ar: "كمية المخزون", en: "Stock Quantity" },
	"Reorder Level": { ar: "حد إعادة الطلب", en: "Reorder Level" },
	"Cost Price": { ar: "سعر التكلفة", en: "Cost Price" },
	"Selling Price": { ar: "سعر البيع", en: "Selling Price" },
	"Profit Margin": { ar: "هامش الربح", en: "Profit Margin" },
	"Transaction Date": { ar: "تاريخ المعاملة", en: "Transaction Date" },
	"Transaction Type": { ar: "نوع المعاملة", en: "Transaction Type" },
	"Transaction Details": { ar: "تفاصيل المعاملة", en: "Transaction Details" },
	"Transaction Number": { ar: "رقم المعاملة", en: "Transaction Number" },
	"Reference Number": { ar: "رقم المرجع", en: "Reference Number" },
	"Due Date": { ar: "تاريخ الاستحقاق", en: "Due Date" },
	"Notes Column": { ar: "ملاحظات", en: "Notes Column" },
	"Audit Log": { ar: "سجل المراجعة", en: "Audit Log" },
	Timestamp: { ar: "التاريخ والوقت", en: "Timestamp" },
	"User Column": { ar: "المستخدم", en: "User Column" },
	Operation: { ar: "العملية", en: "Operation" },
	"Entity Type": { ar: "النوع", en: "Entity Type" },
	"Entity ID": { ar: "المعرف", en: "Entity ID" },
	"Details Column": { ar: "التفاصيل", en: "Details Column" },
	"IP Column": { ar: "IP", en: "IP Column" },
	"Create Operation": { ar: "إنشاء", en: "Create Operation" },
	"Update Operation": { ar: "تعديل", en: "Update Operation" },
	"Delete Operation": { ar: "حذف", en: "Delete Operation" },
	"View Operation": { ar: "عرض", en: "View Operation" },
	"Login Operation": { ar: "تسجيل دخول", en: "Login Operation" },
	"Logout Operation": { ar: "تسجيل خروج", en: "Logout Operation" },
	"Export Operation": { ar: "تصدير", en: "Export Operation" },
	"Import Operation": { ar: "استيراد", en: "Import Operation" },
	"Print Operation": { ar: "طباعة", en: "Print Operation" },
	"Archive Operation": { ar: "أرشفة", en: "Archive Operation" },
	"Restore Operation": { ar: "استعادة", en: "Restore Operation" },
	"Permission Denied": { ar: "الوصول مرفوض", en: "Permission Denied" },
	"Session Expired": { ar: "انتهت الجلسة", en: "Session Expired" },
	"Invalid Token": { ar: "رمز غير صالح", en: "Invalid Token" },
	"Rate Limited": { ar: "تم تقييد المعدل", en: "Rate Limited" },
	"Server Unavailable": { ar: "الخادم غير متاح", en: "Server Unavailable" },
	"Maintenance Mode": { ar: "وضع الصيانة", en: "Maintenance Mode" },
	"System Update": { ar: "تحديث النظام", en: "System Update" },
	Version: { ar: "الإصدار", en: "Version" },
	"Database Backup": { ar: "نسخة احتياطية", en: "Database Backup" },
	"System Health": { ar: "صحة النظام", en: "System Health" },
	"System Settings": { ar: "إعدادات النظام", en: "System Settings" },
	"User Management": { ar: "إدارة المستخدمين", en: "User Management" },
	"Role Management": { ar: "الأدوار", en: "Role Management" },
	"Permission Management": { ar: "الصلاحيات", en: "Permission Management" },
	"Language Settings": { ar: "إعدادات اللغة", en: "Language Settings" },
	"Notification Settings": {
		ar: "إعدادات الإشعارات",
		en: "Notification Settings",
	},
	"Email Settings": { ar: "إعدادات البريد الإلكتروني", en: "Email Settings" },
	"SMS Settings": { ar: "إعدادات الرسائل النصية", en: "SMS Settings" },
	"Payment Settings": { ar: "إعدادات الدفع", en: "Payment Settings" },
	"Tax Settings": { ar: "إعدادات الضريبة", en: "Tax Settings" },
	"Currency Settings": { ar: "إعدادات العملة", en: "Currency Settings" },
	"Company Settings": { ar: "إعدادات الشركة", en: "Company Settings" },
	"Invoice Settings": { ar: "إعدادات الفواتير", en: "Invoice Settings" },
	"Receipt Settings": { ar: "إعدادات الإيصالات", en: "Receipt Settings" },
	"Report Settings": { ar: "إعدادات التقارير", en: "Report Settings" },
	"Print Settings": { ar: "إعدادات الطباعة", en: "Print Settings" },
	"Backup Settings": { ar: "إعدادات النسخ الاحتياطي", en: "Backup Settings" },
	"Security Settings": { ar: "إعدادات الأمان", en: "Security Settings" },
	"General Settings": { ar: "إعدادات عامة", en: "General Settings" },
	"Advanced Settings": { ar: "إعدادات متقدمة", en: "Advanced Settings" },
	"Account Settings": { ar: "إعدادات الحساب", en: "Account Settings" },
	"Profile Settings": { ar: "إعدادات الملف الشخصي", en: "Profile Settings" },
	"Appearance Settings": { ar: "إعدادات المظهر", en: "Appearance Settings" },
	"Theme Settings": { ar: "إعدادات السمة", en: "Theme Settings" },
	"Layout Settings": { ar: "إعدادات التخطيط", en: "Layout Settings" },
	"Sidebar Settings": { ar: "إعدادات الشريط الجانبي", en: "Sidebar Settings" },
	"Header Settings": { ar: "إعدادات الرأس", en: "Header Settings" },
	"Footer Settings": { ar: "إعدادات التذييل", en: "Footer Settings" },
	"Navigation Settings": { ar: "إعدادات التنقل", en: "Navigation Settings" },
	"Search Settings": { ar: "إعدادات البحث", en: "Search Settings" },
	"Filter Settings": { ar: "إعدادات التصفية", en: "Filter Settings" },
	"Sort Settings": { ar: "إعدادات الترتيب", en: "Sort Settings" },
	"Pagination Settings": { ar: "إعدادات الترقيم", en: "Pagination Settings" },
	"Table Settings": { ar: "إعدادات الجدول", en: "Table Settings" },
	"Form Settings": { ar: "إعدادات النموذج", en: "Form Settings" },
	"Modal Settings": { ar: "إعدادات النافذة المنبثقة", en: "Modal Settings" },
	"Alert Settings": { ar: "إعدادات التنبيه", en: "Alert Settings" },
	"Toast Settings": { ar: "إعدادات الإشعارات المنبثقة", en: "Toast Settings" },
	"Loading Settings": { ar: "إعدادات التحميل", en: "Loading Settings" },
	"Error Page Settings": {
		ar: "إعدادات صفحة الخطأ",
		en: "Error Page Settings",
	},
	"Success Page Settings": {
		ar: "إعدادات صفحة النجاح",
		en: "Success Page Settings",
	},
	"Not Found Page": { ar: "صفحة غير موجودة", en: "Not Found Page" },
	"Error Page": { ar: "صفحة خطأ", en: "Error Page" },
	"Access Denied Page": { ar: "صفحة الوصول مرفوض", en: "Access Denied Page" },
	"Maintenance Page": { ar: "صفحة الصيانة", en: "Maintenance Page" },
	"Loading Page": { ar: "صفحة تحميل", en: "Loading Page" },
	"Empty State": { ar: "حالة فارغة", en: "Empty State" },
	"No Results": { ar: "لا توجد نتائج", en: "No Results" },
	"No Data": { ar: "لا توجد بيانات", en: "No Data" },
	"No Items": { ar: "لا توجد أصناف", en: "No Items" },
	"No Records": { ar: "لا توجد سجلات", en: "No Records" },
	"No Entries": { ar: "لا توجد قيود", en: "No Entries" },
	"No Transactions": { ar: "لا توجد معاملات", en: "No Transactions" },
	"No Payments": { ar: "لا توجد مدفوعات", en: "No Payments" },
	"No Invoices": { ar: "لا توجد فواتير", en: "No Invoices" },
	"No Receipts": { ar: "لا توجد إيصالات", en: "No Receipts" },
	"No Cheques": { ar: "لا توجد شيكات", en: "No Cheques" },
	"No Customers": { ar: "لا يوجد عملاء", en: "No Customers" },
	"No Suppliers": { ar: "لا يوجد موردين", en: "No Suppliers" },
	"No Products": { ar: "لا توجد منتجات", en: "No Products" },
	"No Warehouses": { ar: "لا توجد مستودعات", en: "No Warehouses" },
	"No Users": { ar: "لا يوجد مستخدمين", en: "No Users" },
	"No Reports": { ar: "لا توجد تقارير", en: "No Reports" },
	"No Settings": { ar: "لا توجد إعدادات", en: "No Settings" },
	"No Actions Available": {
		ar: "لا توجد إجراءات متاحة",
		en: "No Actions Available",
	},
	"Add New": { ar: "إضافة جديد", en: "Add New" },
	"Edit Existing": { ar: "تعديل موجود", en: "Edit Existing" },
	"Delete Selected": { ar: "حذف المحدد", en: "Delete Selected" },
	"View Details": { ar: "عرض التفاصيل", en: "View Details" },
	"Export Data": { ar: "تصدير البيانات", en: "Export Data" },
	"Import Data": { ar: "استيراد البيانات", en: "Import Data" },
	"Download File": { ar: "تحميل ملف", en: "Download File" },
	"Upload File": { ar: "رفع ملف", en: "Upload File" },
	"Print Page": { ar: "طباعة الصفحة", en: "Print Page" },
	"Refresh Page": { ar: "تحديث الصفحة", en: "Refresh Page" },
	"Go Back": { ar: "العودة", en: "Go Back" },
	"Go Home": { ar: "الرئيسية", en: "Go Home" },
	"Contact Support": { ar: "التواصل مع الدعم", en: "Contact Support" },
	"Report Issue": { ar: "الإبلاغ عن مشكلة", en: "Report Issue" },
	"View Documentation": { ar: "عرض التوثيق", en: "View Documentation" },
	Help: { ar: "مساعدة", en: "Help" },
	FAQ: { ar: "الأسئلة الشائعة", en: "FAQ" },
	About: { ar: "حول", en: "About" },
	"Terms of Service": { ar: "شروط الخدمة", en: "Terms of Service" },
	"Privacy Policy": { ar: "سياسة الخصوصية", en: "Privacy Policy" },
	"Cookie Policy": { ar: "سياسة ملفات تعريف الارتباط", en: "Cookie Policy" },
	License: { ar: "الرخصة", en: "License" },
	Copyright: { ar: "حقوق النشر", en: "Copyright" },
	"All Rights Reserved": {
		ar: "جميع الحقوق محفوظة",
		en: "All Rights Reserved",
	},
	"Powered By": { ar: "مشغل بواسطة", en: "Powered By" },
	"Built With": { ar: "مبني بواسطة", en: "Built With" },
	"Made With": { ar: "صنع بواسطة", en: "Made With" },
	"Version Number": { ar: "رقم الإصدار", en: "Version Number" },
	"Build Date": { ar: "تاريخ البناء", en: "Build Date" },
	"Last Updated": { ar: "آخر تحديث", en: "Last Updated" },
	"System Version": { ar: "إصدار النظام", en: "System Version" },
	"Application Version": { ar: "إصدار التطبيق", en: "Application Version" },
	"API Version": { ar: "إصدار API", en: "API Version" },
	"Database Version": { ar: "إصدار قاعدة البيانات", en: "Database Version" },
	"Check for Updates": { ar: "التحقق من التحديثات", en: "Check for Updates" },
	"Update Available": { ar: "تحديث متاح", en: "Update Available" },
	"Up to Date": { ar: "محدث", en: "Up to Date" },
	"Update Now": { ar: "تحديث الآن", en: "Update Now" },
	"Update Later": { ar: "تحديث لاحقاً", en: "Update Later" },
	Changelog: { ar: "سجل التغييرات", en: "Changelog" },
	"Release Notes": { ar: "ملاحظات الإصدار", en: "Release Notes" },
	"Known Issues": { ar: "مشاكل معروفة", en: "Known Issues" },
	"Fixed Issues": { ar: "مشاكل تم إصلاحها", en: "Fixed Issues" },
	"New Features": { ar: "مميزات جديدة", en: "New Features" },
	Improvements: { ar: "تحسينات", en: "Improvements" },
	"Bug Fixes": { ar: "إصلاح أخطاء", en: "Bug Fixes" },
	"Breaking Changes": { ar: "تغييرات جوهرية", en: "Breaking Changes" },
	"Migration Guide": { ar: "دليل الترقية", en: "Migration Guide" },
	Compatibility: { ar: "التوافق", en: "Compatibility" },
	Requirements: { ar: "المتطلبات", en: "Requirements" },
	Dependencies: { ar: "التبعيات", en: "Dependencies" },
	"License Key": { ar: "مفتاح الترخيص", en: "License Key" },
	"Activate License": { ar: "تفعيل الترخيص", en: "Activate License" },
	"Deactivate License": { ar: "إلغاء تفعيل الترخيص", en: "Deactivate License" },
	"License Expired": { ar: "انتهى الترخيص", en: "License Expired" },
	"License Valid": { ar: "الترخيص صالح", en: "License Valid" },
	"License Invalid": { ar: "الترخيص غير صالح", en: "License Invalid" },
	"Trial Period": { ar: "فترة التجربة", en: "Trial Period" },
	"Trial Expired": { ar: "انتهت فترة التجربة", en: "Trial Expired" },
	"Upgrade Now": { ar: "ترقية الآن", en: "Upgrade Now" },
	Downgrade: { ar: "تخفيض", en: "Downgrade" },
	Subscription: { ar: "الاشتراك", en: "Subscription" },
	"Subscription Expired": { ar: "انتهى الاشتراك", en: "Subscription Expired" },
	"Renew Subscription": { ar: "تجديد الاشتراك", en: "Renew Subscription" },
	"Cancel Subscription": { ar: "إلغاء الاشتراك", en: "Cancel Subscription" },
	"Payment Due": { ar: "الدفع مستحق", en: "Payment Due" },
	"Payment Overdue": { ar: "الدفع متأخر", en: "Payment Overdue" },
	"Payment Received": { ar: "تم استلام الدفع", en: "Payment Received" },
	"Payment Failed": { ar: "فشل الدفع", en: "Payment Failed" },
	"Payment Pending": { ar: "الدفع معلق", en: "Payment Pending" },
	"Payment Processing": { ar: "جارٍ معالجة الدفع", en: "Payment Processing" },
	"Payment Complete": { ar: "اكتمل الدفع", en: "Payment Complete" },
	"Payment Refunded": { ar: "تم استرداد الدفع", en: "Payment Refunded" },
	"Invoice Paid": { ar: "الفاتورة مدفوعة", en: "Invoice Paid" },
	"Invoice Unpaid": { ar: "الفاتورة غير مدفوعة", en: "Invoice Unpaid" },
	"Invoice Partial": { ar: "الفاتورة مدفوعة جزئياً", en: "Invoice Partial" },
	"Invoice Overdue": { ar: "الفاتورة متأخرة", en: "Invoice Overdue" },
	"Invoice Cancelled": { ar: "الفاتورة ملغاة", en: "Invoice Cancelled" },
	"Invoice Draft": { ar: "الفاتورة مسودة", en: "Invoice Draft" },
	"Invoice Sent": { ar: "الفاتورة مرسلة", en: "Invoice Sent" },
	"Invoice Viewed": { ar: "الفاتورة تمت مشاهدتها", en: "Invoice Viewed" },
	"Invoice Expired": { ar: "الفاتورة منتهية الصلاحية", en: "Invoice Expired" },
	"Receipt Paid": { ar: "الإيصال مدفوع", en: "Receipt Paid" },
	"Receipt Unpaid": { ar: "الإيصال غير مدفوع", en: "Receipt Unpaid" },
	"Receipt Partial": { ar: "الإيصال مدفوع جزئياً", en: "Receipt Partial" },
	"Receipt Cancelled": { ar: "الإيصال ملغي", en: "Receipt Cancelled" },
	"Receipt Draft": { ar: "الإيصال مسودة", en: "Receipt Draft" },
	"Cheque Pending": { ar: "الشيك معلق", en: "Cheque Pending" },
	"Cheque Cleared": { ar: "الشيك محصل", en: "Cheque Cleared" },
	"Cheque Bounced": { ar: "الشيك مرتد", en: "Cheque Bounced" },
	"Cheque Deposited": { ar: "الشيك مودع", en: "Cheque Deposited" },
	"Cheque Cancelled": { ar: "الشيك ملغي", en: "Cheque Cancelled" },
	"Cheque Overdue": { ar: "الشيك متأخر", en: "Cheque Overdue" },
	"Cheque Returned": { ar: "الشيك مرتجع", en: "Cheque Returned" },
	"Cheque Under Review": {
		ar: "الشيك قيد المراجعة",
		en: "Cheque Under Review",
	},
	"Order Pending": { ar: "الطلب معلق", en: "Order Pending" },
	"Order Processing": { ar: "الطلب قيد المعالجة", en: "Order Processing" },
	"Order Shipped": { ar: "الطلب تم شحنه", en: "Order Shipped" },
	"Order Delivered": { ar: "الطلب تم توصيله", en: "Order Delivered" },
	"Order Cancelled": { ar: "الطلب ملغي", en: "Order Cancelled" },
	"Order Returned": { ar: "الطلب مرتجع", en: "Order Returned" },
	"Order Completed": { ar: "الطلب مكتمل", en: "Order Completed" },
	"Order Refunded": { ar: "الطلب مسترد", en: "Order Refunded" },
	"Expense Approved": { ar: "المصروف معتمد", en: "Expense Approved" },
	"Expense Rejected": { ar: "المصروف مرفوض", en: "Expense Rejected" },
	"Expense Pending": { ar: "المصروف معلق", en: "Expense Pending" },
	"Expense Paid": { ar: "المصروف مدفوع", en: "Expense Paid" },
	"Expense Unpaid": { ar: "المصروف غير مدفوع", en: "Expense Unpaid" },
	"Transfer Pending": { ar: "التحويل معلق", en: "Transfer Pending" },
	"Transfer Completed": { ar: "التحويل مكتمل", en: "Transfer Completed" },
	"Transfer Cancelled": { ar: "التحويل ملغي", en: "Transfer Cancelled" },
	"Transfer In Transit": { ar: "التحويل في الطريق", en: "Transfer In Transit" },
	"User Active": { ar: "المستخدم نشط", en: "User Active" },
	"User Inactive": { ar: "المستخدم غير نشط", en: "User Inactive" },
	"User Locked": { ar: "المستخدم مقفل", en: "User Locked" },
	"User Suspended": { ar: "المستخدم معلق", en: "User Suspended" },
	"User Deleted": { ar: "المستخدم محذوف", en: "User Deleted" },
	"Account Active": { ar: "الحساب نشط", en: "Account Active" },
	"Account Inactive": { ar: "الحساب غير نشط", en: "Account Inactive" },
	"Account Closed": { ar: "الحساب مغلق", en: "Account Closed" },
	"Account Frozen": { ar: "الحساب مجمد", en: "Account Frozen" },
	"Account Suspended": { ar: "الحساب معلق", en: "Account Suspended" },
	"System Online": { ar: "النظام متاح", en: "System Online" },
	"System Offline": { ar: "النظام غير متاح", en: "System Offline" },
	"System Maintenance": { ar: "النظام قيد الصيانة", en: "System Maintenance" },
	"System Updating": { ar: "النظام قيد التحديث", en: "System Updating" },
	"System Error": { ar: "خطأ في النظام", en: "System Error" },
	"Connection Error": { ar: "خطأ في الاتصال", en: "Connection Error" },
	"Timeout Error": { ar: "خطأ في المهلة الزمنية", en: "Timeout Error" },
	"Not Found Error": { ar: "خطأ في عدم العثور", en: "Not Found Error" },
	"Server Error Message": { ar: "خطأ في الخادم", en: "Server Error Message" },
	"Client Error": { ar: "خطأ في العميل", en: "Client Error" },
	"Network Error": { ar: "خطأ في الشبكة", en: "Network Error" },
	"Validation Error": { ar: "خطأ في التحقق", en: "Validation Error" },
	"Permission Error": { ar: "خطأ في الصلاحيات", en: "Permission Error" },
	"Authentication Error": { ar: "خطأ في المصادقة", en: "Authentication Error" },
	"Authorization Error": { ar: "خطأ في التفويض", en: "Authorization Error" },
	"Data Error": { ar: "خطأ في البيانات", en: "Data Error" },
	"Format Error": { ar: "خطأ في التنسيق", en: "Format Error" },
	"Encoding Error": { ar: "خطأ في الترميز", en: "Encoding Error" },
	"File Error": { ar: "خطأ في الملف", en: "File Error" },
	"Database Error": { ar: "خطأ في قاعدة البيانات", en: "Database Error" },
	"Memory Error": { ar: "خطأ في الذاكرة", en: "Memory Error" },
	"Disk Error": { ar: "خطأ في القرص", en: "Disk Error" },
	"Cache Error": { ar: "خطأ في التخزين المؤقت", en: "Cache Error" },
	"Queue Error": { ar: "خطأ في الطابور", en: "Queue Error" },
	"Worker Error": { ar: "خطأ في العامل", en: "Worker Error" },
	"Task Error": { ar: "خطأ في المهمة", en: "Task Error" },
	"Job Error": { ar: "خطأ في العمل", en: "Job Error" },
	"Process Error": { ar: "خطأ في العملية", en: "Process Error" },
	"Thread Error": { ar: "خطأ في الخيط", en: "Thread Error" },
	"Event Error": { ar: "خطأ في الحدث", en: "Event Error" },
	"Hook Error": { ar: "خطأ في الخطاف", en: "Hook Error" },
	"Plugin Error": { ar: "خطأ في الإضافة", en: "Plugin Error" },
	"Theme Error": { ar: "خطأ في السمة", en: "Theme Error" },
	"Template Error": { ar: "خطأ في القالب", en: "Template Error" },
	"Component Error": { ar: "خطأ في المكون", en: "Component Error" },
	"Module Error": { ar: "خطأ في الوحدة", en: "Module Error" },
	"Package Error": { ar: "خطأ في الحزمة", en: "Package Error" },
	"Dependency Error": { ar: "خطأ في التبعية", en: "Dependency Error" },
	"Configuration Error": { ar: "خطأ في الإعدادات", en: "Configuration Error" },
	"Environment Error": { ar: "خطأ في البيئة", en: "Environment Error" },
	"Runtime Error": { ar: "خطأ في وقت التشغيل", en: "Runtime Error" },
	"Compile Error": { ar: "خطأ في الترجمة", en: "Compile Error" },
	"Syntax Error": { ar: "خطأ في الصياغة", en: "Syntax Error" },
	"Logic Error": { ar: "خطأ في المنطق", en: "Logic Error" },
	"Math Error": { ar: "خطأ في الحساب", en: "Math Error" },
	"Overflow Error": { ar: "خطأ في الفائض", en: "Overflow Error" },
	"Underflow Error": { ar: "خطأ في النقص", en: "Underflow Error" },
	"Zero Division Error": {
		ar: "خطأ في القسمة على صفر",
		en: "Zero Division Error",
	},
	"Index Error": { ar: "خطأ في الفهرس", en: "Index Error" },
	"Key Error": { ar: "خطأ في المفتاح", en: "Key Error" },
	"Value Error": { ar: "خطأ في القيمة", en: "Value Error" },
	"Type Error": { ar: "خطأ في النوع", en: "Type Error" },
	"Attribute Error": { ar: "خطأ في السمة", en: "Attribute Error" },
	"Name Error": { ar: "خطأ في الاسم", en: "Name Error" },
	"Import Error": { ar: "خطأ في الاستيراد", en: "Import Error" },
	"Unbound Local Error": {
		ar: "خطأ في المتغير المحلي غير المربوط",
		en: "Unbound Local Error",
	},
	"Stop Iteration": { ar: "توقف التكرار", en: "Stop Iteration" },
	"Recursion Error": { ar: "خطأ في العودية", en: "Recursion Error" },
	"Memory Limit": { ar: "حد الذاكرة", en: "Memory Limit" },
	"Time Limit": { ar: "حد الوقت", en: "Time Limit" },
	"Resource Limit": { ar: "حد الموارد", en: "Resource Limit" },
	"Connection Limit": { ar: "حد الاتصال", en: "Connection Limit" },
	"Request Limit": { ar: "حد الطلبات", en: "Request Limit" },
	"Rate Limit": { ar: "حد المعدل", en: "Rate Limit" },
	"Size Limit": { ar: "حد الحجم", en: "Size Limit" },
	"Length Limit": { ar: "حد الطول", en: "Length Limit" },
	"Width Limit": { ar: "حد العرض", en: "Width Limit" },
	"Height Limit": { ar: "حد الارتفاع", en: "Height Limit" },
	"Depth Limit": { ar: "حد العمق", en: "Depth Limit" },
	"Weight Limit": { ar: "حد الوزن", en: "Weight Limit" },
	"Volume Limit": { ar: "حد الحجم", en: "Volume Limit" },
	"Area Limit": { ar: "حد المساحة", en: "Area Limit" },
	"Perimeter Limit": { ar: "حد المحيط", en: "Perimeter Limit" },
	"Diameter Limit": { ar: "حد القطر", en: "Diameter Limit" },
	"Radius Limit": { ar: "حد نصف القطر", en: "Radius Limit" },
	"Circumference Limit": { ar: "حد محيط الدائرة", en: "Circumference Limit" },
	"Arc Length Limit": { ar: "حد طول القوس", en: "Arc Length Limit" },
	"Chord Length Limit": { ar: "حد طول الوتر", en: "Chord Length Limit" },
	"Segment Length Limit": { ar: "حد طول القطعة", en: "Segment Length Limit" },
	"Line Length Limit": { ar: "حد طول الخط", en: "Line Length Limit" },
	"Curve Length Limit": { ar: "حد طول المنحنى", en: "Curve Length Limit" },
	"Surface Area Limit": { ar: "حد المساحة السطحية", en: "Surface Area Limit" },
	"Volume Surface Limit": { ar: "حد حجم السطح", en: "Volume Surface Limit" },
	"Total Surface Limit": {
		ar: "حد المساحة الإجمالية",
		en: "Total Surface Limit",
	},
	"Lateral Surface Limit": {
		ar: "حد المساحة الجانبية",
		en: "Lateral Surface Limit",
	},
	"Cross Section Limit": { ar: "حد المقطع العرضي", en: "Cross Section Limit" },
	"Longitudinal Section Limit": {
		ar: "حد المقطع الطولي",
		en: "Longitudinal Section Limit",
	},
	"Horizontal Section Limit": {
		ar: "حد المقطع الأفقي",
		en: "Horizontal Section Limit",
	},
	"Vertical Section Limit": {
		ar: "حد المقطع الرأسي",
		en: "Vertical Section Limit",
	},
	"Diagonal Section Limit": {
		ar: "حد المقطع القطري",
		en: "Diagonal Section Limit",
	},
	"Parallel Section Limit": {
		ar: "حد المقطع الموازي",
		en: "Parallel Section Limit",
	},
	"Perpendicular Section Limit": {
		ar: "حد المقطع العمودي",
		en: "Perpendicular Section Limit",
	},
	"Oblique Section Limit": {
		ar: "حد المقطع المائل",
		en: "Oblique Section Limit",
	},
	"Tangent Section Limit": {
		ar: "حد المقطع المماس",
		en: "Tangent Section Limit",
	},
	"Normal Section Limit": {
		ar: "حد المقطع العمودي",
		en: "Normal Section Limit",
	},
	"Secant Section Limit": {
		ar: "حد المقطع القاطع",
		en: "Secant Section Limit",
	},
	"Chord Section Limit": { ar: "حد المقطع الوتري", en: "Chord Section Limit" },
	"Arc Section Limit": { ar: "حد المقطع القوسي", en: "Arc Section Limit" },
	"Segment Section Limit": {
		ar: "حد المقطع القطعي",
		en: "Segment Section Limit",
	},
	"Sector Section Limit": {
		ar: "حد المقطع المخروطي",
		en: "Sector Section Limit",
	},
	"Annulus Section Limit": {
		ar: "حد المقطع الحلقي",
		en: "Annulus Section Limit",
	},
	"Ellipse Section Limit": {
		ar: "حد المقطع البيضاوي",
		en: "Ellipse Section Limit",
	},
	"Hyperbola Section Limit": {
		ar: "حد المقطع الزائد",
		en: "Hyperbola Section Limit",
	},
	"Parabola Section Limit": {
		ar: "حد المقطع التربيعي",
		en: "Parabola Section Limit",
	},
	"Spiral Section Limit": {
		ar: "حد المقطع الحلزوني",
		en: "Spiral Section Limit",
	},
	"Helix Section Limit": {
		ar: "حد المقطع الحلزوني",
		en: "Helix Section Limit",
	},
	"Catenary Section Limit": {
		ar: "حد المقطع السيتري",
		en: "Catenary Section Limit",
	},
	"Trochoid Section Limit": {
		ar: "حد المقطع التروخي",
		en: "Trochoid Section Limit",
	},
	"Cycloid Section Limit": {
		ar: "حد المقطع الدوري",
		en: "Cycloid Section Limit",
	},
	"Epicycloid Section Limit": {
		ar: "حد المقطع فوق الدوري",
		en: "Epicycloid Section Limit",
	},
	"Hypocycloid Section Limit": {
		ar: "حد المقطع تحت الدوري",
		en: "Hypocycloid Section Limit",
	},
	"Cardioid Section Limit": {
		ar: "حد المقطع القلبي",
		en: "Cardioid Section Limit",
	},
	"Limacon Section Limit": {
		ar: "حد المقطع الليماسي",
		en: "Limacon Section Limit",
	},
	"Rose Section Limit": { ar: "حد المقطع الوردي", en: "Rose Section Limit" },
	"Lemniscate Section Limit": {
		ar: "حد المقطع اللامنثني",
		en: "Lemniscate Section Limit",
	},
	"Cissoid Section Limit": {
		ar: "حد المقطع السيروي",
		en: "Cissoid Section Limit",
	},
	"Conchoid Section Limit": {
		ar: "حد المقطع الصدفي",
		en: "Conchoid Section Limit",
	},
	"Strophoid Section Limit": {
		ar: "حد المقطع العصوي",
		en: "Strophoid Section Limit",
	},
	"Trisectrix Section Limit": {
		ar: "حد المقطع الثلاثي",
		en: "Trisectrix Section Limit",
	},
	"Agnesi Section Limit": {
		ar: "حد المقطع الأغنيسي",
		en: "Agnesi Section Limit",
	},
	"Witch Section Limit": { ar: "حد المقطع السحري", en: "Witch Section Limit" },
	"Folium Section Limit": {
		ar: "حد المقطع الورقي",
		en: "Folium Section Limit",
	},
	"Cubic Section Limit": { ar: "حد المقطع مكعب", en: "Cubic Section Limit" },
	"Quartic Section Limit": {
		ar: "حد المقطع رباعي",
		en: "Quartic Section Limit",
	},
	"Quintic Section Limit": {
		ar: "حد المقطع خماسي",
		en: "Quintic Section Limit",
	},
	"Sextic Section Limit": { ar: "حد المقطع سداسي", en: "Sextic Section Limit" },
	"Septic Section Limit": { ar: "حد المقطع سباعي", en: "Septic Section Limit" },
	"Octic Section Limit": { ar: "حد المقطع ثماني", en: "Octic Section Limit" },
	"Nonic Section Limit": { ar: "حد المقطع تسععي", en: "Nonic Section Limit" },
	"Decic Section Limit": { ar: "حد المقطع عشري", en: "Decic Section Limit" },
	"Total Revenue": { ar: "إجمالي الإيرادات", en: "Total Revenue" },
	"Total Expenses": { ar: "إجمالي المصروفات", en: "Total Expenses" },
	"From Date": { ar: "من تاريخ", en: "From Date" },
	"To Date": { ar: "إلى تاريخ", en: "To Date" },
	From: { ar: "من", en: "From" },
	To: { ar: "إلى", en: "To" },
	"Income statement shows financial performance during a specific period": {
		ar: "تعرض قائمة الدخل الأداء المالي للشركة خلال فترة محددة",
		en: "Income statement shows financial performance during a specific period",
	},
	"Revenue appears as positive values (credit)": {
		ar: "الإيرادات تظهر كقيم موجبة (دائنة)",
		en: "Revenue appears as positive values (credit)",
	},
	"Expenses appear as negative values (debit)": {
		ar: "المصروفات تظهر كقيم سالبة (مدينة)",
		en: "Expenses appear as negative values (debit)",
	},
	"Net Income = Revenue - Expenses": {
		ar: "صافي الدخل = الإيرادات - المصروفات",
		en: "Net Income = Revenue - Expenses",
	},
	"Positive net income means profit, negative means loss": {
		ar: "الموجب يعني ربح والسالب يعني خسارة",
		en: "Positive net income means profit, negative means loss",
	},
	"Performance Ratios": { ar: "نسب الأداء", en: "Performance Ratios" },
	"Expense Ratio to Revenue": {
		ar: "نسبة المصروفات للإيرادات",
		en: "Expense Ratio to Revenue",
	},
	"Profit Margin": { ar: "هامش الربح", en: "Profit Margin" },
	"Revenue to Expenses Ratio": {
		ar: "نسبة الإيرادات المصروفات",
		en: "Revenue to Expenses Ratio",
	},
	"Journals Management": {
		ar: "إدارة القيود المحاسبية",
		en: "Journals Management",
	},
	"Back to Dashboard": { ar: "العودة للوحة التحكم", en: "Back to Dashboard" },
	"New Manual Entry": { ar: "قيد يدوي جديد", en: "New Manual Entry" },
	"All Accounting Journals": {
		ar: "جميع القيود المحاسبية",
		en: "All Accounting Journals",
	},
	"Entry Number": { ar: "رقم القيد", en: "Entry Number" },
	"Are you sure you want to reverse this entry? This action cannot be undone.":
		{
			ar: "هل أنت متأكد من عكس هذا القيد؟ لا يمكن التراجع عن هذا الإجراء.",
			en: "Are you sure you want to reverse this entry? This action cannot be undone.",
		},
	"Failed to reverse entry:": {
		ar: "فشل في عكس القيد:",
		en: "Failed to reverse entry:",
	},
	"Error occurred while reversing entry": {
		ar: "حدث خطأ أثناء عكس القيد",
		en: "Error occurred while reversing entry",
	},
	Hello: { ar: "مرحباً", en: "Hello" },
	"I want": { ar: "أريد", en: "I want" },
	"Source Code": { ar: "المصدري", en: "Source Code" },
	or: { ar: "أو", en: "or" },
	implement: { ar: "تنفيذ", en: "implement" },
	customization: { ar: "تخصيص", en: "customization" },
	Specific: { ar: "محدد", en: "Specific" },
	"for the system": { ar: "للنظام", en: "for the system" },
	Donation: { ar: "التبرع", en: "Donation" },
	Sponsorship: { ar: "رعاية", en: "Sponsorship" },
	development: { ar: "تطوير", en: "development" },
	feature: { ar: "ميزة", en: "feature" },
	in: { ar: "في", en: "in" },
	"I will specify with you": {
		ar: "سأحدده معكم",
		en: "I will specify with you",
	},
	Dollar: { ar: "دولار", en: "Dollar" },
	"I need": { ar: "أحتاج", en: "I need" },
	help: { ar: "مساعدة", en: "help" },
	completing: { ar: "إتمام", en: "completing" },
	inquiry: { ar: "استفسار", en: "inquiry" },
	about: { ar: "عن", en: "about" },
	Status: { ar: "الحالة", en: "Status" },
	refund: { ar: "استرداد", en: "refund" },
	"current package": { ar: "الباقة الحالية", en: "current package" },
	"not yet specified": { ar: "غير محددة بعد", en: "not yet specified" },
	"reference number": { ar: "رقم المرجع", en: "reference number" },
	"Purchase System Request": {
		ar: "طلب شراء النظام",
		en: "Purchase System Request",
	},
	"Purchase Code or Customization Request": {
		ar: "طلب شراء الكود أو التخصيص",
		en: "Purchase Code or Customization Request",
	},
	"Donation or Sponsorship Inquiry": {
		ar: "استفسار تبرع أو رعاية",
		en: "Donation or Sponsorship Inquiry",
	},
	"Help Completing Payment": {
		ar: "مساعدة في إتمام الدفع",
		en: "Help Completing Payment",
	},
	"Refund or Payment Status Inquiry": {
		ar: "استفسار استرداد أو حالة الدفع",
		en: "Refund or Payment Status Inquiry",
	},
	"Contact Information": { ar: "بيانات التواصل", en: "Contact Information" },
	WhatsApp: { ar: "واتساب", en: "WhatsApp" },
	Email: { ar: "بريد", en: "Email" },
	"Current Status": { ar: "الحالة الحالية", en: "Current Status" },
	Reference: { ar: "المرجع", en: "Reference" },
	"On success you will receive clear details or direct payment address": {
		ar: "عند النجاح ستصلك تفاصيل واضحة أو عنوان دفع مباشر",
		en: "On success you will receive clear details or direct payment address",
	},
	"On manual review you can follow up immediately with Azad": {
		ar: "عند المراجعة اليدوية يمكنك المتابعة فوراً مع أزاد",
		en: "On manual review you can follow up immediately with Azad",
	},
	"For any refund or reconciliation use WhatsApp or official email": {
		ar: "لأي استرداد أو تسوية استخدم واتساب أو البريد الرسمي",
		en: "For any refund or reconciliation use WhatsApp or official email",
	},
	"Official contact with Azad": {
		ar: "التواصل الرسمي مع أزاد",
		en: "Official contact with Azad",
	},
	"Open Azad WhatsApp": { ar: "فتح واتساب أزاد", en: "Open Azad WhatsApp" },
	"Send Email": { ar: "إرسال بريد", en: "Send Email" },
	"Minimum donation amount is": {
		ar: "الحد الأدنى للتبرع هو",
		en: "Minimum donation amount is",
	},
	"Minimum donation": { ar: "الحد الأدنى للتبرع", en: "Minimum donation" },
	"Creating payment address...": {
		ar: "جاري إنشاء عنوان الدفع...",
		en: "Creating payment address...",
	},
	"Please select a package first": {
		ar: "الرجاء اختيار باقة أولاً",
		en: "Please select a package first",
	},
	"Selected plan not recognized": {
		ar: "لم يتم التعرف على الخطة المحددة",
		en: "Selected plan not recognized",
	},
	"Plan Purchase Details": {
		ar: "بيانات شراء الخطة",
		en: "Plan Purchase Details",
	},
	"Donation Details": { ar: "بيانات التبرع", en: "Donation Details" },
	Created: { ar: "تم إنشاء", en: "Created" },
	successfully: { ar: "بنجاح", en: "successfully" },
	"Order Number": { ar: "رقم الطلب", en: "Order Number" },
	"Required Amount": { ar: "المبلغ المطلوب", en: "Required Amount" },
	"Payment Address": { ar: "عنوان الدفع", en: "Payment Address" },
	"Copy Address": { ar: "نسخ العنوان", en: "Copy Address" },
	"Open Payment Page": { ar: "فتح صفحة الدفع", en: "Open Payment Page" },
	"Send the amount to the address above and the status will be confirmed automatically":
		{
			ar: "أرسل المبلغ إلى العنوان أعلاه وسيتم تأكيد الحالة تلقائياً",
			en: "Send the amount to the address above and the status will be confirmed automatically",
		},
	"Waiting for your transfer to payment address": {
		ar: "بانتظار تحويلك إلى عنوان الدفع",
		en: "Waiting for your transfer to payment address",
	},
	"Done, I will pay now": { ar: "تم، سأدفع الآن", en: "Done, I will pay now" },
	"Azad WhatsApp": { ar: "واتساب أزاد", en: "Azad WhatsApp" },
	"Email us": { ar: "راسلنا بريد", en: "Email us" },
	"Order saved successfully": {
		ar: "تم حفظ الطلب بنجاح",
		en: "Order saved successfully",
	},
	"Order registered pending follow-up or confirmation": {
		ar: "تم تسجيل الطلب بانتظار المتابعة أو التأكيد",
		en: "Order registered pending follow-up or confirmation",
	},
	"Could not create order": {
		ar: "تعذر إنشاء الطلب",
		en: "Could not create order",
	},
	"Error occurred while creating the order": {
		ar: "حدث خطأ أثناء إنشاء الطلب",
		en: "Error occurred while creating the order",
	},
	"You can retry or complete the process directly with Azad Company": {
		ar: "يمكنك إعادة المحاولة أو إكمال العملية مباشرة مع شركة أزاد",
		en: "You can retry or complete the process directly with Azad Company",
	},
	"Could not connect to server": {
		ar: "تعذر الاتصال بالخادم",
		en: "Could not connect to server",
	},
	"We could not create": { ar: "لم نتمكن من إنشاء", en: "We could not create" },
	"Purchase order": { ar: "طلب شراء", en: "Purchase order" },
	"Donation order": { ar: "طلب تبرع", en: "Donation order" },
	now: { ar: "الآن", en: "now" },
	"You can follow up directly with Azad via WhatsApp or email for the same amount":
		{
			ar: "يمكنك المتابعة مباشرة مع أزاد عبر واتساب أو بريد بنفس المبلغ",
			en: "You can follow up directly with Azad via WhatsApp or email for the same amount",
		},
	"Copied!": { ar: "تم النسخ!", en: "Copied!" },
	"Address copied to clipboard": {
		ar: "تم نسخ العنوان إلى الحافظة",
		en: "Address copied to clipboard",
	},
	"Email address": { ar: "بريد إلكتروني", en: "Email address" },
	"Mobile Number": { ar: "رقم الجوال", en: "Mobile Number" },
	"Company Name": { ar: "اسم الشركة", en: "Company Name" },
	"Payment via PayPal": { ar: "الدفع عبر PayPal", en: "Payment via PayPal" },
	"Transfer is automatically sent to Bitcoin": {
		ar: "يتم التحويل تلقائياً إلى Bitcoin",
		en: "Transfer is automatically sent to Bitcoin",
	},
	Copy: { ar: "نسخ", en: "Copy" },
	"Your order has been saved successfully": {
		ar: "تم حفظ طلبك بنجاح",
		en: "Your order has been saved successfully",
	},
	"Pending payment completion or contact": {
		ar: "قيد انتظار إتمام الدفع أو التواصل",
		en: "Pending payment completion or contact",
	},
	"Follow up Payment": { ar: "متابعة الدفع", en: "Follow up Payment" },
	"Order saved": { ar: "تم حفظ الطلب", en: "Order saved" },
	"Pending coordination with Azad team": {
		ar: "بانتظار التنسيق مع فريق أزاد",
		en: "Pending coordination with Azad team",
	},
	"You can now choose WhatsApp or email to complete payment or inquire": {
		ar: "يمكنك الآن اختيار واتساب أو بريد لإكمال الدفع أو الاستفسار",
		en: "You can now choose WhatsApp or email to complete payment or inquire",
	},
	"Could not complete PayPal order": {
		ar: "تعذر إكمال طلب PayPal",
		en: "Could not complete PayPal order",
	},
	"Could not save PayPal order currently": {
		ar: "تعذر حفظ طلب PayPal حالياً",
		en: "Could not save PayPal order currently",
	},
	"You can follow up directly with Azad via WhatsApp or email": {
		ar: "يمكنك المتابعة مباشرة مع أزاد عبر واتساب أو بريد",
		en: "You can follow up directly with Azad via WhatsApp or email",
	},
	"Connection failed during PayPal": {
		ar: "فشل الاتصال أثناء PayPal",
		en: "Connection failed during PayPal",
	},
	"Could not connect to server while preparing the order": {
		ar: "تعذر التواصل مع الخادم أثناء تجهيز الطلب",
		en: "Could not connect to server while preparing the order",
	},
	"Use WhatsApp or email to complete the purchase or donation with the same details":
		{
			ar: "استخدم واتساب أو بريد لإتمام الشراء أو التبرع بنفس التفاصيل",
			en: "Use WhatsApp or email to complete the purchase or donation with the same details",
		},
	"Please select a package": {
		ar: "الرجاء اختيار باقة",
		en: "Please select a package",
	},
	"Could not prepare card order": {
		ar: "تعذر تجهيز طلب البطاقة",
		en: "Could not prepare card order",
	},
	"Could not save card order currently": {
		ar: "تعذر حفظ طلب البطاقة حالياً",
		en: "Could not save card order currently",
	},
	"You can complete the process directly with Azad via WhatsApp or email": {
		ar: "يمكنك إكمال العملية مباشرة مع أزاد عبر واتساب أو بريد",
		en: "You can complete the process directly with Azad via WhatsApp or email",
	},
	"Connection failed during payment": {
		ar: "فشل الاتصال أثناء الدفع",
		en: "Connection failed during payment",
	},
	"Could not reach server while processing the order": {
		ar: "تعذر الوصول إلى الخادم أثناء معالجة الطلب",
		en: "Could not reach server while processing the order",
	},
	"Don't worry, you can follow up directly with Azad Company": {
		ar: "لا تقلق، يمكنك المتابعة الآن مباشرة مع شركة أزاد",
		en: "Don't worry, you can follow up directly with Azad Company",
	},
	"Payment address created!": {
		ar: "تم إنشاء عنوان الدفع!",
		en: "Payment address created!",
	},
	"Saved Address": { ar: "العنوان المحفوظ", en: "Saved Address" },
	"Order registered pending confirmation or manual follow-up": {
		ar: "تم تسجيل الطلب بانتظار التأكيد أو متابعة يدوية",
		en: "Order registered pending confirmation or manual follow-up",
	},
	"You can follow up directly with Azad Company via WhatsApp or email": {
		ar: "يمكنك المتابعة مباشرة مع شركة أزاد عبر واتساب أو بريد",
		en: "You can follow up directly with Azad Company via WhatsApp or email",
	},
	Continue: { ar: "متابعة", en: "Continue" },
	"Name and email required to purchase plan": {
		ar: "الاسم والبريد الإلكتروني مطلوبان لشراء الخطة",
		en: "Name and email required to purchase plan",
	},
	"Short message (optional)": {
		ar: "رسالة قصيرة (اختياري)",
		en: "Short message (optional)",
	},
	"Company name or additional note (optional)": {
		ar: "اسم الشركة أو ملاحظة إضافية (اختياري)",
		en: "Company name or additional note (optional)",
	},
	"Send the specified amount to the address above": {
		ar: "أرسل المبلغ المحدد إلى العنوان أعلاه",
		en: "Send the specified amount to the address above",
	},
	"Pending payment completion or follow-up with Azad": {
		ar: "بانتظار إتمام الدفع أو المتابعة مع أزاد",
		en: "Pending payment completion or follow-up with Azad",
	},
};

/**
 * Translate a key
 * @param {string} key - The translation key
 * @param {Object} params - Optional parameters for string interpolation
 * @returns {string} Translated text
 */
function t(key, params = {}) {
	const lang = getCurrentLanguage();
	const translation = translations[key];

	if (!translation) {
		return key;
	}

	let text = translation[lang] || translation["ar"] || key;

	// Replace parameters {param}
	Object.keys(params).forEach((param) => {
		text = text.replace(`{${param}}`, params[param]);
	});

	return text;
}

/**
 * Translate all elements with data-i18n attribute
 */
function translatePage() {
	document.querySelectorAll("[data-i18n]").forEach((element) => {
		const key = element.getAttribute("data-i18n");
		element.textContent = t(key);
	});
}

/**
 * Get DataTables language configuration
 */
function getDataTablesLanguage() {
	const lang = getCurrentLanguage();

	if (lang === "ar") {
		return {
			url: "/static/datatables/Arabic.json",
		};
	}

	return {
		sEmptyTable: t("No data available"),
		sInfo: `${t("Showing")} _START_ ${t("to")} _END_ ${t("of")} _TOTAL_ ${t("entries")}`,
		sInfoEmpty: `${t("Showing")} 0 ${t("to")} 0 ${t("of")} 0 ${t("entries")}`,
		sInfoFiltered: `(${t("entries (filtered from")} _MAX_ ${t("total entries)")})`,
		sLengthMenu: `${t("Show")} _MENU_ ${t("entries")}`,
		sLoadingRecords: t("Loading") + "...",
		sProcessing: t("Processing") + "...",
		sSearch: t("Search:"),
		sZeroRecords: t("No records found"),
		oPaginate: {
			sFirst: t("First"),
			sLast: t("Last"),
			sNext: t("Next"),
			sPrevious: t("Previous"),
		},
	};
}

/**
 * Show SweetAlert with translation
 */
function showAlert(title, text, icon = "info") {
	if (typeof Swal !== "undefined") {
		Swal.fire({
			title: t(title),
			text: t(text),
			icon: icon,
			confirmButtonText: t("OK"),
		});
	} else {
		alert(`${t(title)}\n${t(text)}`);
	}
}

/**
 * Show confirmation dialog with translation
 */
function confirmAction(title, text, onConfirm) {
	if (typeof Swal !== "undefined") {
		Swal.fire({
			title: t(title),
			text: t(text),
			icon: "warning",
			showCancelButton: true,
			confirmButtonText: t("Yes"),
			cancelButtonText: t("No"),
			confirmButtonColor: "#d33",
			cancelButtonColor: "#3085d6",
		}).then((result) => {
			if (result.isConfirmed && onConfirm) {
				onConfirm();
			}
		});
	} else {
		if (confirm(`${t(title)}\n${t(text)}`)) {
			if (onConfirm) onConfirm();
		}
	}
}

// Export functions
window.t = t;
window.translatePage = translatePage;
window.getDataTablesLanguage = getDataTablesLanguage;
window.showAlert = showAlert;
window.confirmAction = confirmAction;

// Auto-translate on page load
document.addEventListener("DOMContentLoaded", () => {
	translatePage();
});
