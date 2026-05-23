class LazyLoader {
    constructor() {
        this.observers = new Map();
        this.init();
    }
    
    init() {
        if ('IntersectionObserver' in window) {
            const imageObserver = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        const img = entry.target;
                        if (img.dataset.src) {
                            img.src = img.dataset.src;
                            img.removeAttribute('data-src');
                            imageObserver.unobserve(img);
                        }
                    }
                });
            });
            
            this.observers.set('images', imageObserver);
            this.observeImages();
        }
    }
    
    observeImages() {
        const images = document.querySelectorAll('img[data-src]');
        const observer = this.observers.get('images');
        
        if (observer) {
            images.forEach(img => observer.observe(img));
        }
    }
    
    loadModule(moduleName) {
        return import(`/static/js/modules/${moduleName}.js`);
    }
}

const lazyLoader = new LazyLoader();
window.lazyLoader = lazyLoader;

