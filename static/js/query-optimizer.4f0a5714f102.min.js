class QueryOptimizer {
    constructor() {
        this.cache = new Map();
        this.cacheTimeout = 60000;
    }
    
    async fetchWithCache(url, options = {}) {
        const cacheKey = this.getCacheKey(url, options);
        
        const cached = this.cache.get(cacheKey);
        if (cached && (Date.now() - cached.timestamp < this.cacheTimeout)) {            return cached.data;
        }
        
        const startTime = Date.now();
        const response = await fetch(url, options);
        const data = await response.json();
        
        if (window.perfMonitor) {
            window.perfMonitor.measureAPICall(url, startTime);
        }
        
        this.cache.set(cacheKey, {
            data: data,
            timestamp: Date.now()
        });
        
        return data;
    }
    
    getCacheKey(url, options) {
        return `${url}_${JSON.stringify(options)}`;
    }
    
    invalidateCache(pattern) {
        for (const key of this.cache.keys()) {
            if (key.includes(pattern)) {
                this.cache.delete(key);
            }
        }
    }
    
    clearCache() {
        this.cache.clear();
    }
}

window.queryOptimizer = new QueryOptimizer();

