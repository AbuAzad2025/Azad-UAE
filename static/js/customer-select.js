(function($) {
  'use strict';
  // =====================================
  // UNIVERSAL SMART SEARCH SYSTEM
  // =====================================
  
  const SmartSearch = {
  
  // =====================================
    // CUSTOMER SEARCH
  // =====================================
    initCustomerSearch: function() {      
      $('.customer-select').each(function(index) {
        const $select = $(this);        
    if ($select.hasClass('select2-hidden-accessible')) {      $select.select2('destroy');
    }
    
        $select.select2({
      ajax: {
            url: '/customers/api/search',
        dataType: 'json',
            delay: 300,
        data: function(params) {          return {
            q: params.term || '',
            page: params.page || 1
          };
        },
        processResults: function(data) {              const items = Array.isArray(data) ? data : (data.results || []);
              const results = {
                results: items.map(item => ({
                  id: item.id,
                  text: item.text || `${item.name}${item.phone ? ' - ' + item.phone : ''}`,
                  name: item.name,
                  phone: item.phone || '',
                  balance: item.balance || 0
                })),
                pagination: { more: false }
              };              return results;
        },
        cache: true
      },
          placeholder: 'ابحث عن زبون...',
      allowClear: true,
      minimumInputLength: 0,
      dir: 'rtl',
      width: '100%',
          templateResult: SmartSearch.formatCustomerResult,
          templateSelection: SmartSearch.formatCustomerSelection,
          escapeMarkup: function(markup) { return markup; }
        });      });
    },
    
    // =====================================
    // SUPPLIER SEARCH
    // =====================================
    initSupplierSearch: function() {      
      $('.supplier-select').each(function(index) {
        const $select = $(this);        
        if ($select.hasClass('select2-hidden-accessible')) {          $select.select2('destroy');
        }
        
        $select.select2({
          ajax: {
            url: '/suppliers/api/search',
            dataType: 'json',
            delay: 300,
            data: function(params) {              return {
                q: params.term || '',
                page: params.page || 1
              };
            },
            processResults: function(data) {              const items = Array.isArray(data) ? data : (data.results || []);
              const results = {
                results: items.map(item => ({
                  id: item.id,
                  text: item.text || `${item.name}${item.phone ? ' - ' + item.phone : ''}`,
                  name: item.name,
                  phone: item.phone || '',
                  balance: item.balance || 0
                })),
                pagination: { more: false }
              };              return results;
            },
            cache: true
          },
          placeholder: 'ابحث عن مورد...',
          allowClear: true,
          minimumInputLength: 0,
          dir: 'rtl',
          width: '100%',
          templateResult: SmartSearch.formatSupplierResult,
          templateSelection: SmartSearch.formatSupplierSelection,
          escapeMarkup: function(markup) { return markup; }
        });      });
    },
  
  // =====================================
    // PRODUCT SEARCH
  // =====================================
    initProductSearch: function() {      
      $('.product-select').each(function(index) {
        const $select = $(this);    
    if ($select.hasClass('select2-hidden-accessible')) {      $select.select2('destroy');
    }
    
        $select.select2({
      ajax: {
            url: '/products/api/search',
        dataType: 'json',
            delay: 300,
        data: function(params) {          return {
            q: params.term || '',
            page: params.page || 1
          };
        },
        processResults: function(data) {              const items = Array.isArray(data) ? data : (data.results || []);
              const results = {
                results: items.map(item => ({
                  id: item.id,
                  text: item.text || `${item.name} (${item.code || ''})`,
                  name: item.name,
                  code: item.code || '',
                  price: item.price || 0,
                  stock: item.stock || 0
                })),
                pagination: { more: false }
              };              return results;
        },
        cache: true
      },
      placeholder: 'ابحث عن منتج...',
      allowClear: true,
      minimumInputLength: 0,
      dir: 'rtl',
      width: '100%',
          templateResult: SmartSearch.formatProductResult,
          templateSelection: SmartSearch.formatProductSelection,
          escapeMarkup: function(markup) { return markup; }
        });      });
    },
    
    // =====================================
    // FORMATTING FUNCTIONS
    // =====================================
    formatCustomerResult: function(item) {
      if (item.loading) return 'جاري البحث...';
      if (!item.id) return item.text;
      
      const balance = parseFloat(item.balance || 0);
      const balanceText = balance !== 0 ? ` (${balance > 0 ? '+' : ''}${balance.toFixed(2)} AED)` : '';
      
      return $(`
        <div class="d-flex justify-content-between align-items-center">
          <div>
            <i class="fas fa-user me-2"></i>
            <strong>${item.name}</strong>
            ${item.phone ? `<br><small class="text-muted">${item.phone}</small>` : ''}
          </div>
          <div class="text-end">
            <small class="text-muted">${balanceText}</small>
          </div>
        </div>
      `);
    },
    
    formatCustomerSelection: function(item) {
      if (!item.id) return item.text;
      return item.name + (item.phone ? ' - ' + item.phone : '');
    },
    
    formatSupplierResult: function(item) {
      if (item.loading) return 'جاري البحث...';
      if (!item.id) return item.text;
      
      const balance = parseFloat(item.balance || 0);
      const balanceText = balance !== 0 ? ` (${balance > 0 ? '+' : ''}${balance.toFixed(2)} AED)` : '';
      
      return $(`
        <div class="d-flex justify-content-between align-items-center">
          <div>
            <i class="fas fa-truck me-2"></i>
            <strong>${item.name}</strong>
            ${item.phone ? `<br><small class="text-muted">${item.phone}</small>` : ''}
          </div>
          <div class="text-end">
            <small class="text-muted">${balanceText}</small>
        </div>
      </div>
      `);
    },
    
    formatSupplierSelection: function(item) {
      if (!item.id) return item.text;
      return item.name + (item.phone ? ' - ' + item.phone : '');
    },
    
    formatProductResult: function(item) {
      if (item.loading) return 'جاري البحث...';
      if (!item.id) return item.text;
      
      const stock = parseFloat(item.stock || 0);
      const stockText = stock > 0 ? `${stock} متوفر` : 'غير متوفر';
      const stockClass = stock > 0 ? 'text-success' : 'text-danger';
      
      return $(`
        <div class="d-flex justify-content-between align-items-center">
          <div>
            <i class="fas fa-box me-2"></i>
            <strong>${item.name}</strong>
            ${item.code ? `<br><small class="text-muted">${item.code}</small>` : ''}
          </div>
          <div class="text-end">
            <small class="${stockClass}">${stockText}</small>
            <br><small class="text-muted">${parseFloat(item.price || 0).toFixed(2)} AED</small>
          </div>
        </div>
      `);
    },
    
    formatProductSelection: function(item) {
      if (!item.id) return item.text;
      return item.name + (item.code ? ' (' + item.code + ')' : '');
    },
  
  // =====================================
    // INITIALIZATION
  // =====================================
    init: function() {      
      // تهيئة جميع أنواع البحث
      this.initCustomerSearch();
      this.initSupplierSearch();
      this.initProductSearch();    }
  };
  
  // =====================================
  // AUTO-INITIALIZATION
  // =====================================
  
  $(document).ready(function() {    
    // تأخير بسيط للتأكد من تحميل جميع الملفات
    setTimeout(function() {
      SmartSearch.init();
    }, 100);
  });
  
  // تهيئة فورية عند تحميل الصفحة
  $(window).on('load', function() {    SmartSearch.init();
  });
  
  // =====================================
  // GLOBAL EXPORTS
  // =====================================
  
  window.SmartSearch = SmartSearch;
  window.initCustomerSelect = SmartSearch.initCustomerSearch;
  window.initSupplierSelect = SmartSearch.initSupplierSearch;
  window.initProductSelect = SmartSearch.initProductSearch;  
})(jQuery);
