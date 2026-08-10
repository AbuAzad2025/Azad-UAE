import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

let fetchMock;
let fakeLocation;
let originalLocation;

function mountBoard(kind) {
  const cardTag = kind === 'pipeline' ? 'pipeline-card' : 'kanban-card';
  const colTag = kind === 'pipeline' ? 'pipeline-column' : 'kanban-column';
  const cardsTag = kind === 'pipeline' ? 'pipeline-cards' : 'kanban-cards';
  document.body.innerHTML = `
    <div class="${colTag}" data-stage-id="3">
      <div class="${cardsTag}">
        <div class="${cardTag}" draggable="true" data-lead-id="10" data-task-id="10">Item</div>
      </div>
    </div>
    <div class="${colTag}">
      <div class="${cardsTag}">
        <div class="${cardTag}" draggable="true" data-lead-id="20" data-task-id="20">Item 2</div>
      </div>
    </div>
  `;
}

function dragEvent(type, { getData = () => '' } = {}) {
  const ev = new Event(type, { bubbles: true, cancelable: true });
  ev.dataTransfer = { setData: vi.fn(), getData: vi.fn(getData) };
  return ev;
}

async function flush() {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

describe('crm/pipeline.js', () => {
  beforeEach(() => {
    originalLocation = window.location;
    fakeLocation = { reload: vi.fn() };
    Object.defineProperty(window, 'location', { configurable: true, value: fakeLocation });
    fetchMock = vi.fn();
    global.fetch = fetchMock;
    const meta = document.createElement('meta');
    meta.name = 'csrf-token';
    meta.content = 'csrf123';
    document.head.appendChild(meta);
    mountBoard('pipeline');
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    document.head.innerHTML = '';
    Object.defineProperty(window, 'location', { configurable: true, value: originalLocation });
    delete global.fetch;
    vi.resetModules();
  });

  it('stores the lead id and marks the card on dragstart', async () => {
    await import('../../static/js/crm/pipeline.js');
    const card = document.querySelector('.pipeline-card');
    const ev = dragEvent('dragstart');
    card.dispatchEvent(ev);
    expect(ev.dataTransfer.setData).toHaveBeenCalledWith('text/plain', '10');
    expect(card.classList.contains('dragging')).toBe(true);
  });

  it('removes the dragging class on dragend', async () => {
    await import('../../static/js/crm/pipeline.js');
    const card = document.querySelector('.pipeline-card');
    card.classList.add('dragging');
    card.dispatchEvent(dragEvent('dragend'));
    expect(card.classList.contains('dragging')).toBe(false);
  });

  it('marks the drop column on dragover and dragleave', async () => {
    await import('../../static/js/crm/pipeline.js');
    const col = document.querySelector('.pipeline-cards');
    const over = dragEvent('dragover');
    col.dispatchEvent(over);
    expect(over.defaultPrevented).toBe(true);
    expect(col.classList.contains('drag-over')).toBe(true);
    col.dispatchEvent(dragEvent('dragleave'));
    expect(col.classList.contains('drag-over')).toBe(false);
  });

  it('posts the stage move on drop and reloads on success', async () => {
    fetchMock.mockResolvedValue({ json: () => Promise.resolve({ success: true }) });
    await import('../../static/js/crm/pipeline.js');
    const col = document.querySelector('.pipeline-cards');
    col.dispatchEvent(dragEvent('drop', { getData: () => '10' }));
    await flush();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toBe('/crm/api/move-stage');
    expect(opts.method).toBe('POST');
    expect(opts.headers).toEqual({
      'Content-Type': 'application/json',
      'X-CSRFToken': 'csrf123',
    });
    expect(JSON.parse(opts.body)).toEqual({ lead_id: 10, stage_id: 3 });
    expect(fakeLocation.reload).toHaveBeenCalledTimes(1);
  });

  it('reloads on fetch failure', async () => {
    fetchMock.mockRejectedValue(new Error('network'));
    await import('../../static/js/crm/pipeline.js');
    const col = document.querySelector('.pipeline-cards');
    col.dispatchEvent(dragEvent('drop', { getData: () => '10' }));
    await flush();
    expect(fakeLocation.reload).toHaveBeenCalledTimes(1);
  });

  it('ignores drops without a lead id or stage id', async () => {
    await import('../../static/js/crm/pipeline.js');
    const col = document.querySelector('.pipeline-cards');
    col.dispatchEvent(dragEvent('drop'));
    const emptyStageCol = document.querySelectorAll('.pipeline-cards')[1];
    emptyStageCol.dispatchEvent(dragEvent('drop', { getData: () => '20' }));
    await flush();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(fakeLocation.reload).not.toHaveBeenCalled();
  });
});

describe('projects/kanban.js', () => {
  beforeEach(() => {
    originalLocation = window.location;
    fakeLocation = { reload: vi.fn() };
    Object.defineProperty(window, 'location', { configurable: true, value: fakeLocation });
    fetchMock = vi.fn();
    global.fetch = fetchMock;
    const meta = document.createElement('meta');
    meta.name = 'csrf-token';
    meta.content = 'csrf123';
    document.head.appendChild(meta);
    mountBoard('kanban');
    vi.resetModules();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    document.head.innerHTML = '';
    Object.defineProperty(window, 'location', { configurable: true, value: originalLocation });
    delete global.fetch;
    vi.resetModules();
  });

  it('stores the task id and marks the card on dragstart', async () => {
    await import('../../static/js/projects/kanban.js');
    const card = document.querySelector('.kanban-card');
    const ev = dragEvent('dragstart');
    card.dispatchEvent(ev);
    expect(ev.dataTransfer.setData).toHaveBeenCalledWith('text/plain', '10');
    expect(card.classList.contains('dragging')).toBe(true);
  });

  it('removes the dragging class on dragend', async () => {
    await import('../../static/js/projects/kanban.js');
    const card = document.querySelector('.kanban-card');
    card.classList.add('dragging');
    card.dispatchEvent(dragEvent('dragend'));
    expect(card.classList.contains('dragging')).toBe(false);
  });

  it('marks the drop column on dragover and dragleave', async () => {
    await import('../../static/js/projects/kanban.js');
    const col = document.querySelector('.kanban-cards');
    const over = dragEvent('dragover');
    col.dispatchEvent(over);
    expect(over.defaultPrevented).toBe(true);
    expect(col.classList.contains('drag-over')).toBe(true);
    col.dispatchEvent(dragEvent('dragleave'));
    expect(col.classList.contains('drag-over')).toBe(false);
  });

  it('posts the task move on drop and reloads on success', async () => {
    fetchMock.mockResolvedValue({ json: () => Promise.resolve({ success: true }) });
    await import('../../static/js/projects/kanban.js');
    const col = document.querySelector('.kanban-cards');
    col.dispatchEvent(dragEvent('drop', { getData: () => '10' }));
    await flush();
    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toBe('/projects/api/move-task');
    expect(opts.method).toBe('POST');
    expect(opts.headers['X-CSRFToken']).toBe('csrf123');
    expect(JSON.parse(opts.body)).toEqual({ task_id: 10, stage_id: 3 });
    expect(fakeLocation.reload).toHaveBeenCalledTimes(1);
  });

  it('reloads on fetch failure', async () => {
    fetchMock.mockRejectedValue(new Error('network'));
    await import('../../static/js/projects/kanban.js');
    const col = document.querySelector('.kanban-cards');
    col.dispatchEvent(dragEvent('drop', { getData: () => '10' }));
    await flush();
    expect(fakeLocation.reload).toHaveBeenCalledTimes(1);
  });

  it('ignores drops without a task id or stage id', async () => {
    await import('../../static/js/projects/kanban.js');
    const col = document.querySelector('.kanban-cards');
    col.dispatchEvent(dragEvent('drop'));
    const emptyStageCol = document.querySelectorAll('.kanban-cards')[1];
    emptyStageCol.dispatchEvent(dragEvent('drop', { getData: () => '20' }));
    await flush();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(fakeLocation.reload).not.toHaveBeenCalled();
  });
});
