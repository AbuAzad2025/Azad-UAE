document.addEventListener('DOMContentLoaded', function() {
    document.addEventListener('keydown', function(e) {
        if (e.ctrlKey || e.metaKey) {
            switch(e.key.toLowerCase()) {
                case 'n':
                    e.preventDefault();
                    if (window.location.pathname.includes('sales')) {
                        window.location = '/sales/new';
                    } else if (window.location.pathname.includes('customers')) {
                        window.location = '/customers/new';
                    } else if (window.location.pathname.includes('products')) {
                        window.location = '/products/new';
                    }
                    break;
                
                case 'k':
                    e.preventDefault();
                    const searchInput = document.querySelector('#quick-search') || 
                                      document.querySelector('input[type="search"]') ||
                                      document.querySelector('input[name="search"]');
                    if (searchInput) {
                        searchInput.focus();
                        searchInput.select();
                    }
                    break;
                
                case 's':
                    if (document.querySelector('form')) {
                        e.preventDefault();
                        document.querySelector('form').submit();
                    }
                    break;
                
                case 'h':
                    e.preventDefault();
                    window.location = '/dashboard';
                    break;
            }
        }
        
        if (e.key === 'Escape') {
            const modal = document.querySelector('.modal.show');
            if (modal) {
                $(modal).modal('hide');
            }
        }
        
        if (e.altKey) {
            switch(e.key) {
                case '1':
                    e.preventDefault();
                    window.location = '/dashboard';
                    break;
                case '2':
                    e.preventDefault();
                    window.location = '/sales';
                    break;
                case '3':
                    e.preventDefault();
                    window.location = '/customers';
                    break;
                case '4':
                    e.preventDefault();
                    window.location = '/products';
                    break;
                case '5':
                    e.preventDefault();
                    window.location = '/payments';
                    break;
            }
        }
    });
    
    const helpText = document.createElement('div');
    helpText.id = 'keyboard-help';
    helpText.className = 'keyboard-shortcuts-help';
    helpText.innerHTML = `
        <div class="shortcuts-content">
            <h5>اختصارات لوحة المفاتيح</h5>
            <table>
                <tr><td>Ctrl+N</td><td>إضافة جديد</td></tr>
                <tr><td>Ctrl+K</td><td>بحث سريع</td></tr>
                <tr><td>Ctrl+S</td><td>حفظ</td></tr>
                <tr><td>Ctrl+H</td><td>الرئيسية</td></tr>
                <tr><td>Alt+1-5</td><td>التنقل السريع</td></tr>
                <tr><td>Esc</td><td>إغلاق النافذة</td></tr>
            </table>
        </div>
    `;
    helpText.style.cssText = 'display:none;position:fixed;bottom:20px;right:20px;background:white;padding:15px;border-radius:8px;box-shadow:0 4px 12px rgba(0,0,0,0.15);z-index:9999;';
    document.body.appendChild(helpText);
    
    document.addEventListener('keydown', function(e) {
        if (e.key === '?' && e.shiftKey) {
            e.preventDefault();
            const help = document.getElementById('keyboard-help');
            help.style.display = help.style.display === 'none' ? 'block' : 'none';
        }
    });
});

