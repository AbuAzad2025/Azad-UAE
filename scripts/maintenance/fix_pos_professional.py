import re

path = r'D:\Data\karaj\UAE\Azad-UAE\templates\pos\index.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add alert inside openSessionModal body
old1 = '''      <div class="modal-body">
        <div class="form-group">
          <label>رصيد الافتتاح (نقدي)</label>
          <input id="openSessionBalance" type="number" step="0.01" class="form-control" value="0">
        </div>
        <div class="form-group">
          <label>ملاحظات</label>
          <textarea id="openSessionNotes" class="form-control" rows="2" placeholder="اختياري"></textarea>
        </div>
      </div>'''
new1 = '''      <div class="modal-body">
        <div id="openSessionAlert" class="alert d-none mb-3"></div>
        <div class="form-group">
          <label>رصيد الافتتاح (نقدي)</label>
          <input id="openSessionBalance" type="number" step="0.01" class="form-control" value="0">
        </div>
        <div class="form-group">
          <label>ملاحظات</label>
          <textarea id="openSessionNotes" class="form-control" rows="2" placeholder="اختياري"></textarea>
        </div>
      </div>'''
content = content.replace(old1, new1)

# 2. Add alert inside closeSessionModal body
old2 = '''      <div class="modal-body">
        <div class="alert alert-info">
          <strong>رصيد الافتتاح:</strong> <span id="closeOpening">0.00</span><br>
          <strong>إجمالي المبيعات النقدية:</strong> <span id="closeCashSales">0.00</span><br>
          <strong>الرصيد المتوقع:</strong> <span id="closeExpected">0.00</span>
        </div>
        <div class="form-group">
          <label>الرصيد الفعلي (المعدود في الدرج)</label>
          <input id="closeSessionBalance" type="number" step="0.01" class="form-control">
        </div>
        <div class="form-group">
          <label>ملاحظات</label>
          <textarea id="closeSessionNotes" class="form-control" rows="2" placeholder="اختياري"></textarea>
        </div>
      </div>'''
new2 = '''      <div class="modal-body">
        <div id="closeSessionAlert" class="alert d-none mb-3"></div>
        <div class="alert alert-info">
          <strong>رصيد الافتتاح:</strong> <span id="closeOpening">0.00</span><br>
          <strong>إجمالي المبيعات النقدية:</strong> <span id="closeCashSales">0.00</span><br>
          <strong>الرصيد المتوقع:</strong> <span id="closeExpected">0.00</span>
        </div>
        <div class="form-group">
          <label>الرصيد الفعلي (المعدود في الدرج)</label>
          <input id="closeSessionBalance" type="number" step="0.01" class="form-control">
        </div>
        <div class="form-group">
          <label>ملاحظات</label>
          <textarea id="closeSessionNotes" class="form-control" rows="2" placeholder="اختياري"></textarea>
        </div>
      </div>'''
content = content.replace(old2, new2)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated templates/pos/index.html")
