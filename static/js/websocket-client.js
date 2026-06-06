class WebSocketClient {
    constructor() {
        this.socket = null;
        this.connected = false;
        this.reconnectDelay = 1000;
        this.maxReconnectDelay = 30000;
        this.reconnectAttempts = 0;
    }
    
    connect(url = null) {
        if (this.socket && this.connected) {
            return;
        }
        
        const wsUrl = url || (window.location.protocol === 'https:' ? 'wss://' : 'ws://') + 
                             window.location.host + '/socket.io/';
        
        try {
            if (typeof io !== 'undefined') {
                this.socket = io();
                this.setupHandlers();
            }
        } catch (error) {
            console.error('WebSocket connection failed:', error);
            this.scheduleReconnect();
        }
    }
    
    setupHandlers() {
        this.socket.on('connect', () => {
            console.log('WebSocket connected');
            this.connected = true;
            this.reconnectAttempts = 0;
            this.reconnectDelay = 1000;
            
            this.emit('authenticate', {
                user_id: window.currentUserId
            });
        });
        
        this.socket.on('disconnect', () => {
            this.connected = false;
            this.scheduleReconnect();
        });
        
        this.socket.on('sale_created', (data) => {
            this.handleSaleCreated(data);
        });
        
        this.socket.on('payment_received', (data) => {
            this.handlePaymentReceived(data);
        });
        
        this.socket.on('stock_alert', (data) => {
            this.handleStockAlert(data);
        });
        
        this.socket.on('notification', (data) => {
            this.showNotification(data.message, data.type);
        });
    }
    
    scheduleReconnect() {
        if (this.reconnectAttempts >= 10) {
            console.log('Max reconnect attempts reached');
            return;
        }
        
        setTimeout(() => {
            console.log(`Reconnecting... (attempt ${this.reconnectAttempts + 1})`);
            this.reconnectAttempts++;
            this.connect();
            
            this.reconnectDelay = Math.min(
                this.reconnectDelay * 2,
                this.maxReconnectDelay
            );
        }, this.reconnectDelay);
    }
    
    emit(event, data) {
        if (this.socket && this.connected) {
            this.socket.emit(event, data);
        }
    }
    
    handleSaleCreated(data) {
        this.showNotification(`فاتورة جديدة: ${data.sale_number}`, 'success');
        
        if (window.location.pathname === '/sales') {
            this.refreshSalesList();
        }
    }
    
    handlePaymentReceived(data) {
        this.showNotification(`دفعة جديدة: ${data.amount} درهم`, 'info');
        
        if (window.location.pathname.includes('/payments')) {
            this.refreshPaymentsList();
        }
    }
    
    handleStockAlert(data) {
        this.showNotification(`تنبيه مخزون: ${data.product_name}`, 'warning');
    }
    
    showNotification(message, type = 'info') {
        if (typeof Swal !== 'undefined') {
            const Toast = Swal.mixin({
                toast: true,
                position: 'top-end',
                showConfirmButton: false,
                timer: 3000,
                timerProgressBar: true,
                didOpen: (toast) => {
                    toast.addEventListener('mouseenter', Swal.stopTimer)
                    toast.addEventListener('mouseleave', Swal.resumeTimer)
                }
            });
            
            Toast.fire({
                icon: type,
                title: message
            });
        }
    }
    
    refreshSalesList() {
        const table = $('#sales-table').DataTable();
        if (table) {
            table.ajax.reload(null, false);
        }
    }
    
    refreshPaymentsList() {
        const table = $('#payments-table').DataTable();
        if (table) {
            table.ajax.reload(null, false);
        }
    }
}

const wsClient = new WebSocketClient();

document.addEventListener('DOMContentLoaded', function() {
    wsClient.connect();
});

window.wsClient = wsClient;

