let deferredPrompt;

window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
    
    showInstallPromotion();
});

function showInstallPromotion() {
    const promptDiv = document.createElement('div');
    promptDiv.className = 'pwa-install-prompt show';
    promptDiv.innerHTML = `
        <h5 style="margin-bottom: 10px;">📱 ثبّت التطبيق</h5>
        <p style="margin-bottom: 15px; font-size: 14px;">
            ثبّت UAE-Sale على جهازك للوصول الأسرع
        </p>
        <button class="btn btn-primary btn-sm" id="install-btn">تثبيت</button>
        <button class="btn btn-secondary btn-sm mr-2" id="dismiss-install">لاحقاً</button>
    `;
    
    document.body.appendChild(promptDiv);
    
    document.getElementById('install-btn').addEventListener('click', async () => {
        promptDiv.remove();
        
        if (deferredPrompt) {
            deferredPrompt.prompt();
            const { outcome } = await deferredPrompt.userChoice;
            
            if (outcome === 'accepted') {            }
            
            deferredPrompt = null;
        }
    });
    
    document.getElementById('dismiss-install').addEventListener('click', () => {
        promptDiv.remove();
        localStorage.setItem('pwa-install-dismissed', Date.now());
    });
    
    const dismissed = localStorage.getItem('pwa-install-dismissed');
    if (dismissed && (Date.now() - dismissed < 7 * 24 * 60 * 60 * 1000)) {
        promptDiv.remove();
    }
}

window.addEventListener('appinstalled', () => {    deferredPrompt = null;
});

