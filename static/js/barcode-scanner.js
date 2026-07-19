class BarcodeScanner {
    constructor(options = {}) {
        this.onScan = options.onScan || function() {};
        this.buffer = '';
        this.timeout = null;
        this.scanDelay = options.scanDelay || 100;
        this.minLength = options.minLength || 3;
        this.active = false;
        this._boundHandleKeyPress = this.handleKeyPress.bind(this);
    }
    
    start() {
        this.active = true;
        document.addEventListener('keypress', this._boundHandleKeyPress);
    }
    
    stop() {
        this.active = false;
        document.removeEventListener('keypress', this._boundHandleKeyPress);
    }
    
    handleKeyPress(e) {
        if (!this.active) return;
        
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
            if (!e.target.classList.contains('barcode-input')) {
                return;
            }
        }
        
        if (e.key === 'Enter') {
            if (this.buffer.length >= this.minLength) {
                this.onScan(this.buffer);
            }
            this.buffer = '';
            clearTimeout(this.timeout);
            return;
        }
        
        this.buffer += e.key;
        
        clearTimeout(this.timeout);
        this.timeout = setTimeout(() => {
            this.buffer = '';
        }, this.scanDelay);
    }
}

class CameraBarcodeScanner {
    constructor(videoElement, options = {}) {
        this.video = videoElement;
        this.canvas = document.createElement('canvas');
        this.onScan = options.onScan || function() {};
        this.isScanning = false;
        this.stream = null;
    }
    
    async start() {
        try {
            this.stream = await navigator.mediaDevices.getUserMedia({
                video: { facingMode: 'environment' }
            });
            this.video.srcObject = this.stream;
            this.video.play();
            this.isScanning = true;
            this.scan();
        } catch (error) {            alert('لا يمكن الوصول إلى الكاميرا');
        }
    }
    
    stop() {
        this.isScanning = false;
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
        }
        this.video.srcObject = null;
    }
    
    scan() {
        if (!this.isScanning) return;
        
        if (this.video.readyState === this.video.HAVE_ENOUGH_DATA) {
            this.canvas.width = this.video.videoWidth;
            this.canvas.height = this.video.videoHeight;
            const ctx = this.canvas.getContext('2d');
            ctx.drawImage(this.video, 0, 0, this.canvas.width, this.canvas.height);
            
            const imageData = ctx.getImageData(0, 0, this.canvas.width, this.canvas.height);
            const code = this.detectBarcode(imageData);
            
            if (code) {
                this.onScan(code);
                this.stop();
                return;
            }
        }
        
        requestAnimationFrame(() => this.scan());
    }
    
    detectBarcode() {
        return null;
    }
}

window.BarcodeScanner = BarcodeScanner;
window.CameraBarcodeScanner = CameraBarcodeScanner;

