import re

path = r'D:\Data\karaj\UAE\Azad-UAE\static\js\pos\index.js'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add modal alert helper after showAlert
old_showAlert = '''    const showAlert = (msg, level='danger') => {
        const el = qs('#posAlert');
        el.className = 'alert alert-' + level;
        el.textContent = msg;
        el.classList.remove('d-none');
        setTimeout(()=>{ el.classList.add('d-none'); }, 5000);
    };'''

new_showAlert = '''    const showAlert = (msg, level='danger') => {
        const el = qs('#posAlert');
        el.className = 'alert alert-' + level;
        el.textContent = msg;
        el.classList.remove('d-none');
        setTimeout(()=>{ el.classList.add('d-none'); }, 5000);
    };
    const showModalAlert = (modalId, msg, level='danger') => {
        const el = qs('#' + modalId + 'Alert');
        if (!el) { showAlert(msg, level); return; }
        el.className = 'alert alert-' + level + ' mb-3';
        el.textContent = msg;
        el.classList.remove('d-none');
        setTimeout(()=>{ el.classList.add('d-none'); }, 6000);
    };
    const hideModalAlert = (modalId) => {
        const el = qs('#' + modalId + 'Alert');
        if (el) el.classList.add('d-none');
    };'''

content = content.replace(old_showAlert, new_showAlert)

# 2. Update openSessionConfirm to use modal alert
old_open = '''    qs('#openSessionConfirm').addEventListener('click', async () => {
        const balance = toNum(qs('#openSessionBalance').value);
        const notes = qs('#openSessionNotes').value.trim();
        qs('#openSessionConfirm').disabled = true;
        try {
            const r = await fetch('/pos/api/session/open', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
                credentials: 'same-origin',
                body: JSON.stringify({ opening_balance: balance, notes: notes || undefined })
            });
            const j = await r.json();
            if (!r.ok || !j.success) throw new Error(j.error || 'فشل فتح الجلسة');
            $('#openSessionModal').modal('hide');
            await loadSession();
            showAlert('تم فتح الجلسة: ' + j.session.number, 'success');
        } catch (err) {
            showAlert(err.message, 'danger');
        } finally {
            qs('#openSessionConfirm').disabled = false;
        }
    });'''

new_open = '''    qs('#openSessionConfirm').addEventListener('click', async () => {
        const balance = toNum(qs('#openSessionBalance').value);
        const notes = qs('#openSessionNotes').value.trim();
        hideModalAlert('openSession');
        qs('#openSessionConfirm').disabled = true;
        try {
            const r = await fetch('/pos/api/session/open', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
                credentials: 'same-origin',
                body: JSON.stringify({ opening_balance: balance, notes: notes || undefined })
            });
            const j = await r.json();
            if (!r.ok || !j.success) throw new Error(j.error || 'فشل فتح الجلسة');
            $('#openSessionModal').modal('hide');
            await loadSession();
            showAlert('تم فتح الجلسة: ' + j.session.number, 'success');
        } catch (err) {
            showModalAlert('openSession', err.message, 'danger');
        } finally {
            qs('#openSessionConfirm').disabled = false;
        }
    });'''

content = content.replace(old_open, new_open)

# 3. Update closeSessionBtn to hide alert and show error if report fails
old_close_btn = '''    qs('#closeSessionBtn').addEventListener('click', async () => {
        try {
            const r = await fetch('/pos/api/session/report', { credentials: 'same-origin' });
            const j = await r.json();
            if (j.success && j.session) {
                qs('#closeOpening').textContent = fmt(j.session.opening_balance);
                qs('#closeCashSales').textContent = fmt(j.session.total_cash_sales);
                qs('#closeExpected').textContent = fmt((j.session.opening_balance || 0) + (j.session.total_cash_sales || 0));
            }
        } catch (_) {}
        qs('#closeSessionBalance').value = '';
        qs('#closeSessionNotes').value = '';
        $('#closeSessionModal').modal('show');
    });'''

new_close_btn = '''    qs('#closeSessionBtn').addEventListener('click', async () => {
        hideModalAlert('closeSession');
        let reportLoaded = false;
        try {
            const r = await fetch('/pos/api/session/report', { credentials: 'same-origin' });
            const j = await r.json();
            if (j.success && j.session) {
                qs('#closeOpening').textContent = fmt(j.session.opening_balance);
                qs('#closeCashSales').textContent = fmt(j.session.total_cash_sales);
                qs('#closeExpected').textContent = fmt((j.session.opening_balance || 0) + (j.session.total_cash_sales || 0));
                reportLoaded = true;
            }
        } catch (err) {
            showModalAlert('closeSession', 'تعذر تحميل بيانات الجلسة: ' + (err.message || 'خطأ غير معروف'), 'warning');
        }
        qs('#closeSessionBalance').value = '';
        qs('#closeSessionNotes').value = '';
        $('#closeSessionModal').modal('show');
    });'''

content = content.replace(old_close_btn, new_close_btn)

# 4. Update closeSessionConfirm to use modal alert
old_close_confirm = '''    qs('#closeSessionConfirm').addEventListener('click', async () => {
        const balance = toNum(qs('#closeSessionBalance').value);
        if (!balance && balance !== 0) {
            showAlert('يرجى إدخال رصيد الإغلاق.', 'warning');
            return;
        }
        const notes = qs('#closeSessionNotes').value.trim();
        qs('#closeSessionConfirm').disabled = true;
        try {
            const r = await fetch('/pos/api/session/close', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
                credentials: 'same-origin',
                body: JSON.stringify({ closing_balance: balance, notes: notes || undefined })
            });
            const j = await r.json();
            if (!r.ok || !j.success) throw new Error(j.error || 'فشل إغلاق الجلسة');
            $('#closeSessionModal').modal('hide');
            await loadSession();
            const diff = j.session.difference;
            if (Math.abs(diff) > 0.01) {
                showAlert('تم إغلاق الجلسة. فرق الرصيد: ' + fmt(diff), diff < 0 ? 'danger' : 'warning');
            } else {
                showAlert('تم إغلاق الجلسة بنجاح. الرصيد مطابق.', 'success');
            }
        } catch (err) {
            showAlert(err.message, 'danger');
        } finally {
            qs('#closeSessionConfirm').disabled = false;
        }
    });'''

new_close_confirm = '''    qs('#closeSessionConfirm').addEventListener('click', async () => {
        const balance = toNum(qs('#closeSessionBalance').value);
        if (balance === '' || Number.isNaN(Number(qs('#closeSessionBalance').value))) {
            showModalAlert('closeSession', 'يرجى إدخال رصيد الإغلاق.', 'warning');
            return;
        }
        const notes = qs('#closeSessionNotes').value.trim();
        hideModalAlert('closeSession');
        qs('#closeSessionConfirm').disabled = true;
        try {
            const r = await fetch('/pos/api/session/close', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
                credentials: 'same-origin',
                body: JSON.stringify({ closing_balance: balance, notes: notes || undefined })
            });
            const j = await r.json();
            if (!r.ok || !j.success) throw new Error(j.error || 'فشل إغلاق الجلسة');
            $('#closeSessionModal').modal('hide');
            await loadSession();
            const diff = j.session.difference;
            if (Math.abs(diff) > 0.01) {
                showAlert('تم إغلاق الجلسة. فرق الرصيد: ' + fmt(diff), diff < 0 ? 'danger' : 'warning');
            } else {
                showAlert('تم إغلاق الجلسة بنجاح. الرصيد مطابق.', 'success');
            }
        } catch (err) {
            showModalAlert('closeSession', err.message, 'danger');
        } finally {
            qs('#closeSessionConfirm').disabled = false;
        }
    });'''

content = content.replace(old_close_confirm, new_close_confirm)

# 5. Auto-focus barcode after done modal closes (add event listener for hidden.bs.modal)
old_loadSession = '''    loadSession();'''
new_loadSession = '''    $('#posDoneModal').on('hidden.bs.modal', function () {
        qs('#productSearch').focus();
    });
    loadSession();'''

content = content.replace(old_loadSession, new_loadSession)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated static/js/pos/index.js")
