class PerformanceMonitor {
    constructor() {
        this.metrics = [];
        this.enabled = true;
    }
    
    measurePageLoad() {
        if (!this.enabled || !window.performance) return;
        
        window.addEventListener('load', () => {
            const perfData = window.performance.timing;
            const pageLoadTime = perfData.loadEventEnd - perfData.navigationStart;
            const connectTime = perfData.responseEnd - perfData.requestStart;
            const renderTime = perfData.domComplete - perfData.domLoading;
            
            this.log('page_load', pageLoadTime);
            this.log('connect_time', connectTime);
            this.log('render_time', renderTime);
            
            if (pageLoadTime > 3000) {            }
        });
    }
    
    measureAPICall(url, startTime) {
        const duration = Date.now() - startTime;
        this.log('api_call', duration, {url: url});
        
        if (duration > 2000) {        }
        
        return duration;
    }
    
    log(metric, value, tags = {}) {
        const entry = {
            timestamp: new Date().toISOString(),
            metric: metric,
            value: value,
            tags: tags
        };
        
        this.metrics.push(entry);
        
        if (this.metrics.length > 100) {
            this.metrics.shift();
        }
        
        this.sendToServer(entry);
    }
    
    sendToServer(entry) {
        if (navigator.sendBeacon) {
            const blob = new Blob([JSON.stringify(entry)], {type: 'application/json'});
            navigator.sendBeacon('/monitoring/metrics', blob);
        }
    }
    
    getMetrics() {
        return this.metrics;
    }
    
    getAverageMetric(metricName) {
        const filtered = this.metrics.filter(m => m.metric === metricName);
        if (filtered.length === 0) return 0;
        
        const sum = filtered.reduce((acc, m) => acc + m.value, 0);
        return sum / filtered.length;
    }
}

const perfMonitor = new PerformanceMonitor();
perfMonitor.measurePageLoad();

window.perfMonitor = perfMonitor;

