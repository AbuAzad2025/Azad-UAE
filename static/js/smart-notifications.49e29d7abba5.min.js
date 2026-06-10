class SmartNotifications {
    constructor() {
        this.queue = [];
        this.shown = new Set();
        this.init();
    }
    
    init() {
        this.checkLowStock();
        this.checkOverduePayments();
        this.checkSystemHealth();
        
        setInterval(() => this.processQueue(), 5000);
    }
    
    async checkLowStock() {
        try {
            const response = await fetch('/api/products/low-stock');
            const data = await response.json();
            
            if (data.success && data.products.length > 0) {
                this.notify({
                    id: 'low-stock',
                    title: 'تنبيه مخزون منخفض',
                    message: `${data.products.length} منتج بحاجة لإعادة طلب`,
                    type: 'warning',
                    action: '/warehouse',
                    priority: 'high'
                });
            }
        } catch (e) {        }
    }
    
    async checkOverduePayments() {
        try {
            const response = await fetch('/api/analytics/overdue-payments');
            const data = await response.json();
            
            if (data.success && data.count > 0) {
                this.notify({
                    id: 'overdue-payments',
                    title: 'مدفوعات متأخرة',
                    message: `${data.count} عميل لديهم مدفوعات متأخرة`,
                    type: 'info',
                    action: '/reports/receivables',
                    priority: 'medium'
                });
            }
        } catch (e) {        }
    }
    
    async checkSystemHealth() {
        try {
            const response = await fetch('/health');
            const data = await response.json();
            
            if (!data.database?.healthy || !data.disk?.healthy) {
                this.notify({
                    id: 'system-health',
                    title: 'تحذير النظام',
                    message: 'توجد مشكلة في صحة النظام',
                    type: 'error',
                    action: '/monitoring/dashboard',
                    priority: 'critical'
                });
            }
        } catch (e) {        }
    }
    
    notify(notification) {
        if (this.shown.has(notification.id)) {
            return;
        }
        
        this.queue.push(notification);
        this.shown.add(notification.id);
        
        setTimeout(() => this.shown.delete(notification.id), 3600000);
    }
    
    processQueue() {
        if (this.queue.length === 0) return;
        
        this.queue.sort((a, b) => {
            const priority = {'critical': 3, 'high': 2, 'medium': 1, 'low': 0};
            return priority[b.priority || 'low'] - priority[a.priority || 'low'];
        });
        
        const notification = this.queue.shift();
        this.show(notification);
    }
    
    show(notification) {
        if (typeof Swal !== 'undefined') {
            Swal.fire({
                icon: notification.type,
                title: notification.title,
                text: notification.message,
                showCancelButton: !!notification.action,
                confirmButtonText: notification.action ? 'عرض' : 'حسناً',
                cancelButtonText: 'إغلاق',
                timer: notification.priority === 'critical' ? null : 10000,
                timerProgressBar: true
            }).then((result) => {
                if (result.isConfirmed && notification.action) {
                    window.location = notification.action;
                }
            });
        }
    }
}

const smartNotifications = new SmartNotifications();
window.smartNotifications = smartNotifications;

