class AdvancedSearch {
    constructor(options = {}) {
        this.endpoint = options.endpoint || '/api/v2/search';
        this.onResult = options.onResult || function() {};
        this.debounceDelay = options.debounceDelay || 300;
        this.minLength = options.minLength || 2;
        this.debounceTimer = null;
    }
    
    search(query, filters = {}) {
        clearTimeout(this.debounceTimer);
        
        if (query.length < this.minLength) {
            return;
        }
        
        this.debounceTimer = setTimeout(() => {
            this.executeSearch(query, filters);
        }, this.debounceDelay);
    }
    
    async executeSearch(query, filters) {
        const startTime = Date.now();
        
        try {
            const params = new URLSearchParams({
                q: query,
                ...filters
            });
            
            const response = await fetch(`${this.endpoint}?${params}`);
            const data = await response.json();
            
            if (window.perfMonitor) {
                window.perfMonitor.measureAPICall(this.endpoint, startTime);
            }
            
            this.onResult(data);
        } catch (error) {            this.onResult({success: false, error: error.message});
        }
    }
    
    clear() {
        clearTimeout(this.debounceTimer);
    }
}

window.AdvancedSearch = AdvancedSearch;

