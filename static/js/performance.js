// Performance Optimization Script
$(document).ready(function() {
    // Lazy loading for images
    if ('IntersectionObserver' in window) {
        const imageObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    img.src = img.dataset.src;
                    img.classList.remove('lazy');
                    imageObserver.unobserve(img);
                }
            });
        });

        document.querySelectorAll('img[data-src]').forEach(img => {
            imageObserver.observe(img);
        });
    }

    // Debounce function for search inputs
    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    // Optimize search inputs
    $('input[type="search"], input[placeholder*="بحث"], input[placeholder*="search"]').each(function() {
        const $input = $(this);
        const originalHandler = $input.data('events');
        
        if (originalHandler) {
            $input.off('input keyup');
            $input.on('input keyup', debounce(function() {
                if (originalHandler.input) {
                    originalHandler.input.forEach(handler => handler.handler.call(this));
                }
            }, 300));
        }
    });

    // Preload critical pages
    function preloadPage(url) {
        const link = document.createElement('link');
        link.rel = 'prefetch';
        link.href = url;
        document.head.appendChild(link);
    }

    $('.nav-link, .btn').hover(function() {
        const href = $(this).attr('href');
        if (href && href.startsWith('/') && !href.includes('#') &&
            !/\/\d+\/?$/.test(href) &&
            !/^\/(reports|owner|store|pos|api)\//.test(href) &&
            !/\?/.test(href)) {
            preloadPage(href);
        }
    });

    // Optimize DataTables
    if ($.fn.DataTable) {
        $.extend($.fn.dataTable.defaults, {
            "processing": true,
            "serverSide": false,
            "deferRender": true,
            "responsive": true,
            "pageLength": 25,
            "lengthMenu": [[10, 25, 50, 100], [10, 25, 50, 100]],
            "language": {
                "url": "/static/datatables/Arabic.json"
            },
            "dom": '<"row"<"col-sm-12 col-md-6"l><"col-sm-12 col-md-6"f>>' +
                   '<"row"<"col-sm-12"tr>>' +
                   '<"row"<"col-sm-12 col-md-5"i><"col-sm-12 col-md-7"p>>',
            "initComplete": function() {
                // Add loading class removal
                $(this).closest('.card').find('.card-body').removeClass('loading');
            }
        });
    }

    // Optimize form submissions
    $('form').on('submit', function() {
        const $form = $(this);
        const $submitBtn = $form.find('button[type="submit"], input[type="submit"]');
        
        // Disable submit button to prevent double submission
        $submitBtn.prop('disabled', true);
        
        // Add loading state
        $submitBtn.html('<i class="fas fa-spinner fa-spin mr-2"></i>جاري الحفظ...');
        
        // Re-enable after 5 seconds as fallback
        setTimeout(() => {
            $submitBtn.prop('disabled', false);
            $submitBtn.html($submitBtn.data('original-text') || 'حفظ');
        }, 5000);
    });

    // Store original button text
    $('button[type="submit"], input[type="submit"]').each(function() {
        $(this).data('original-text', $(this).html());
    });

    // Optimize AJAX requests
    $.ajaxSetup({
        timeout: 10000,
        cache: false,
        beforeSend: function(xhr, settings) {
            // Add loading indicator
            if (settings.type === 'POST' || settings.type === 'PUT' || settings.type === 'DELETE') {
                $('body').addClass('loading');
            }
        },
        complete: function() {
            $('body').removeClass('loading');
        },
        error: function(xhr, status) {
            if (status === 'timeout') {
                alert('انتهت مهلة الاتصال. يرجى المحاولة مرة أخرى.');
            } else if (xhr.status === 500) {
                alert('حدث خطأ في الخادم. يرجى المحاولة مرة أخرى.');
            }
        }
    });

    // Optimize scroll performance
    let ticking = false;
    function updateScrollPosition() {
        // Add scroll-based optimizations here
        ticking = false;
    }

    window.addEventListener('scroll', function() {
        if (!ticking) {
            requestAnimationFrame(updateScrollPosition);
            ticking = true;
        }
    });

    // Optimize resize performance
    let resizeTimeout;
    window.addEventListener('resize', function() {
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(function() {
            // Trigger DataTables responsive update
            if ($.fn.DataTable) {
                $.fn.dataTable.tables({ visible: true, api: true }).columns.adjust();
            }
        }, 250);
    });

    // تعطيل loading للبطاقات - يسبب مشاكل
    // $('.card').each(function() {
    //     const $card = $(this);
    //     if ($card.find('table').length > 0) {
    //         $card.find('.card-body').addClass('loading');
    //     }
    // });

    // Optimize tooltips
    $('[data-toggle="tooltip"]').tooltip({
        delay: { show: 500, hide: 100 }
    });

    // Optimize modals
    $('.modal').on('show.bs.modal', function() {
        $(this).find('input:first').focus();
    });

    // Add smooth scrolling
    $('a[href^="#"]').on('click', function(e) {
        const href = this.getAttribute('href');
        if (href && href !== '#') {
            e.preventDefault();
            const target = $(href);
            if (target.length) {
                $('html, body').animate({
                    scrollTop: target.offset().top - 100
                }, 500);
            }
        }
    });

    // Add performance monitoring - تحسين
    if (window.performance && (window.performance.timing || window.performance.getEntriesByType)) {
        window.addEventListener('load', function() {
            setTimeout(function() {
                // Use Navigation Timing API (modern) with timing fallback
                

            }, 100);
        });
    }
});

// CSS for loading states
const loadingCSS = `
.loading {
    position: relative;
    pointer-events: none;
}

.loading::after {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(255, 255, 255, 0.8);
    z-index: 1000;
    display: flex;
    align-items: center;
    justify-content: center;
}

.loading::before {
    content: 'جاري التحميل...';
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    z-index: 1001;
    background: var(--primary);
    color: white;
    padding: 10px 20px;
    border-radius: 5px;
    font-weight: 600;
}

.card-body.loading {
    min-height: 200px;
}

.card-body.loading::after {
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 40px;
    height: 40px;
    border: 4px solid #f3f3f3;
    border-top: 4px solid var(--primary-green);
    border-radius: 50%;
    animation: spin 1s linear infinite;
}

@keyframes spin {
    0% { transform: translate(-50%, -50%) rotate(0deg); }
    100% { transform: translate(-50%, -50%) rotate(360deg); }
}

img.lazy {
    opacity: 0;
    transition: opacity 0.3s;
}

img.lazy.loaded {
    opacity: 1;
}
`;

// Inject CSS
const style = document.createElement('style');
style.textContent = loadingCSS;
document.head.appendChild(style);
