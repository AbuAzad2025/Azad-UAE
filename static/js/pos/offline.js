(function () {
  'use strict';

  let swRegistration = null;
  let offlineStatusBar = null;

  function createOfflineBar() {
    if (document.getElementById('posOfflineBar')) return;
    const bar = document.createElement('div');
    bar.id = 'posOfflineBar';
    bar.className = 'alert alert-danger d-flex justify-content-between align-items-center py-1 mb-2 d-none';
    bar.setAttribute('role', 'alert');
    bar.innerHTML =
      '<div><i class="fas fa-wifi-slash mr-1"></i> أنت غير متصل — الفواتير سيتم حفظها محلياً وإرسالها لاحقاً</div>' +
      '<button id="retryQueueBtn" class="btn btn-sm btn-light">إعادة المحاولة</button>';
    const sessionBar = document.getElementById('posSessionBar');
    if (sessionBar && sessionBar.parentNode) {
      sessionBar.parentNode.insertBefore(bar, sessionBar.nextSibling);
    }
    offlineStatusBar = bar;
  }

  function updateOnlineStatus() {
    if (!offlineStatusBar) return;
    if (navigator.onLine) {
      offlineStatusBar.classList.add('d-none');
    } else {
      offlineStatusBar.classList.remove('d-none');
    }
  }

  function registerSW() {
    if (!('serviceWorker' in navigator)) return;
    navigator.serviceWorker.register('/static/pos-sw.js', { scope: '/pos/' }).then(function (reg) {
      swRegistration = reg;
    }).catch(function () { });
  }

  function retryQueue() {
    if (swRegistration && swRegistration.active) {
      swRegistration.active.postMessage('retry-queue');
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    createOfflineBar();
    registerSW();
    updateOnlineStatus();
    window.addEventListener('online', function () {
      updateOnlineStatus();
      retryQueue();
    });
    window.addEventListener('offline', updateOnlineStatus);
    document.addEventListener('click', function (e) {
      if (e.target && e.target.id === 'retryQueueBtn') retryQueue();
    });
  });

  // noinspection JSUnusedGlobalSymbols
  window.__posOffline = { retryQueue: retryQueue };
})();
