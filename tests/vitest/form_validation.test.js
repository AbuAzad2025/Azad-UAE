import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('form_validation.js', () => {
  let container;

  beforeEach(() => {
    document.body.innerHTML = `
      <form class="needs-validation">
        <input name="email" type="email" required minlength="5" maxlength="50" />
        <input name="phone" type="tel" required />
        <input name="password" type="password" required minlength="8" />
        <input name="confirm" type="password" data-equal-to="input[name='password']" />
        <select name="status" required><option value="">Choose</option><option value="active">Active</option></select>
      </form>
    `;
    container = document.querySelector('form');
  });

  afterEach(() => {
    document.body.innerHTML = '';
    vi.resetModules();
  });

  async function loadAndInit() {
    await import('../../static/js/form_validation.js');
    window.FormValidation.init();
  }

  it('validates required email field', async () => {
    await loadAndInit();
    const email = container.querySelector('input[name="email"]');
    email.value = '';
    email.dispatchEvent(new Event('blur'));
    expect(email.classList.contains('is-invalid')).toBe(true);

    email.value = 'valid@test.com';
    email.dispatchEvent(new Event('blur'));
    expect(email.classList.contains('is-invalid')).toBe(false);
  });

  it('validates email format', async () => {
    await loadAndInit();
    const email = container.querySelector('input[name="email"]');
    email.value = 'invalid-email';
    email.dispatchEvent(new Event('blur'));
    expect(email.classList.contains('is-invalid')).toBe(true);

    email.value = 'valid@test.com';
    email.dispatchEvent(new Event('blur'));
    expect(email.classList.contains('is-invalid')).toBe(false);
  });

  it('validates phone pattern', async () => {
    await loadAndInit();
    const phone = container.querySelector('input[name="phone"]');
    phone.value = 'abc';
    phone.dispatchEvent(new Event('blur'));
    expect(phone.classList.contains('is-invalid')).toBe(true);

    phone.value = '+971 50 123 4567';
    phone.dispatchEvent(new Event('blur'));
    expect(phone.classList.contains('is-invalid')).toBe(false);
  });

  it('validates min length', async () => {
    await loadAndInit();
    const pwd = container.querySelector('input[name="password"]');
    pwd.value = '123';
    pwd.dispatchEvent(new Event('blur'));
    expect(pwd.classList.contains('is-invalid')).toBe(true);

    pwd.value = '12345678';
    pwd.dispatchEvent(new Event('blur'));
    expect(pwd.classList.contains('is-invalid')).toBe(false);
  });

  it('validates equalTo (password confirmation)', async () => {
    await loadAndInit();
    const pwd = container.querySelector('input[name="password"]');
    const confirm = container.querySelector('input[name="confirm"]');
    pwd.value = '12345678';
    confirm.value = 'different';
    confirm.dispatchEvent(new Event('blur'));
    expect(confirm.classList.contains('is-invalid')).toBe(true);

    confirm.value = '12345678';
    confirm.dispatchEvent(new Event('blur'));
    expect(confirm.classList.contains('is-invalid')).toBe(false);
  });

  it('prevents form submit when invalid', async () => {
    await loadAndInit();
    container.querySelector('input[name="email"]').value = '';
    const submitEvent = new Event('submit', { cancelable: true });
    container.dispatchEvent(submitEvent);
    expect(submitEvent.defaultPrevented).toBe(true);
  });

  it('allows form submit when valid', async () => {
    await loadAndInit();
    container.querySelector('input[name="email"]').value = 'test@test.com';
    container.querySelector('input[name="phone"]').value = '+971501234567';
    container.querySelector('input[name="password"]').value = '12345678';
    container.querySelector('input[name="confirm"]').value = '12345678';
    container.querySelector('select[name="status"]').value = 'active';
    const submitEvent = new Event('submit', { cancelable: true });
    container.dispatchEvent(submitEvent);
    expect(submitEvent.defaultPrevented).toBe(false);
  });

  it('validateField and validateForm are exposed', async () => {
    await loadAndInit();
    expect(typeof window.FormValidation.validateField).toBe('function');
    expect(typeof window.FormValidation.validateForm).toBe('function');
    expect(window.FormValidation.MSG).toBeDefined();
  });
});
