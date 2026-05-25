class NotificationSystem {
    constructor() {
        this.permission = 'default';
        this.queue = [];
        this.init();
    }
    
    async init() {
        if ('Notification' in window) {
            this.permission = await Notification.requestPermission();
        }
    }
    
    show(title, options = {}) {
        if (this.permission === 'granted') {
            const notification = new Notification(title, {
                body: options.body || '',
                icon: options.icon || '/static/img/logo.png',
                badge: '/static/img/azad_favicon.png',
                tag: options.tag || 'default',
                requireInteraction: options.requireInteraction || false,
                ...options
            });
            
            notification.onclick = function(event) {
                event.preventDefault();
                window.focus();
                if (options.url) {
                    window.location.href = options.url;
                }
                notification.close();
            };
            
            return notification;
        } else {
            this.showFallback(title, options);
        }
    }
    
    showFallback(title, options) {
        if (typeof Swal !== 'undefined') {
            const Toast = Swal.mixin({
                toast: true,
                position: 'top-end',
                showConfirmButton: false,
                timer: 3000,
                timerProgressBar: true
            });
            
            Toast.fire({
                icon: options.type || 'info',
                title: title,
                text: options.body
            });
        } else {
            alert(`${title}\n${options.body || ''}`);
        }
    }
    
    notifyNewSale(saleData) {
        this.show('فاتورة جديدة', {
            body: `${saleData.sale_number} - ${saleData.total_amount} درهم`,
            icon: '/static/img/invoice-icon.png',
            tag: 'new-sale',
            url: `/sales/view/${saleData.id}`
        });
    }
    
    notifyPayment(paymentData) {
        this.show('دفعة جديدة', {
            body: `استلام ${paymentData.amount} درهم`,
            icon: '/static/img/payment-icon.png',
            tag: 'new-payment',
            type: 'success'
        });
    }
    
    notifyLowStock(productData) {
        this.show('تنبيه مخزون', {
            body: `${productData.name} - المخزون منخفض`,
            icon: '/static/img/alert-icon.png',
            tag: 'low-stock',
            requireInteraction: true,
            type: 'warning'
        });
    }
}

const notificationSystem = new NotificationSystem();
window.notificationSystem = notificationSystem;

