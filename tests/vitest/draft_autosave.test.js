import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const DAY_MS = 24 * 60 * 60 * 1000;

function formHTML() {
  return `
    <form id="f">
      <input type="text" name="title" value="">
      <input type="checkbox" name="active" value="yes">
      <input type="password" name="pw" value="">
      <input type="hidden" name="hid" value="">
      <input type="text" name="disabled_field" value="" disabled>
      <input type="text" value="" data-no-name>
      <select name="kind"><option value="a">a</option><option value="b">b</option></select>
      <textarea name="notes"></textarea>
    </form>
  `;
}

describe('draft-autosave.js', () => {
  let DraftAutosave;

  beforeEach(async () => {
    localStorage.clear();
    document.body.innerHTML = formHTML();
    vi.resetModules();
    await import('../../static/js/draft-autosave.js');
    DraftAutosave = window.DraftAutosave;
  });

  afterEach(() => {
    localStorage.clear();
    document.body.innerHTML = '';
    vi.useRealTimers();
    vi.resetModules();
  });

  it('save stores serialized field values excluding password/hidden/disabled/nameless', () => {
    const form = document.getElementById('f');
    form.querySelector('[name="title"]').value = 'hello';
    form.querySelector('[name="active"]').checked = true;
    form.querySelector('[name="notes"]').value = 'some notes';
    DraftAutosave.save('k', form);

    const payload = JSON.parse(localStorage.getItem('azad_draft_k'));
    expect(payload.data.title).toBe('hello');
    expect(payload.data.active).toBe('yes');
    expect(payload.data.notes).toBe('some notes');
    expect(payload.data.pw).toBeUndefined();
    expect(payload.data.hid).toBeUndefined();
    expect(payload.data.disabled_field).toBeUndefined();
    expect(payload.timestamp).toBeLessThanOrEqual(Date.now());
  });

  it('unchecked checkbox is omitted from the draft', () => {
    const form = document.getElementById('f');
    DraftAutosave.save('k2', form);
    expect(JSON.parse(localStorage.getItem('azad_draft_k2')).data.active).toBeUndefined();
  });

  it('load restores text/select/textarea values and checkbox state', () => {
    const form = document.getElementById('f');
    form.querySelector('[name="title"]').value = 'hello';
    form.querySelector('[name="active"]').checked = true;
    form.querySelector('[name="notes"]').value = 'some notes';
    DraftAutosave.save('r', form);
    form.querySelector('[name="title"]').value = '';
    form.querySelector('[name="active"]').checked = false;
    form.querySelector('[name="notes"]').value = '';

    expect(DraftAutosave.load('r', form)).toBe(true);
    expect(form.querySelector('[name="title"]').value).toBe('hello');
    expect(form.querySelector('[name="notes"]').value).toBe('some notes');
    expect(form.querySelector('[name="active"]').checked).toBe(true);
  });

  it('load dispatches change events for restored inputs', () => {
    const form = document.getElementById('f');
    form.querySelector('[name="title"]').value = 'changed';
    DraftAutosave.save('evt', form);
    form.querySelector('[name="title"]').value = '';

    const seen = [];
    form.addEventListener('change', (e) => seen.push(e.target.name));
    DraftAutosave.load('evt', form);
    expect(seen).toContain('title');
  });

  it('load returns false for missing drafts and never touches the form', () => {
    const form = document.getElementById('f');
    expect(DraftAutosave.load('missing', form)).toBe(false);
    expect(form.querySelector('[name="title"]').value).toBe('');
  });

  it('load returns false on corrupted JSON payloads (entry left in place)', () => {
    localStorage.setItem('azad_draft_corrupt', '{not-json');
    const form = document.getElementById('f');
    expect(DraftAutosave.load('corrupt', form)).toBe(false);
    // Documented behavior: the catch path only signals failure; only expiry clears.
    expect(localStorage.getItem('azad_draft_corrupt')).toBe('{not-json');
  });

  it('load treats drafts older than 24h as expired and clears them', () => {
    localStorage.setItem(
      'azad_draft_old',
      JSON.stringify({ data: { title: 'stale' }, timestamp: Date.now() - DAY_MS - 5000 }),
    );
    const form = document.getElementById('f');
    expect(DraftAutosave.load('old', form)).toBe(false);
    expect(localStorage.getItem('azad_draft_old')).toBeNull();
  });

  it('hasDraft distinguishes fresh vs expired vs absent drafts', () => {
    expect(DraftAutosave.hasDraft('none')).toBe(false);
    DraftAutosave.save('fresh', document.getElementById('f'));
    expect(DraftAutosave.hasDraft('fresh')).toBe(true);
    localStorage.setItem(
      'azad_draft_stale',
      JSON.stringify({ data: {}, timestamp: Date.now() - DAY_MS * 2 }),
    );
    expect(DraftAutosave.hasDraft('stale')).toBe(false);
    localStorage.setItem('azad_draft_broken', 'zzz');
    expect(DraftAutosave.hasDraft('broken')).toBe(false);
  });

  it('clear removes the stored draft', () => {
    DraftAutosave.save('c', document.getElementById('f'));
    expect(localStorage.getItem('azad_draft_c')).not.toBeNull();
    DraftAutosave.clear('c');
    expect(localStorage.getItem('azad_draft_c')).toBeNull();
  });

  it('init with no matching form is a no-op', () => {
    expect(() => DraftAutosave.init('nope', '#does-not-exist')).not.toThrow();
  });

  it('init shows a restore banner seeded from an existing draft and restores values on click', () => {
    const form = document.getElementById('f');
    form.querySelector('[name="title"]').value = 'restorable';
    DraftAutosave.save('banner', form);
    form.querySelector('[name="title"]').value = '';

    DraftAutosave.init('banner', '#f');
    const banner = form.querySelector('.alert-info');
    expect(banner).not.toBeNull();

    banner.querySelector('.js-draft-restore').click();
    expect(form.querySelector('[name="title"]').value).toBe('restorable');
    expect(form.querySelector('.js-draft-banner, .alert-info')).toBeNull();
  });

  it('init discard button deletes the stored draft', () => {
    const form = document.getElementById('f');
    form.querySelector('[name="title"]').value = 'to-discard';
    DraftAutosave.save('discard', form);

    DraftAutosave.init('discard', '#f');
    form.querySelector('.js-draft-discard').click();
    expect(localStorage.getItem('azad_draft_discard')).toBeNull();
    expect(form.querySelector('.alert-info')).toBeNull();
  });

  it('init schedules a debounced autosave on input/change events', async () => {
    vi.useFakeTimers();
    DraftAutosave.init('debounce', '#f');
    const input = document.querySelector('[name="title"]');
    input.value = 'typed';
    input.dispatchEvent(new Event('input', { bubbles: true }));

    vi.advanceTimersByTime(4900);
    expect(localStorage.getItem('azad_draft_debounce')).toBeNull();
    vi.advanceTimersByTime(200);
    expect(JSON.parse(localStorage.getItem('azad_draft_debounce')).data.title).toBe('typed');
  });

  it('init clears the draft when the form is submitted', () => {
    DraftAutosave.save('submit', document.getElementById('f'));
    DraftAutosave.init('submit', '#f');
    document.getElementById('f').dispatchEvent(new Event('submit', { bubbles: true }));
    expect(localStorage.getItem('azad_draft_submit')).toBeNull();
  });

  it('init saves pending state on beforeunload', () => {
    DraftAutosave.init('unload', '#f');
    const input = document.querySelector('[name="title"]');
    input.value = 'final';
    input.dispatchEvent(new Event('change', { bubbles: true }));
    input.value = 'final-via-unload';
    window.dispatchEvent(new Event('beforeunload'));
    expect(JSON.parse(localStorage.getItem('azad_draft_unload')).data.title).toBe('final-via-unload');
  });

  it('serializes no-op gracefully when a save hits quota errors', () => {
    const original = Storage.prototype.setItem;
    Storage.prototype.setItem = vi.fn(() => { throw new Error('quota'); });
    expect(() => DraftAutosave.save('quota', document.getElementById('f'))).not.toThrow();
    Storage.prototype.setItem = original;
  });
});
