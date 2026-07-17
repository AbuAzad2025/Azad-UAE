(function () {
  'use strict';

  const input = document.querySelector('input[name="q"][data-search-autocomplete]');
  if (!input) return;

  const form = input.closest('form');
  const resultsWrap = document.querySelector('.ps-autocomplete-results');
  if (!resultsWrap) return;

  const slug = document.body.getAttribute('data-store-slug');
  if (!slug) return;

  let timer = null;
  let activeIndex = -1;

  function closeDropdown() {
    resultsWrap.style.display = 'none';
    resultsWrap.innerHTML = '';
    activeIndex = -1;
  }

  function renderResults(data) {
    resultsWrap.innerHTML = '';
    activeIndex = -1;
    if (!data.results || data.results.length === 0) {
      resultsWrap.style.display = 'none';
      return;
    }
    const list = document.createElement('div');
    list.setAttribute('role', 'listbox');
    data.results.forEach(function (item, i) {
      const a = document.createElement('a');
      a.href = item.url;
      a.setAttribute('role', 'option');
      a.setAttribute('data-index', i);
      a.className = 'ps-autocomplete-item';
      let html = '';
      if (item.image) {
        html += '<span class="ps-ac-img"><img src="' + item.image + '" alt="" loading="lazy"></span>';
      }
      html += '<span class="ps-ac-info"><span class="ps-ac-name">' + escapeHtml(item.name) + '</span><span class="ps-ac-price">' + item.price.toFixed(2) + '</span></span>';
      a.innerHTML = html;
      a.addEventListener('click', function (e) {
        e.preventDefault();
        window.location.href = item.url;
      });
      list.appendChild(a);
    });
    resultsWrap.appendChild(list);
    resultsWrap.style.display = 'block';
  }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }

  function doSearch(query) {
    if (query.length < 2) {
      closeDropdown();
      return;
    }
    const url = '/s/' + encodeURIComponent(slug) + '/api/search?q=' + encodeURIComponent(query);
    fetch(url)
      .then(function (r) { return r.json(); })
      .then(function (data) { renderResults(data); })
      .catch(function () { closeDropdown(); });
  }

  input.addEventListener('input', function () {
    const val = input.value.trim();
    clearTimeout(timer);
    timer = setTimeout(function () { doSearch(val); }, 300);
  });

  input.addEventListener('keydown', function (e) {
    const items = resultsWrap.querySelectorAll('.ps-autocomplete-item');
    if (e.key === 'Escape') {
      closeDropdown();
      input.blur();
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      activeIndex = Math.min(activeIndex + 1, items.length - 1);
      setActive(items);
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      activeIndex = Math.max(activeIndex - 1, 0);
      setActive(items);
      return;
    }
    if (e.key === 'Enter' && activeIndex >= 0 && items[activeIndex]) {
      e.preventDefault();
      window.location.href = items[activeIndex].href;
    }
  });

  function setActive(items) {
    items.forEach(function (el, i) {
      if (i === activeIndex) {
        el.classList.add('ps-ac-active');
        el.setAttribute('aria-selected', 'true');
      } else {
        el.classList.remove('ps-ac-active');
        el.setAttribute('aria-selected', 'false');
      }
    });
  }

  document.addEventListener('click', function (e) {
    if (!form.contains(e.target)) {
      closeDropdown();
    }
  });
})();
