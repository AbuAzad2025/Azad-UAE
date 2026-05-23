class RealtimeUpdates {
    constructor() {
        this.socket = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
    }
    
    connect() {
        if (typeof io === 'undefined') {
            console.log('Socket.IO not loaded');
            return;
        }
        
        this.socket = io();
        
        this.socket.on('connect', () => {
            console.log('Connected to server');
            this.reconnectAttempts = 0;
            this.socket.emit('subscribe_notifications');
        });
        
        this.socket.on('disconnect', () => {
            console.log('Disconnected from server');
            this.reconnect();
        });
        
        this.socket.on('sale_created', (data) => {
            this.showNotification('فاتورة جديدة', `تم إنشاء فاتورة ${data.sale_number}`, 'success');
            this.updateDashboardStats();
        });
        
        this.socket.on('payment_received', (data) => {
            this.showNotification('دفعة جديدة', `تم استلام دفعة ${data.amount} درهم`, 'info');
            this.updateDashboardStats();
        });
        
        this.socket.on('stock_alert', (data) => {
            this.showNotification('تنبيه مخزون', `المنتج ${data.product_name} - مخزون منخفض`, 'warning');
        });
        
        this.socket.on('notification', (data) => {
            this.showNotification('إشعار', data.message, data.type);
        });
    }
    
    reconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            setTimeout(() => {
                console.log(`Reconnecting... (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
                this.connect();
            }, 2000 * this.reconnectAttempts);
        }
    }
    
    showNotification(title, message, type = 'info') {
        if (typeof Swal !== 'undefined') {
            Swal.fire({
                toast: true,
                position: 'top-end',
                icon: type,
                title: title,
                text: message,
                showConfirmButton: false,
                timer: 3000,
                timerProgressBar: true
            });
        } else {
            console.log(`${title}: ${message}`);
        }
    }
    
    updateDashboardStats() {
        if (window.location.pathname === '/dashboard') {
            location.reload();
        }
    }
}

document.addEventListener('DOMContentLoaded', function() {
    const realtime = new RealtimeUpdates();
    realtime.connect();
});

