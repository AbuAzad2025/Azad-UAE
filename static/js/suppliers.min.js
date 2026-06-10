/**
 * Suppliers Management JavaScript
 */

document.addEventListener('DOMContentLoaded', function() {
    // تهيئة DataTables
    if (document.querySelector('#suppliersTable')) {
        $('#suppliersTable').DataTable({
            language: {
                url: '/static/datatables/Arabic.json'
            },
            order: [[0, 'desc']],
            pageLength: 25
        });
    }

    // تأكيد الحذف
    document.querySelectorAll('.delete-supplier').forEach(btn => {
        btn.addEventListener('click', function(e) {
            if (!confirm('هل أنت متأكد من حذف هذا المورد؟')) {
                e.preventDefault();
            }
        });
    });

    // البحث السريع
    const searchInput = document.querySelector('#supplierSearch');
    if (searchInput) {
        searchInput.addEventListener('input', function(e) {
            const searchTerm = e.target.value.toLowerCase();
            const rows = document.querySelectorAll('.supplier-row');
            
            rows.forEach(row => {
                const text = row.textContent.toLowerCase();
                row.style.display = text.includes(searchTerm) ? '' : 'none';
            });
        });
    }
});

