if ('serviceWorker' in navigator) {
    window.addEventListener('load', function() {
        navigator.serviceWorker.register('/static/sw.js')
            .then(function(registration) {                
                registration.addEventListener('updatefound', function() {
                    const newWorker = registration.installing;
                    
                    newWorker.addEventListener('statechange', function() {
                        if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                            if (confirm('تحديث جديد متاح. هل تريد تحديث الصفحة؟')) {
                                window.location.reload();
                            }
                        }
                    });
                });
            })
            .catch(function(err) {            });
        
        let refreshing = false;
        navigator.serviceWorker.addEventListener('controllerchange', function() {
            if (!refreshing) {
                refreshing = true;
                window.location.reload();
            }
        });
    });
}

if ('Notification' in window && navigator.serviceWorker) {
    Notification.requestPermission().then(function(permission) {
        if (permission === 'granted') {        }
    });
}

