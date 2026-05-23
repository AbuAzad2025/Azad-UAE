/**
 * Advanced Notification System
 * نظام إشعارات احترافي مع Toast + Sound + Vibration
 */

class NotificationManager {
    constructor() {
        this.container = null;
        this.userHasInteracted = false; // Track user interaction for vibration API
        this.sounds = {
            success: new Audio('data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2/LDciUFLIHO8tiJNwgZaLvt559NEAxQp+PwtmMcBjiR1/LMeSwFJHfH8N2QQAoUXrTp66hVFApGn+DyvmwhBi6Bzvi6bh0HH27A7+OHUQ0MUqzn77BhGggziNXzzn0pBSh+zPLaizsKGGS46eihUhELTKXh8bllHAU2jdj0yoAtBSJ6yPDajjwKF12y6OioVBIKSKHf8bllHAU3jtj0yoEtBSJ6yO/ajTsKGF+y6OmoUxELTKPh8bllHAU3jtf0y4EtBSF7yO/bjDwKGF+y6OmpUxELTKPh8bllHAY3jtf0y4EtBSJ7yO/bjDsKGF+z6OmoUxELTKPh8bllHAY3jtf0y4EtBSJ7yO/bjDwKGF+z6OmpUxELTKPh8bllHAY3jtf0y4EtBSJ7yO/bjDsKGF+z6OmpUxELTKPh8bllHAY3jtf0y4EtBSJ7yO/bjDwKGF+z6OmpUxELTKPh8bllHAY3jtf0y4EtBSJ7yO/bjDsKGF+z6OmpUxELTKPh8bllHAY3jtf0y4EtBSJ7yO/bjDwKGF+z6OmpUxELTKPh8bllHAY3jtf0y4EtBSJ7yO/bjDsKGF+z6OmpUxELTKPh8bllHAY3jtf0y4EtBSJ7yO/bjDwKGF+z6OmpUxELTKPh8bllHAY3jtf0y4EtBSJ7yO/bjDsKGF+z6OmpUxELTKPh8bllHAY3jtf0y4EtBSJ7yO/bjDwKGF+z6OmpUxELTKPh8bllHAY3jtf0y4EtBSJ7yO/bjDsKGF+z6OmpUxELTKPh8bllHAY3jtf0y4EtBSJ7yO/bjDwKGF+z6OmpUxELTKPh8bllHAY3jtf0y4EtBSJ7yO/bjDsKGF+z6OmpUxELTKPh8bllHAY3jtf0y4EtBSJ7yO/bjDwKGF+z6OmpUxELTKPh8bllHAY3jtf0y4EtBSJ7yO/bjDsKGF+z6OmpUxELTKPh8bllHAY3jtf0y4EtBSJ7yO/bjDwKGF+z6OmpUxELTKPh8bllHAY3jtf0y4EtBSJ7yO/bjDsKGF+z6OmpUxELTKPh8bllHAY3jtf0y4EtBSJ7yO/bjDwKGF+z6OmpUxELTKPh8bllHAY3jtf0y4EtBSJ7yO/bjDsKGF+z6OmpUxELTKPh8bllHAY3jtf0y4EtBSJ7yO/bjDwKGF+z6OmpUxELTKPh8bllHAY3jtf0y4EtBSJ7yO/bjDsKGF+z6OmpUxELTKPh8bllHAY3jtf0y4EtBSJ7yO/bjDwKGF+z6OmpUxELTKPh8bllHAY3jtf0y4EtBQ=='),
            error: new Audio('data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAAB/fn9/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/fQ=='),
            warning: new Audio('data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACAgYGCgoODhISFhYaGh4eIiImJioqLi4yMjY2Ojo+PkJCRkZKSk5OUlJWVlpaXl5iYmZmampubm5ycnZ2enp+foKCgoaGio6OkpKWlpqanp6ioqamqqquqq6yrrKysra6rrq6vr7CwsbCxsbKys7O0tLS1tba2t7e3uLi5ubq6u7u8vLy9vr6/v8DAwcHCwsPDw8TFxcbGx8fIyMnJysrLy8zMzc3Ozs/P0NDR0dLS09PU1NXV1tbX19jY2dna2tvb3Nzd3d7e39/g4OHh4uLj4+Tk5eXm5ufn6Ojp6erq6+vs7O3t7u7v7/Dw8fHy8vPz9PT19fb29/f4+Pn5+vr7+/z8/f3+/v////7+/f39/Pz7+/r6+fn4+Pf39vb19fT08/Py8vHx8PDv7+7u7e3s7Ovr6urp6ejo5+fm5uXl5OTj4+Li4eHg4N/f3t7d3dzc29va2tnZ2NjX19bW1dXU1NPT0tLR0dDQ0M/Pzs7Nzc3My8vKysnJyMjHx8bGxcXExMPDwsLBwcDAwMC/v76+vb29vLy7u7q6ubi4uLe3tra1tbW0tLOzsrKxsbCwsK+vr66urq2trKysq6uqqqqpqKioqKenp6ampaWkpKSkpaSlpKSko6OioqGhoa==')
        };
        this.init();
        this.trackUserInteraction();
    }

    init() {
        // Create notification container
        if (!document.getElementById('toast-container')) {
            this.container = document.createElement('div');
            this.container.id = 'toast-container';
            this.container.className = 'toast-container';
            document.body.appendChild(this.container);
        } else {
            this.container = document.getElementById('toast-container');
        }

        // Inject CSS
        this.injectStyles();
    }

    trackUserInteraction() {
        // Track first user interaction to enable vibration API
        const enableInteraction = () => {
            this.userHasInteracted = true;
            // Remove listeners after first interaction
            document.removeEventListener('click', enableInteraction);
            document.removeEventListener('touchstart', enableInteraction);
            document.removeEventListener('keydown', enableInteraction);
        };
        
        document.addEventListener('click', enableInteraction, { once: true, passive: true });
        document.addEventListener('touchstart', enableInteraction, { once: true, passive: true });
        document.addEventListener('keydown', enableInteraction, { once: true, passive: true });
    }

    injectStyles() {
        if (document.getElementById('toast-styles')) return;

        const style = document.createElement('style');
        style.id = 'toast-styles';
        style.textContent = `
            .toast-container {
                position: fixed;
                top: 80px;
                left: 20px;
                z-index: 99999;
                pointer-events: none;
            }

            .toast {
                position: relative;
                min-width: 300px;
                max-width: 500px;
                padding: 15px 20px;
                margin-bottom: 15px;
                background: white;
                border-radius: 12px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.15);
                pointer-events: all;
                animation: slideIn 0.3s ease-out;
                display: flex;
                align-items: center;
                gap: 12px;
                border-right: 5px solid;
                font-family: 'Tajawal', sans-serif;
            }

            .toast.toast-success { border-right-color: #28a745; }
            .toast.toast-error { border-right-color: #dc3545; }
            .toast.toast-warning { border-right-color: #ffc107; }
            .toast.toast-info { border-right-color: #17a2b8; }

            .toast-icon {
                font-size: 24px;
                flex-shrink: 0;
                width: 35px;
                height: 35px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: 50%;
            }

            .toast-success .toast-icon {
                background: #d4edda;
                color: #28a745;
            }

            .toast-error .toast-icon {
                background: #f8d7da;
                color: #dc3545;
            }

            .toast-warning .toast-icon {
                background: #fff3cd;
                color: #ffc107;
            }

            .toast-info .toast-icon {
                background: #d1ecf1;
                color: #17a2b8;
            }

            .toast-content {
                flex: 1;
            }

            .toast-title {
                font-weight: 700;
                font-size: 15px;
                margin-bottom: 3px;
                color: #333;
            }

            .toast-message {
                font-size: 14px;
                color: #666;
                line-height: 1.4;
            }

            .toast-close {
                cursor: pointer;
                background: transparent;
                border: none;
                font-size: 20px;
                color: #999;
                padding: 0;
                width: 24px;
                height: 24px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: 50%;
                transition: all 0.2s;
            }

            .toast-close:hover {
                background: #f0f0f0;
                color: #333;
            }

            .toast-progress {
                position: absolute;
                bottom: 0;
                right: 0;
                height: 3px;
                background: currentColor;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
                animation: progress linear;
            }

            @keyframes slideIn {
                from {
                    transform: translateX(-100%);
                    opacity: 0;
                }
                to {
                    transform: translateX(0);
                    opacity: 1;
                }
            }

            @keyframes slideOut {
                from {
                    transform: translateX(0);
                    opacity: 1;
                }
                to {
                    transform: translateX(-100%);
                    opacity: 0;
                }
            }

            @keyframes progress {
                from { width: 100%; }
                to { width: 0%; }
            }

            .toast.removing {
                animation: slideOut 0.3s ease-in forwards;
            }
        `;
        document.head.appendChild(style);
    }

    show(options) {
        const {
            type = 'info',
            title = '',
            message = '',
            duration = 10000,
            sound = true,
            vibrate = true
        } = options;

        // Create toast element
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;

        // Icon
        const icons = {
            success: '✓',
            error: '✕',
            warning: '⚠',
            info: 'ℹ'
        };

        // Progress bar
        const progress = document.createElement('div');
        progress.className = 'toast-progress';
        progress.style.animationDuration = `${duration}ms`;

        toast.innerHTML = `
            <div class="toast-icon">${icons[type]}</div>
            <div class="toast-content">
                ${title ? `<div class="toast-title">${title}</div>` : ''}
                <div class="toast-message">${message}</div>
            </div>
            <button class="toast-close" onclick="this.closest('.toast').remove()">×</button>
        `;
        toast.appendChild(progress);

        // Add to container
        this.container.appendChild(toast);

        // Play sound (only after user interaction to comply with browser policies)
        if (sound && this.sounds[type]) {
            this.sounds[type].volume = 0.3;
            this.sounds[type].play().catch(() => {
                // Silently fail if autoplay is blocked
            });
        }

        // Vibrate (only if user has interacted with the page)
        if (vibrate && 'vibrate' in navigator && this.userHasInteracted) {
            const patterns = {
                success: [100],
                error: [100, 50, 100],
                warning: [50, 50, 50],
                info: [50]
            };
            navigator.vibrate(patterns[type] || [50]);
        }

        // Auto remove
        setTimeout(() => {
            toast.classList.add('removing');
            setTimeout(() => toast.remove(), 300);
        }, duration);

        return toast;
    }

    success(message, title = 'نجح!') {
        return this.show({ type: 'success', title, message });
    }

    error(message, title = 'خطأ!') {
        return this.show({ type: 'error', title, message, duration: 20000 });
    }

    warning(message, title = 'تحذير!') {
        return this.show({ type: 'warning', title, message });
    }

    info(message, title = 'معلومة') {
        return this.show({ type: 'info', title, message });
    }
}

// Global instance
window.notify = new NotificationManager();

// jQuery integration
if (typeof $ !== 'undefined') {
    $.notify = function(message, type = 'info', title = '') {
        return window.notify.show({ type, title, message });
    };
}

// Replace old flash messages with toasts
$(document).ready(function() {
    $('.alert').each(function() {
        const $alert = $(this);
        const message = $alert.text().trim();
        let type = 'info';
        
        if ($alert.hasClass('alert-success')) type = 'success';
        else if ($alert.hasClass('alert-danger') || $alert.hasClass('alert-error')) type = 'error';
        else if ($alert.hasClass('alert-warning')) type = 'warning';
        
        if (message) {
            notify.show({ type, message });
            $alert.remove();
        }
    });
});

