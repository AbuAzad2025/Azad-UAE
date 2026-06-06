class AdvancedFeatures {
    static initAll() {
        this.initAutosave();
        this.initSmartForms();
        this.initQuickActions();
        this.initDataValidation();
    }

    static initAutosave() {
        const forms = document.querySelectorAll('[data-autosave]');
        forms.forEach(form => {
            const inputs = form.querySelectorAll('input, textarea, select');
            inputs.forEach(input => {
                input.addEventListener('change', () => {
                    const formData = new FormData(form);
                    const data = Object.fromEntries(formData);
                    localStorage.setItem(`autosave_${form.id}`, JSON.stringify(data));
                });
            });

            const saved = localStorage.getItem(`autosave_${form.id}`);
            if (saved) {
                const data = JSON.parse(saved);
                Object.keys(data).forEach(key => {
                    const input = form.querySelector(`[name="${key}"]`);
                    if (input) input.value = data[key];
                });
            }
        });
    }

    static initSmartForms() {
        document.querySelectorAll('[data-smart-calculate]').forEach(input => {
            input.addEventListener('blur', function() {
                const formula = this.dataset.smartCalculate;
                const result = AdvancedFeatures.evaluateFormula(formula, this.form);
                const target = this.form.querySelector(`[name="${this.dataset.target}"]`);
                if (target) target.value = result;
            });
        });
    }

    static evaluateFormula(formula, form) {
        try {
            const vars = {};
            formula.match(/\{(\w+)\}/g)?.forEach(match => {
                const varName = match.slice(1, -1);
                const input = form.querySelector(`[name="${varName}"]`);
                if (input) vars[varName] = parseFloat(input.value) || 0;
            });

            let expression = formula;
            Object.keys(vars).forEach(key => {
                expression = expression.replace(new RegExp(`\\{${key}\\}`, 'g'), vars[key]);
            });

            // التحقق من أن التعبير يحتوي فقط على أرقام وعمليات رياضية بسيطة لضمان الأمان
            if (!/^[\d\.\+\-\*\/\(\)\s]+$/.test(expression)) {
                return 0;
            }

            // استخدام محاسب آمن بسيط للمعاينة فقط (لا يعتمد للعمليات المالية النهائية)
            return AdvancedFeatures.safeMathEval(expression);
        } catch (e) {
            return 0;
        }
    }

    static safeMathEval(str) {
        // حساب معاينة فقط، ولا يعتمد للعمليات المالية النهائية.
        try {
            // تنظيف المسافات
            str = str.replace(/\s+/g, '');

            // استخدام آلية حساب يدوية آمنة للعمليات البسيطة (+, -, *, /)
            // ملاحظة: هذا يدعم العمليات الأساسية المتسلسلة
            const tokens = str.match(/(\d+\.?\d*)|[\+\-\*\/]/g);
            if (!tokens) return 0;

            let result = parseFloat(tokens[0]) || 0;
            for (let i = 1; i < tokens.length; i += 2) {
                const operator = tokens[i];
                const nextValue = parseFloat(tokens[i + 1]) || 0;

                if (operator === '+') result += nextValue;
                else if (operator === '-') result -= nextValue;
                else if (operator === '*') result *= nextValue;
                else if (operator === '/') result = nextValue !== 0 ? result / nextValue : 0;
            }
            return result;
        } catch (e) {
            return 0;
        }
    }

    static initQuickActions() {
        document.querySelectorAll('[data-quick-action]').forEach(button => {
            button.addEventListener('click', function(e) {
                e.preventDefault();
                const action = this.dataset.quickAction;
                AdvancedFeatures.executeQuickAction(action, this);
            });
        });
    }

    static async executeQuickAction(action, element) {
        switch(action) {
            case 'duplicate':
                window.location = element.href + '?duplicate=1';
                break;
            case 'print':
                window.print();
                break;
            case 'export':
                const url = element.dataset.exportUrl;
                window.location = url;
                break;
            case 'refresh':
                location.reload();
                break;
        }
    }

    static initDataValidation() {
        document.querySelectorAll('[data-validate]').forEach(input => {
            input.addEventListener('blur', function() {
                const rules = this.dataset.validate.split('|');
                const errors = [];

                rules.forEach(rule => {
                    if (rule === 'required' && !this.value) {
                        errors.push('هذا الحقل مطلوب');
                    }
                    if (rule.startsWith('min:')) {
                        const min = parseFloat(rule.split(':')[1]);
                        if (parseFloat(this.value) < min) {
                            errors.push(`القيمة يجب أن تكون ${min} أو أكثر`);
                        }
                    }
                    if (rule === 'email' && this.value && !this.value.includes('@')) {
                        errors.push('البريد الإلكتروني غير صحيح');
                    }
                });

                const errorDiv = this.parentElement.querySelector('.validation-error');
                if (errorDiv) errorDiv.remove();

                if (errors.length > 0) {
                    const div = document.createElement('div');
                    div.className = 'validation-error text-danger small';
                    div.textContent = errors[0];
                    this.parentElement.appendChild(div);
                    this.classList.add('is-invalid');
                } else {
                    this.classList.remove('is-invalid');
                    this.classList.add('is-valid');
                }
            });
        });
    }
}

document.addEventListener('DOMContentLoaded', function() {
    AdvancedFeatures.initAll();
});

window.AdvancedFeatures = AdvancedFeatures;
