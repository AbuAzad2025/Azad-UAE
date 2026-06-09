/**
 * Ultra Fast Performance Optimizer
 * تحسين الأداء الفائق - تجربة مستخدم لا مثيل لها
 */

(function() {
  'use strict';

  // ========== Performance Optimizer ==========
  const Performance = {
    // Lazy Load Images
    lazyLoadImages() {
      if ('IntersectionObserver' in window) {
        const imageObserver = new IntersectionObserver((entries, observer) => {
          entries.forEach(entry => {
            if (entry.isIntersecting) {
              const img = entry.target;
              img.src = img.dataset.src;
              img.classList.add('loaded');
              observer.unobserve(img);
            }
          });
        });

        document.querySelectorAll('img[data-src]').forEach(img => {
          imageObserver.observe(img);
        });
      }
    },

    prefetchLinks() {
      document.querySelectorAll('a[href^="/"]').forEach(link => {
        const url = link.getAttribute('href');
        if (!url) return;
        if (/\/\d+\/?$/.test(url)) return;
        if (/^\/(reports|owner|store|pos|api)\//.test(url)) return;
        if (/\?/.test(url)) return;
        link.addEventListener('mouseenter', function() {
          const hoverUrl = this.getAttribute('href');
          if (hoverUrl && !document.querySelector(`link[rel="prefetch"][href="${hoverUrl}"]`)) {
            const prefetch = document.createElement('link');
            prefetch.rel = 'prefetch';
            prefetch.href = hoverUrl;
            document.head.appendChild(prefetch);
          }
        }, { once: true });
      });
    },

    // Debounce Function
    debounce(func, wait) {
      let timeout;
      return function executedFunction(...args) {
        const later = () => {
          clearTimeout(timeout);
          func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
      };
    },

    // Throttle Function
    throttle(func, limit) {
      let inThrottle;
      return function() {
        const args = arguments;
        const context = this;
        if (!inThrottle) {
          func.apply(context, args);
          inThrottle = true;
          setTimeout(() => inThrottle = false, limit);
        }
      };
    },

    // Initialize All
    init() {
      this.lazyLoadImages();
      this.prefetchLinks();
      
      // Smooth Scroll
      document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
          const target = document.querySelector(this.getAttribute('href'));
          if (target) {
            e.preventDefault();
            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
          }
        });
      });    }
  };

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => Performance.init());
  } else {
    Performance.init();
  }

})();

