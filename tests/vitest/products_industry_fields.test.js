import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

let fetchMock;

function setReadyState(state) {
  Object.defineProperty(document, 'readyState', { configurable: true, value: state });
}

function restoreReadyState() {
  delete document.readyState;
}

function mount({ value = '', includeContainer = true, options = ['', 'general', 'food', 'cloth'] } = {}) {
  const opts = options.map((o) => `<option value="${o}">${o || 'اختر'}</option>`).join('');
  document.body.innerHTML =
    `<select id="product_industry">${opts}</select>` +
    (includeContainer ? '<div id="industryFieldsContainer"></div>' : '');
  if (value) document.querySelector('#product_industry').value = value;
}

function response(data) {
  return { json: () => Promise.resolve(data) };
}

async function flush() {
  await new Promise((r) => setTimeout(r, 0));
}

describe('products/industry-fields.js', () => {
  beforeEach(() => {
    setReadyState('complete');
    document.documentElement.removeAttribute('dir');
    fetchMock = vi.fn();
    global.fetch = fetchMock;
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    delete global.fetch;
    restoreReadyState();
    vi.resetModules();
  });

  it('does nothing when the industry select is missing', async () => {
    document.body.innerHTML = '';
    await import('../../static/js/products/industry-fields.js');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('returns early when the fields container is missing', async () => {
    mount({ includeContainer: false });
    await import('../../static/js/products/industry-fields.js');
    expect(() =>
      document.querySelector('#product_industry').dispatchEvent(new Event('change'))
    ).not.toThrow();
  });

  it('does not auto-load the general industry on init', async () => {
    mount({ value: 'general' });
    await import('../../static/js/products/industry-fields.js');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('auto-loads a preselected non-general industry on init', async () => {
    mount({ value: 'food' });
    fetchMock.mockResolvedValue(response({ fields: [] }));
    await import('../../static/js/products/industry-fields.js');
    expect(fetchMock).toHaveBeenCalledWith('/api/industry-fields?industry=food', {
      headers: { Accept: 'application/json' },
    });
  });

  it('reloads fields on select change and shows a spinner', async () => {
    mount({ value: '' });
    fetchMock.mockResolvedValue(response({ fields: [] }));
    await import('../../static/js/products/industry-fields.js');
    const select = document.querySelector('#product_industry');
    select.value = 'cloth';
    select.dispatchEvent(new Event('change'));
    expect(fetchMock).toHaveBeenCalledWith('/api/industry-fields?industry=cloth', expect.any(Object));
    expect(document.querySelector('#industryFieldsContainer').innerHTML).toContain('جاري التحميل');
  });

  it('clears the container when no fields come back', async () => {
    mount({ value: 'food' });
    fetchMock.mockResolvedValue(response({ fields: [] }));
    await import('../../static/js/products/industry-fields.js');
    await flush();
    expect(document.querySelector('#industryFieldsContainer').innerHTML).toBe('');
  });

  it('renders all field types with required flags', async () => {
    mount({ value: 'food' });
    fetchMock.mockResolvedValue(
      response({
        industry: 'أغذية',
        fields: [
          { field_code: 'brand', field_name_en: 'Brand', field_name_ar: 'العلامة', field_type: 'text', is_required: 1 },
          { field_code: 'notes', field_name_en: 'Notes', field_name_ar: 'ملاحظات', field_type: 'textarea', is_required: 0 },
          { field_code: 'size', field_name_en: 'Size', field_name_ar: 'الحجم', field_type: 'select', field_options: 'S, M, L', is_required: 0 },
          { field_code: 'weight', field_name_en: 'Weight', field_name_ar: 'الوزن', field_type: 'number', is_required: 1 },
          { field_code: 'expiry', field_name_en: 'Expiry', field_name_ar: 'الانتهاء', field_type: 'date', is_required: 0 },
        ],
      })
    );
    await import('../../static/js/products/industry-fields.js');
    await flush();
    const html = document.querySelector('#industryFieldsContainer').innerHTML;
    expect(html).toContain('Brand');
    expect(html).toContain('name="extra_brand"');
    expect(html).toContain('required');
    expect(html).toContain('name="extra_notes"');
    expect(html).toContain('<textarea');
    expect(html).toContain('name="extra_size"');
    expect(html).toContain('<option value="S">S</option>');
    expect(html).toContain('name="extra_weight"');
    expect(html).toContain('type="number"');
    expect(html).toContain('name="extra_expiry"');
    expect(html).toContain('type="date"');
  });

  it('prefers Arabic names when the document is RTL', async () => {
    document.documentElement.dir = 'rtl';
    mount({ value: 'food' });
    fetchMock.mockResolvedValue(
      response({
        industry: 'أغذية',
        fields: [{ field_code: 'brand', field_name_en: 'Brand', field_name_ar: 'العلامة', field_type: 'text', is_required: 0 }],
      })
    );
    await import('../../static/js/products/industry-fields.js');
    await flush();
    const html = document.querySelector('#industryFieldsContainer').innerHTML;
    expect(html).toContain('العلامة');
    expect(html).not.toContain('Brand');
  });

  it('escapes HTML in field labels and options', async () => {
    mount({ value: 'food' });
    fetchMock.mockResolvedValue(
      response({
        industry: 'أغذية',
        fields: [
          { field_code: 'x<y', field_name_en: 'A&B "q"', field_name_ar: '', field_type: 'select', field_options: '<b>hi</b>, plain', is_required: 0 },
        ],
      })
    );
    await import('../../static/js/products/industry-fields.js');
    await flush();
    const container = document.querySelector('#industryFieldsContainer');
    expect(container.querySelector('b')).toBeNull();
    expect(container.querySelector('label').textContent).toContain('A&B "q"');
    const select = container.querySelector('select');
    expect(select.getAttribute('name')).toBe('extra_x<y');
    const opts = Array.from(select.options).map((o) => o.text);
    expect(opts).toEqual(['-- اختر --', '<b>hi</b>', 'plain']);
  });

  it('clears the container when the request fails', async () => {
    mount({ value: 'food' });
    fetchMock.mockRejectedValue(new Error('network'));
    await import('../../static/js/products/industry-fields.js');
    await flush();
    expect(document.querySelector('#industryFieldsContainer').innerHTML).toBe('');
  });

  it('defers initialisation until DOMContentLoaded while loading', async () => {
    setReadyState('loading');
    mount({ value: 'food' });
    fetchMock.mockResolvedValue(response({ fields: [] }));
    await import('../../static/js/products/industry-fields.js');
    expect(fetchMock).not.toHaveBeenCalled();
    document.dispatchEvent(new Event('DOMContentLoaded'));
    expect(fetchMock).toHaveBeenCalled();
  });
});
