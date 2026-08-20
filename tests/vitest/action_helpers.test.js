import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

let originalLocation;

async function loadActionHelpers() {
  await import('../../static/js/action-helpers.js');
  return window.ActionHelpers;
}

function flush() {
  return new Promise((resolve) => setTimeout(resolve, 10));
}

beforeEach(async () => {
  document.body.innerHTML = '';
  document.head.innerHTML = '';
  originalLocation = window.location;
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { ...originalLocation, reload: vi.fn() },
  });
  window.prompt = vi.fn();
  window.confirm = vi.fn();
  window.alert = vi.fn();
  window.open = vi.fn();
  global.fetch = vi.fn();
  delete window.ActionHelpers;
  vi.resetModules();
});

afterEach(() => {
  Object.defineProperty(window, 'location', { configurable: true, value: originalLocation });
  document.body.innerHTML = '';
  document.head.innerHTML = '';
  vi.restoreAllMocks();
  vi.resetModules();
  delete global.fetch;
  delete window.ActionHelpers;
});

describe('action-helpers.js', () => {
  describe('getCsrfToken', () => {
    it('reads from meta[name="csrf-token"]', async () => {
      document.head.innerHTML = '<meta name="csrf-token" content="abc123">';
      const AH = await loadActionHelpers();
      expect(AH.getCsrfToken()).toBe('abc123');
    });

    it('falls back to input[name="csrf_token"]', async () => {
      document.body.innerHTML = '<input type="hidden" name="csrf_token" value="input_tok">';
      const AH = await loadActionHelpers();
      expect(AH.getCsrfToken()).toBe('input_tok');
    });

    it('returns "" when neither exists', async () => {
      const AH = await loadActionHelpers();
      expect(AH.getCsrfToken()).toBe('');
    });

    it('prefers meta tag over hidden input when both exist', async () => {
      document.head.innerHTML = '<meta name="csrf-token" content="meta_tok">';
      document.body.innerHTML = '<input type="hidden" name="csrf_token" value="input_tok">';
      const AH = await loadActionHelpers();
      expect(AH.getCsrfToken()).toBe('meta_tok');
    });
  });

  describe('openPrintWindow', () => {
    it('opens a new tab with the given url', async () => {
      const AH = await loadActionHelpers();
      AH.openPrintWindow('/print/123');
      expect(window.open).toHaveBeenCalledWith('/print/123', '_blank');
    });

    it('does nothing when url is empty string', async () => {
      const AH = await loadActionHelpers();
      AH.openPrintWindow('');
      expect(window.open).not.toHaveBeenCalled();
    });

    it('does nothing when url is null', async () => {
      const AH = await loadActionHelpers();
      AH.openPrintWindow(null);
      expect(window.open).not.toHaveBeenCalled();
    });

    it('does nothing when url is undefined', async () => {
      const AH = await loadActionHelpers();
      AH.openPrintWindow(undefined);
      expect(window.open).not.toHaveBeenCalled();
    });
  });

  describe('archivePaymentItem', () => {
    it('does nothing when prompt returns null', async () => {
      const AH = await loadActionHelpers();
      window.prompt.mockReturnValue(null);
      AH.archivePaymentItem('receipt', 5, 'REC-1');
      expect(window.confirm).not.toHaveBeenCalled();
      expect(global.fetch).not.toHaveBeenCalled();
    });

    it('does nothing when prompt returns empty string', async () => {
      const AH = await loadActionHelpers();
      window.prompt.mockReturnValue('');
      AH.archivePaymentItem('receipt', 5, 'REC-1');
      expect(window.confirm).not.toHaveBeenCalled();
      expect(global.fetch).not.toHaveBeenCalled();
    });

    it('does nothing when confirm returns false', async () => {
      const AH = await loadActionHelpers();
      window.prompt.mockReturnValue('reason');
      window.confirm.mockReturnValue(false);
      AH.archivePaymentItem('receipt', 5, 'REC-1');
      expect(global.fetch).not.toHaveBeenCalled();
    });

    it('sends POST to receipt endpoint for receipt type', async () => {
      const AH = await loadActionHelpers();
      window.prompt.mockReturnValue('bad condition');
      window.confirm.mockReturnValue(true);
      global.fetch.mockResolvedValue({ ok: true });

      AH.archivePaymentItem('receipt', 10, 'REC-10');
      await flush();

      expect(global.fetch).toHaveBeenCalledTimes(1);
      const [url, opts] = global.fetch.mock.calls[0];
      expect(url).toBe('/payments/receipts/10/archive');
      expect(opts.method).toBe('POST');
      expect(opts.headers['Content-Type']).toContain('application/x-www-form-urlencoded');
      expect(opts.body).toContain('reason=bad');
      expect(opts.body).toContain('condition');
      expect(opts.credentials).toBe('same-origin');
    });

    it('sends POST to payment endpoint for payment type', async () => {
      const AH = await loadActionHelpers();
      window.prompt.mockReturnValue('cancelled');
      window.confirm.mockReturnValue(true);
      global.fetch.mockResolvedValue({ ok: true });

      AH.archivePaymentItem('payment', 7, 'PAY-7');
      await flush();

      const [url] = global.fetch.mock.calls[0];
      expect(url).toBe('/payments/payments/7/archive');
    });

    it('uses id in prompt/confirm when number is falsy', async () => {
      const AH = await loadActionHelpers();
      window.prompt.mockReturnValue('reason');
      window.confirm.mockReturnValue(false);
      AH.archivePaymentItem('receipt', 42, null);
      expect(window.prompt).toHaveBeenCalledWith(expect.stringContaining('#42'));
      expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('#42'));
    });

    it('reloads page on success', async () => {
      const AH = await loadActionHelpers();
      window.prompt.mockReturnValue('ok');
      window.confirm.mockReturnValue(true);
      global.fetch.mockResolvedValue({ ok: true });

      AH.archivePaymentItem('receipt', 1, 'R-1');
      await flush();

      expect(window.location.reload).toHaveBeenCalled();
    });

    it('alerts on fetch failure with non-JSON response', async () => {
      const AH = await loadActionHelpers();
      window.prompt.mockReturnValue('reason');
      window.confirm.mockReturnValue(true);
      global.fetch.mockResolvedValue({
        ok: false,
        status: 500,
        headers: { get: () => 'text/html' },
      });

      AH.archivePaymentItem('receipt', 1, 'R-1');
      await flush();
      await flush();

      expect(window.alert).toHaveBeenCalledWith('فشلت عملية الأرشفة (HTTP 500)');
    });

    it('alerts generic error when JSON body has message field', async () => {
      const AH = await loadActionHelpers();
      window.prompt.mockReturnValue('reason');
      window.confirm.mockReturnValue(true);
      global.fetch.mockResolvedValue({
        ok: false,
        status: 400,
        headers: { get: () => 'application/json' },
        json: () => Promise.resolve({ message: 'duplicate archive' }),
      });

      AH.archivePaymentItem('payment', 2, 'P-2');
      await flush();
      await flush();

      expect(window.alert).toHaveBeenCalledWith('فشلت عملية الأرشفة');
    });

    it('alerts generic error when JSON body has no message or error', async () => {
      const AH = await loadActionHelpers();
      window.prompt.mockReturnValue('reason');
      window.confirm.mockReturnValue(true);
      global.fetch.mockResolvedValue({
        ok: false,
        status: 422,
        headers: { get: () => 'application/json' },
        json: () => Promise.resolve({}),
      });

      AH.archivePaymentItem('receipt', 3, 'R-3');
      await flush();
      await flush();

      expect(window.alert).toHaveBeenCalledWith('فشلت عملية الأرشفة');
    });

    it('alerts generic error when JSON body has error field', async () => {
      const AH = await loadActionHelpers();
      window.prompt.mockReturnValue('reason');
      window.confirm.mockReturnValue(true);
      global.fetch.mockResolvedValue({
        ok: false,
        status: 403,
        headers: { get: () => 'application/json' },
        json: () => Promise.resolve({ error: 'not allowed' }),
      });

      AH.archivePaymentItem('receipt', 3, 'R-3');
      await flush();
      await flush();

      expect(window.alert).toHaveBeenCalledWith('فشلت عملية الأرشفة');
    });

    it('alerts generic error when JSON body throws during parse', async () => {
      const AH = await loadActionHelpers();
      window.prompt.mockReturnValue('reason');
      window.confirm.mockReturnValue(true);
      global.fetch.mockResolvedValue({
        ok: false,
        status: 500,
        headers: { get: () => 'application/json' },
        json: () => Promise.reject(new Error('bad json')),
      });

      AH.archivePaymentItem('payment', 9, 'P-9');
      await flush();
      await flush();

      expect(window.alert).toHaveBeenCalledWith('فشلت عملية الأرشفة');
    });

    it('alerts on network error', async () => {
      const AH = await loadActionHelpers();
      window.prompt.mockReturnValue('reason');
      window.confirm.mockReturnValue(true);
      global.fetch.mockRejectedValue(new Error('Network failure'));

      AH.archivePaymentItem('receipt', 1, 'R-1');
      await flush();
      await flush();

      expect(window.alert).toHaveBeenCalledWith('Error: Network failure');
    });

    it('normalizes non-receipt types to payment endpoint', async () => {
      const AH = await loadActionHelpers();
      window.prompt.mockReturnValue('x');
      window.confirm.mockReturnValue(true);
      global.fetch.mockResolvedValue({ ok: true });

      AH.archivePaymentItem('invoice', 11, 'INV-11');
      await flush();

      const [url] = global.fetch.mock.calls[0];
      expect(url).toBe('/payments/payments/11/archive');
    });

    it('includes X-CSRFToken header from meta tag', async () => {
      document.head.innerHTML = '<meta name="csrf-token" content="csrf_xyz">';
      const AH = await loadActionHelpers();
      window.prompt.mockReturnValue('reason');
      window.confirm.mockReturnValue(true);
      global.fetch.mockResolvedValue({ ok: true });

      AH.archivePaymentItem('receipt', 1, 'R-1');
      await flush();

      const [, opts] = global.fetch.mock.calls[0];
      expect(opts.headers['X-CSRFToken']).toBe('csrf_xyz');
    });
  });
});
