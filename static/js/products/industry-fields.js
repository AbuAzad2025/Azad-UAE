(function() {
    const INDUSTRY_SELECT = '#product_industry';
    const CONTAINER = '#industryFieldsContainer';
    const API_URL = '/api/industry-fields';
    function esc(v) {
        return String(v == null ? '' : v)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }
    function loadFields(industryCode) {
        const container = document.querySelector(CONTAINER);
        if (!container) return;
        container.innerHTML = '<div class="text-muted small"><i class="fas fa-spinner fa-spin"></i> جاري التحميل...</div>';
        fetch(`${API_URL}?industry=${encodeURIComponent(industryCode)}`, {
            headers: {'Accept': 'application/json'},
        }).then(r => r.json()).then(data => {
            if (!data.fields || data.fields.length === 0) {
                container.innerHTML = '';
                return;
            }
            let html = '<hr><h5 class="text-info"><i class="fas fa-cogs"></i> حقول إضافية (' + esc(data.industry) + ')</h5><div class="row">';
            data.fields.forEach(function(f) {
                const label = (document.dir === 'rtl' ? f.field_name_ar : f.field_name_en) || f.field_code;
                const requiredAttr = f.is_required ? ' required' : '';
                const reqStar = f.is_required ? ' <span class="text-danger">*</span>' : '';
                const code = esc(f.field_code);
                html += '<div class="col-md-6 col-lg-4">';
                html += '<div class="form-group">';
                html += '<label><i class="fas fa-sliders-h text-muted"></i> ' + esc(label) + reqStar + '</label>';
                if (f.field_type === 'textarea') {
                    html += '<textarea name="extra_' + code + '" class="form-control" rows="2"' + requiredAttr + '></textarea>';
                } else if (f.field_type === 'select' && f.field_options) {
                    html += '<select name="extra_' + code + '" class="form-control"' + requiredAttr + '>';
                    html += '<option value="">-- اختر --</option>';
                    f.field_options.split(',').forEach(function(opt) {
                        const o = opt.trim();
                        html += '<option value="' + esc(o) + '">' + esc(o) + '</option>';
                    });
                    html += '</select>';
                } else if (f.field_type === 'number') {
                    html += '<input type="number" name="extra_' + code + '" class="form-control" step="0.01"' + requiredAttr + '>';
                } else if (f.field_type === 'date') {
                    html += '<input type="date" name="extra_' + code + '" class="form-control"' + requiredAttr + '>';
                } else {
                    html += '<input type="text" name="extra_' + code + '" class="form-control"' + requiredAttr + '>';
                }
                html += '</div></div>';
            });
            html += '</div>';
            container.innerHTML = html;
        }).catch(function() {
            container.innerHTML = '';
        });
    }
    function init() {
        const select = document.querySelector(INDUSTRY_SELECT);
        if (!select) return;
        select.addEventListener('change', function() {
            loadFields(this.value);
        });
        if (select.value && select.value !== 'general') {
            loadFields(select.value);
        }
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
