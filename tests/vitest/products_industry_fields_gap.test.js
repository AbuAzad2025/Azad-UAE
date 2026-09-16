import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

function mount(value) {
  document.body.innerHTML =
    `<select id="product_industry"><option value=""></option><option value="food">food</option></select>` +
    '<div id="industryFieldsContainer"></div>';
  if (value) document.querySelector('#product_industry').value = value;
}

async function flush() {
  await new Promise((r) => setTimeout(r, 0));
}

describe('products/industry-fields gap branches', () => {
  beforeEach(() => {
    Object.defineProperty(document, 'readyState', { configurable: true, value: 'complete' });
    document.documentElement.removeAttribute('dir');
    global.fetch = vi.fn();
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    delete global.fetch;
    delete document.readyState;
    vi.resetModules();
  });

  it('falls back to field_code when names are empty', async () => {
    mount('food');
    global.fetch.mockResolvedValue({
      json: () =>
        Promise.resolve({
          industry: 'food',
          fields: [
            {
              field_code: 'mycode',
              field_name_en: '',
              field_name_ar: '',
              field_type: 'text',
              is_required: 0,
            },
          ],
        }),
    });
    await import('../../static/js/products/industry-fields.js');
    await flush();
    const label = document.querySelector('#industryFieldsContainer label');
    expect(label.textContent).toContain('mycode');
  });

  it('renders null codes and names without throwing', async () => {
    mount('food');
    global.fetch.mockResolvedValue({
      json: () =>
        Promise.resolve({
          industry: 'food',
          fields: [
            {
              field_code: null,
              field_name_en: null,
              field_name_ar: null,
              field_type: 'text',
              is_required: 0,
            },
          ],
        }),
    });
    await import('../../static/js/products/industry-fields.js');
    await flush();
    expect(document.querySelector('#industryFieldsContainer').innerHTML).toContain('extra_');
  });
});
