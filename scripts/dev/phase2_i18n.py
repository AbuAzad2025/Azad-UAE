"""
Phase 2: i18n — Scan templates for remaining Arabic, generate keys, apply replacements.
Only replaces inside non-template (HTML text) segments.
"""
import os, re, subprocess, sys

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), 'templates')
I18N_PATH     = os.path.join(os.path.dirname(__file__), 'utils', 'i18n.py')
EXCLUDE_DIRS  = {'shop', 'public', 'owner', 'auth'}
ARABIC_CHARS  = r'[\u0600-\u06FF]'
TAG_SPLIT     = re.compile(r'({%.*?%}|{{.*?}}|{#.*?#})')

# Arabic word-level → English translation (for composing keys)
WORD_MAP = {
    'إدارة':'Management','قائمة':'List','جديد':'New','زبون':'Customer',
    'زبائن':'Customers','مورد':'Supplier','موردين':'Suppliers','منتج':'Product',
    'منتجات':'Products','فاتورة':'Invoice','بيع':'Sale','شراء':'Purchase',
    'تقرير':'Report','تقارير':'Reports','مخزون':'Inventory','مستودع':'Warehouse',
    'مستودعات':'Warehouses','مبيعات':'Sales','مشتريات':'Purchases',
    'معلومات':'Info','الزبون':'Customer','الزبائن':'Customers',
    'المورد':'Supplier','الموردين':'Suppliers','المنتج':'Product',
    'المنتجات':'Products','الفاتورة':'Invoice','المبيعات':'Sales',
    'المشتريات':'Purchases','المخزون':'Inventory','المستودع':'Warehouse',
    'المستودعات':'Warehouses','المالية':'Finance','المحاسبة':'Accounting',
    'محاسبة':'Accounting','محاسبي':'Accounting','محاسبية':'Accounting',
    'الحسابات':'Accounts','الحساب':'Account','حساب':'Account','حسابات':'Accounts',
    'المدفوعات':'Payments','الدفع':'Payment','دفع':'Payment','مدفوع':'Paid',
    'المصروفات':'Expenses','مصروفات':'Expenses','مصروف':'Expense',
    'المصروف':'Expense','التقارير':'Reports','الإعدادات':'Settings',
    'إعدادات':'Settings','الموظفين':'Employees','الموظف':'Employee',
    'موظف':'Employee','موظفين':'Employees','المستخدمين':'Users',
    'المستخدم':'User','مستخدم':'User','مستخدمين':'Users',
    'الصلاحيات':'Permissions','صلاحيات':'Permissions','صلاحية':'Permission',
    'الدور':'Role','الشركاء':'Partners','شريك':'Partner','شريك!':'Partner',
    'المنصة':'Platform','النظام':'System','النسخ':'Backups','نسخ':'Backups',
    'الاحتياطية':'Backup','النسخ الاحتياطية':'Backups','الطباعة':'Printing',
    'طباعة':'Print','الشيكات':'Cheques','الشيك':'Cheque','شيك':'Cheque',
    'شيكات':'Cheques','البنك':'Bank','بنك':'Bank','النقدي':'Cash',
    'النقدية':'Cash','نقدي':'Cash','نقدية':'Cash','بطاقة':'Card',
    'تحويل':'Transfer','بنكي':'Bank','المتجر':'Store','متجر':'Store',
    'الشركة':'Company','شركة':'Company','الفرع':'Branch','فرع':'Branch',
    'الفروع':'Branches','فروع':'Branches','كود':'Code','الكود':'Code',
    'رمز':'Code','الرمز':'Code','الاسم':'Name','اسم':'Name',
    'الوصف':'Description','وصف':'Description','بيان':'Description',
    'ملاحظات':'Notes','ملاحظة':'Note','ملاحظات!':'Notes','العنوان':'Address',
    'عنوان':'Address','الهاتف':'Phone','هاتف':'Phone','البريد':'Email',
    'الإلكتروني':'Email','الموقع':'Website','البيانات':'Data',
    'سعر':'Price','السعر':'Price','التكلفة':'Cost','تكلفة':'Cost',
    'الكمية':'Quantity','كمية':'Qty','العدد':'Count','عدد':'Count',
    'المجموع':'Total','مجموع':'Total','الإجمالي':'Total','إجمالي':'Total',
    'الخصم':'Discount','خصم':'Discount','الضريبة':'Tax','ضريبة':'Tax',
    'الشحن':'Shipping','شحن':'Shipping','الرصيد':'Balance','رصيد':'Balance',
    'رصيده':'Balance','المبلغ':'Amount','مبلغ':'Amount','المبالغ':'Amounts',
    'القيمة':'Value','قيمة':'Value','نسبة':'Rate','معدل':'Rate',
    'سعر الصرف':'Exchange Rate','العملة':'Currency','عملة':'Currency',
    'تاريخ':'Date','التاريخ':'Date','الوقت':'Time','وقت':'Time',
    'الحالة':'Status','حالة':'Status','نشط':'Active','نشطة':'Active',
    'غير نشط':'Inactive','معلق':'Pending','معلقة':'Pending',
    'مؤكدة':'Confirmed','مكتمل':'Completed','مكتملة':'Completed',
    'ملغي':'Cancelled','ملغية':'Cancelled','ملغاة':'Cancelled',
    'جزئي':'Partial','جزئياً':'Partial','بلا':'None',
    'إلغاء':'Cancel','حفظ':'Save','حذف':'Delete','تعديل':'Edit',
    'عرض':'View','بحث':'Search','طباعة':'Print','إضافة':'Add',
    'تحديث':'Update','إرسال':'Submit','تأكيد':'Confirm','إغلاق':'Close',
    'رجوع':'Back','تصدير':'Export','اختيار':'Select','اختياري':'Optional',
    'مطلوب':'Required','تحميل':'Download','رفع':'Upload','إظهار':'Show',
    'إخفاء':'Hide','تطبيق':'Apply','تغيير':'Change','معاينة':'Preview',
    'العربية':'Arabic','الإنجليزية':'English','اليوم':'Today','الكل':'All',
    'الكلية':'All','قائمة':'List','الرئيسية':'Home','اللغة':'Language',
    'الفترة':'Period','فترة':'Period','مدة':'Duration','بداية':'Start',
    'نهاية':'End','عام':'General','المميزات':'Features','مميزات':'Features',
    'اشتراك':'Subscription','باقة':'Plan','شهري':'Monthly','سنوي':'Yearly',
    'مجاني':'Free','غير متاح':'N/A','مميز':'Featured',
    'المرتجعات':'Returns','مرتجع':'Return','المرتجعات!':'Returns',
    'الأرشيف':'Archive','أرشيف':'Archive','مؤرشفة':'Archived',
    'الزبون!':'Customer','نظام المحاسبة':'Accounting System',
    'الذمم':'Receivables','المدينة':'Receivables','المستحقات':'Dues',
    'مستحقات':'Dues','الموازنة':'Budget','موازنة':'Budget',
    'الموازنات':'Budgets','الميزان':'Trial Balance','ميزان':'Balance',
    'المراجعة':'Review','تسوية':'Reconciliation','مطابقة':'Reconciliation',
    'الهامش':'Margin','هامش':'Margin','الأصول':'Assets','الخصوم':'Liabilities',
    'الإيرادات':'Revenue','الأرباح':'Profits','الخسائر':'Losses',
    'التوزيعات':'Distributions','أرباح':'Profit','الرواتب':'Salaries',
    'السلف':'Advances','سلفة':'Advance','سلف':'Advances',
    'الموظفين!':'Employees','الموظف!':'Employee','التحليلات':'Analytics',
    'الإحصائيات':'Statistics','المؤشرات':'Indicators','التوقعات':'Forecasts',
    'الحركات':'Movements','حركة':'Movement','الأصناف':'Items','صنف':'Item',
    'الأيام':'Days','أيام':'Days','باقي':'Balance','الجلسة':'Session',
    'جلسة':'Session','كاشير':'Cashier','النقدي':'Cash','الصندوق':'Fund',
    'الدرج':'Drawer','الوضع':'Mode','الداكن':'Dark','القائمة':'Menu',
    'الجانبية':'Sidebar','التبديل':'Toggle','بروفايلي':'Profile',
    'الملف':'File','الشخصي':'Personal','المساعد':'Assistant','الذكي':'Smart',
    'عدد':'Count','مليون':'Million','ألف':'Thousand','مئة':'Hundred',
    'دينار':'Dinar','درهم':'Dirham','دولار':'Dollar','ريال':'Riyal',
    'شيكل':'Shekel','يورو':'Euro','جنيه':'Pound',
    'نظام':'System','أدوات':'Tools','أدوات!':'Tools','صحة':'Health',
    'مفاتيح':'Keys','ذكاء':'AI','اصطناعي':'Artificial',
    'الفواتير':'Invoices','سند':'Voucher','السندات':'Vouchers',
    'قبض':'Receipt','سند قبض':'Receipt Voucher',
    'إيصال':'Receipt','وصل':'Receipt',
    'مستخدمي':'Users','منصة':'Platform','لوحة':'Dashboard',
    'التحكم':'Control','ترويسات':'Headers','رأسية':'Headers',
    'سجل':'Log','تاريخ':'History','الشركة!':'Company','بيانات':'Data',
    'استعادة':'Restore','صفري':'Zero','تفاصيل':'Details',
    'التفاصيل':'Details','مرفوض':'Rejected','مرفوضة':'Rejected',
    'محظور':'Blocked','محظورة':'Blocked','موقوف':'Suspended',
    'متوقف':'Stopped','متوقفة':'Stopped','معلق!':'Suspended',
    'منتهية':'Expired','ساري':'Active','صالح':'Valid',
    'البحث':'Search','الفلتر':'Filter','فلتر':'Filter','فلاتر':'Filters',
    'الذكي':'Smart','باسم':'By name','بالاسم':'By name',
    'بالهاتف':'By phone','بالرقم':'By number','بالباركود':'By barcode',
    'الكاش':'Cash','الآجل':'Credit','آجل':'Credit','آجلة':'Credit',
    'نقداً':'Cash','الشبكة':'Grid','التقليدية':'Classic',
    'الكلاسيكية':'Classic','الحديثة':'Modern','البسيطة':'Simple',
    'الكلاسيكي':'Classic','الحديث':'Modern','البسيط':'Simple',
    'فاتورة بيع':'Sales Invoice','فاتورة شراء':'Purchase Invoice',
    'أمر شراء':'Purchase Order','عرض سعر':'Quote',
    'كشف حساب':'Statement','ميزان':'Balance','ملخص':'Summary',
    'مقدمة':'Introduction','الرئيسية':'Main','إضافي':'Additional',
    'إضافية':'Additional','عام':'General','عامة':'General',
    'خاص':'Specific','خاصة':'Specific','المسؤول':'Responsible',
    'مطلوب':'Required','إجباري':'Required','اختياري':'Optional',
    'الموجودة':'Available','المتاحة':'Available','المتبقي':'Remaining',
    'الباقي':'Remaining','المتوقع':'Expected','الفعلي':'Actual',
    'الافتراضي':'Default','التلقائي':'Auto','يدوي':'Manual',
    'يدوي!':'Manual','يدوياً':'Manually',
    'فلسطيني':'Palestinian','فلسطينية':'Palestinian',
    'خليجي':'Gulf','خليجية':'Gulf',
    'عربي':'Arabic','عربية':'Arabic',
    'إنجليزي':'English','إنجليزية':'English','بالعربية':'In Arabic',
    'بالإنجليزية':'In English','بالإنجليزي':'In English',
    'آخر':'Last','أخير':'Last','الأخيرة':'Recent',
    'الأسبوع':'Week','الشهر':'Month','السنة':'Year',
    'الربع':'Quarter','هذا':'This','هذه':'This',
    'مشترك':'Shared','مشتركة':'Shared',
    'تحت':'Under','فوق':'Above','بين':'Between',
    'خلال':'During','داخل':'Inside','خارج':'Outside',
    'محلي':'Local','دولي':'International','عالمي':'Global',
    'إقليمي':'Regional','وطني':'National',
    'الكبير':'Large','الصغير':'Small','المتوسط':'Medium',
    'العالي':'High','المنخفض':'Low',
    'احتياطي':'Reserve','احتياطية':'Reserve',
    'الصيانة':'Maintenance','صيانة':'Maintenance',
    'ضمان':'Warranty','كفالة':'Guarantee',
    'التنبيه':'Alert','تنبيه':'Alert','تنبيهات':'Alerts',
    'إشعار':'Notification','إشعارات':'Notifications',
    'الزبائن!':'Customers','الموردين!':'Suppliers',
    'للمبيعات':'Sales','للمشتريات':'Purchases',
    'للمنتجات':'Products','للمخزون':'Inventory',
    'للمستودعات':'Warehouses','للزبائن':'Customers',
    'للموردين':'Suppliers','للحسابات':'Accounts',
    'للمدفوعات':'Payments','للمصروفات':'Expenses',
    'للمستخدمين':'Users','للموظفين':'Employees',
    'للشركاء':'Partners','للتقارير':'Reports',
    'للإعدادات':'Settings','للطباعة':'Printing',
    'للفواتير':'Invoices','للشيكات':'Cheques',
    'للمالية':'Finance','للبرنامج':'Software',
    'إنشاء':'Create','انشاء':'Create',
    'جديدة':'New','قديم':'Old','قديمة':'Old',
    'العميل':'Customer','عملاء':'Customers','العملاء':'Customers',
    'المندوب':'Rep','مندوب':'Rep',
    'الفلتر':'Filter','البحث':'Search',
    'الاستحقاق':'Due','الصرف':'Exchange',
    'متأخر':'Late','متأخرة':'Late',
    'مرتدة':'Returned','مرتد':'Returned',
    'قريبة':'Near','قريب':'Near',
    'الباركود':'Barcode',
    'للإرجاع':'Return','للاسترجاع':'Return',
    'لالغاء':'Cancel','للحذف':'Delete',
    'سريع':'Quick','سريعة':'Quick',
    'التقليدي':'Classic','التقليدية':'Classic',
    'الشبكة':'Grid','البسيط':'Simple',
    'الحديث':'Modern','الحديثة':'Modern',
    'الرئيسي':'Main','الفرعي':'Sub',
    'موبايل':'Mobile','جوال':'Mobile',
    'منخفض':'Low','منخفضة':'Low',
    'مرتفع':'High','مرتفعة':'High',
    'متوسط!':'Medium','متوسطة':'Medium',
    'مجموع':'Total','فرعي':'Sub',
    'مسلسل':'Serial','مسلسلة':'Serial','التسلسلي':'Serial','تسلسلي':'Serial',
    'مرجعي':'Reference','مرجعية':'Reference',
    'يدوي':'Manual','يدوية':'Manual',
    'فعلي':'Actual','فعلية':'Actual',
    'متوقع':'Expected','متوقعة':'Expected',
    'مهم':'Important','مهمة':'Task',
    'ممتاز':'Excellent','جيد':'Good','ممتازة':'Excellent',
    'ضعيف':'Weak','ضعيفة':'Weak',
    'صفر':'Zero','كبير':'Large','صغير':'Small',
    'نصف':'Half','ربع':'Quarter','ثلث':'Third',
    'ثابت':'Fixed','متغير':'Variable',
    'مؤقت':'Temporary','دائم':'Permanent',
    'سنوي':'Annual','شهري':'Monthly','أسبوعي':'Weekly',
    'يومي':'Daily','ربعي':'Quarterly',
    'متاح':'Available','متاحة':'Available',
    'محجوز':'Reserved','محجوزة':'Reserved',
    'مشغول':'Busy','مشغولة':'Busy',
    'مغلق':'Closed','مفتوح':'Open',
    'مقفل':'Locked','مقفلة':'Locked',
    'صافي':'Net','خام':'Gross',
    'ربح':'Profit','خسارة':'Loss',
    'دخل':'Income','مصروف':'Expense',
    'وارد':'Income','صادر':'Expense',
    'إيراد':'Revenue','إيرادات':'Revenues',
    'مقبوض':'Received','مقبوضة':'Received',
    'مدفوع':'Paid','مدفوعة':'Paid',
    'مسدد':'Paid','مسددة':'Paid',
    'مؤكد':'Confirmed','مؤكدة':'Confirmed',
    'مرفوض':'Rejected','مرفوضة':'Rejected',
    'منتهي':'Expired','منتهية':'Expired',
    'الانتظار':'Waiting','انتظار':'Waiting',
    'تحت':'Under','المراجعة':'Review',
    'المعالجة':'Processing','معالجة':'Processing',
}


def get_existing():
    """Parse i18n.py → {arabic: english_key}."""
    d = {}
    try:
        with open(I18N_PATH, 'r', encoding='utf-8') as f:
            c = f.read()
        for m in re.finditer(r"'([^']+)':\s*\{[^}]*?'ar':\s*'([^']*)'", c):
            d[m.group(2)] = m.group(1)
    except: pass
    return d

def compose_key(ar_text):
    """Build an English key from Arabic text by translating each word."""
    words = re.split(r'[\s\-]+', ar_text.strip())
    parts = []
    for w in words:
        w = w.strip('؟!.,;-:()[]{}+/ \t-')
        if w in WORD_MAP:
            parts.append(WORD_MAP[w])
        else:
            # Try removing leading ال
            if w.startswith('ال') and len(w) > 3 and w[2:] in WORD_MAP:
                parts.append(WORD_MAP[w[2:]])
            # unknown word — just append cleaned form (only if empty so far)
            elif not parts:
                parts.append(w.replace(' ',''))
    if not parts:
        return None
    return ' '.join(parts)

def is_meaningful(text):
    """Quick check that text has at least one meaningful word."""
    text = text.strip()
    if len(text) < 3:
        return False
    words = re.split(r'[\s\-]+', text)
    clean = [w.strip('؟!.,;-:()[]{}+/ \t-') for w in words if w.strip()]
    if not clean:
        return False
    # At least one word that's not a stop-word
    stops = {'في','من','إلى','على','عن','مع','لا','لم','لن','هل','قد',
             'هو','هي','هم','نحن','أنت','أنا','هذا','هذه','ذلك','تلك',
             'بين','تحت','فوق','دون','غير','جدا','فقط','هناك','هنا','نعم',
             'بـ','لـ','ثم','أو','بل','لكن','حتى','إذا','كان','كانت',
             'يكون','تكون','يتم','يمكن','يجب','عند','بعد','قبل','خلال',
             'كل','بعض','أي','ذات','نفس','أيضا','حيث','حول','بسبب','رغم',
             'مثل','لدى','لديه','لديك','عليه','عليها','لهم','لها','له',
             'عليهم','أبداً','أخيراً','أخيرا','فقط','دائماً',
             'بالمئة','بعد','قبل','فوق','دون','حتى','نحو','م',
             'واحد','اثنان','اثنين','ثلاثة','أربعة','خمسة',
             'ستة','سبعة','ثمانية','تسعة','عشرة'}
    meaningful = [w for w in clean if w not in stops]
    return len(meaningful) > 0

def extract_arabic(segment):
    """Return set of Arabic words found in a non-template segment."""
    found = set()
    for m in re.finditer(ARABIC_CHARS + r'{3,}', segment):
        w = m.group(0)
        if is_meaningful(w):
            found.add(w)
    return found

def process_file(fp, ar_known, new_map, existing_mapped):
    """Process one template file. Returns # replacements."""
    with open(fp, 'r', encoding='utf-8') as f:
        content = f.read()
    segs = TAG_SPLIT.split(content)

    # Phase 1 – collect Arabic words from non-template segments
    words = set()
    for s in segs:
        if s.startswith('{%') or s.startswith('{{') or s.startswith('{#'):
            continue
        words.update(extract_arabic(s))

    # Phase 2 – determine key for each word
    lookup = {}  # arabic → key
    for w in sorted(words, key=len, reverse=True):
        if w in ar_known:
            lookup[w] = ar_known[w]
            existing_mapped.add(w)
        elif w in new_map:
            lookup[w] = new_map[w]
        else:
            k = compose_key(w)
            if k and k not in ar_known.values() and k not in new_map.values():
                new_map[w] = k
                lookup[w] = k
            else:
                # Generate a suffix if needed
                base = compose_key(w) or 'Key'
                k = base
                n = 2
                while k in ar_known.values() or k in new_map.values():
                    k = f'{base}_{n}'
                    n += 1
                new_map[w] = k
                lookup[w] = k

    if not lookup:
        return 0

    # Phase 3 – replace in non-template segments only
    new_segs = []
    repl = 0
    for s in segs:
        if s.startswith('{%') or s.startswith('{{') or s.startswith('{#'):
            new_segs.append(s)
        else:
            for ar, key in sorted(lookup.items(), key=lambda x: -len(x[0])):
                cnt = s.count(ar)
                if cnt:
                    s = s.replace(ar, "{{ t('" + key + "') }}")
                    repl += cnt
            new_segs.append(s)

    if repl:
        with open(fp, 'w', encoding='utf-8') as f:
            f.write(''.join(new_segs))
    return repl

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 60)
    print("Phase 2: i18n — Arabic extraction & replacement")
    print("=" * 60)

    ar_known = get_existing()
    print(f"Existing translation keys: {len(ar_known)}")

    # Collect files
    files = sorted(
        os.path.join(dp, f)
        for dp, dn, fn in os.walk(TEMPLATES_DIR)
        for f in fn if f.endswith('.html')
        if not os.path.relpath(dp, TEMPLATES_DIR).split(os.sep)[0] in EXCLUDE_DIRS
    )
    print(f"Template files to scan: {len(files)}")

    new_map = {}          # arabic → new key
    existing_mapped = set()  # arabic already in translations
    total_repl = 0
    files_mod = 0

    for fp in files:
        cnt = process_file(fp, ar_known, new_map, existing_mapped)
        if cnt:
            total_repl += cnt
            files_mod += 1
            rel = os.path.relpath(fp, os.path.dirname(__file__))
            print(f"  {rel}: {cnt} replacements")

    print(f"\nFiles modified: {files_mod}")
    print(f"Total replacements: {total_repl}")

    # Print new keys
    if new_map:
        keys_sorted = sorted(new_map.items(), key=lambda x: x[1])
        print(f"\nNew keys generated: {len(new_map)}")
        print("\n--- New keys ---")
        for ar, key in keys_sorted[:30]:
            print(f"  {key}: '{ar}'")
        if len(keys_sorted) > 30:
            print(f"  ... and {len(keys_sorted)-30} more")

        # Write to i18n.py
        with open(I18N_PATH, 'r', encoding='utf-8') as f:
            i18n_content = f.read()

        lines = []
        for ar, key in keys_sorted:
            escaped = ar.replace('\\', '\\\\').replace("'", "\\'")
            lines.append(f"    '{key}': {{'ar': '{escaped}', 'en': '{key}'}},")

        # Insert before the closing brace
        idx = i18n_content.rfind('\n}')
        if idx > 0:
            i18n_content = i18n_content[:idx] + '\n' + '\n'.join(lines) + i18n_content[idx:]

        with open(I18N_PATH, 'w', encoding='utf-8') as f:
            f.write(i18n_content)
        print(f"\nAdded {len(new_map)} new keys to {I18N_PATH}")

    # Verification
    print("\n" + "=" * 60)
    print("Verification")
    print("=" * 60)

    with open(I18N_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    kc = {}
    for m in re.finditer(r"'([^']+)':\s*\{", content):
        k = m.group(1)
        kc[k] = kc.get(k, 0) + 1
    dups = {k: v for k, v in kc.items() if v > 1}
    if dups:
        print("WARNING: Duplicate keys:")
        for k, v in sorted(dups.items()):
            print(f"  '{k}' x{v}")
    else:
        print("No duplicate keys found.")

    r = subprocess.run(['python', '-m', 'py_compile', I18N_PATH],
                       capture_output=True, text=True)
    if r.returncode == 0:
        print("i18n.py compiles successfully.")
    else:
        print(f"COMPILE ERROR:\n{r.stderr}")

    final = get_existing()
    # Add new keys not yet in final
    for ak in new_map:
        if ak not in final:
            final[ak] = new_map[ak]
    print(f"Final key count in TRANSLATIONS: {len(final)}")

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"1. New keys added to i18n.py: {len(new_map)}")
    print(f"2. Template files modified: {files_mod}")
    print(f"3. Replacements made: {total_repl}")
    w = '; '.join(f'{k}(x{v})' for k,v in sorted(dups.items())) if dups else 'None'
    print(f"4. Errors/Warnings: {w}")
    print(f"5. Final key count: {len(final)}")

if __name__ == '__main__':
    main()
    print("\nDone.")
