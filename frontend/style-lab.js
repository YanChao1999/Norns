const STORAGE_KEY = 'norns-ux-style';

const STYLES = {
  'fate-loom': {
    name: 'Fate Loom',
    tagline: 'Norse editorial. Stages as threads of fate. Ceremonial gate.'
  },
  'linear-operator': {
    name: 'Linear Operator',
    tagline: 'Calm SaaS workbench. Dense, light, keyboard-first.'
  },
  'control-room': {
    name: 'Control Room',
    tagline: 'Dark agent ops. Handoff-first. Sticky “your turn”.',
    recommended: true
  },
  'review-bench': {
    name: 'Review Bench',
    tagline: 'Split HITL. Kanban is the map. Inspector never leaves.'
  }
};

const ORDER = ['fate-loom', 'linear-operator', 'control-room', 'review-bench'];

const STAGES = [
  { id: 'urd', name: 'Urd', subtitle: 'intake', approval: true },
  { id: 'verdandi', name: 'Verdandi', subtitle: 'work', approval: true },
  { id: 'skuld', name: 'Skuld', subtitle: 'ship', approval: false }
];

const CARDS = [
  {
    id: 'norn-12',
    title: 'Draft RFC for session auth',
    stage: 'urd',
    status: 'idle',
    external: 'NORN-12',
    preview: 'Write the intake brief. No agent has run yet.'
  },
  {
    id: 'norn-08',
    title: 'Auth session handoff',
    stage: 'verdandi',
    status: 'running',
    external: 'NORN-08',
    preview: 'Verdandi agent is producing the next-stage handoff.'
  },
  {
    id: 'norn-09',
    title: 'Polarion sync',
    stage: 'verdandi',
    status: 'blocked',
    external: 'NORN-09',
    preview: 'Tool allowlist is empty. Polarion was not granted.'
  },
  {
    id: 'norn-04',
    title: 'Release notes',
    stage: 'skuld',
    status: 'waiting_approval',
    external: 'NORN-04',
    preview: 'Skuld drafted ship notes. Waiting on a human gate.'
  },
  {
    id: 'norn-01',
    title: 'Docs preview',
    stage: 'skuld',
    status: 'done',
    external: 'NORN-01',
    preview: 'Handoff accepted. Stage complete.'
  }
];

const STATUS_LABEL = {
  idle: 'idle',
  running: 'running',
  waiting_approval: 'waiting',
  blocked: 'blocked',
  done: 'done'
};

const state = {
  view: 'compare',
  picked: localStorage.getItem(STORAGE_KEY),
  openCardId: 'norn-04'
};

if (!ORDER.includes(state.picked)) {
  state.picked = null;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

function columnTitle(styleId, stage) {
  if (styleId === 'fate-loom') return stage.name;
  if (styleId === 'control-room') return `${stage.name} / ${stage.subtitle}`;
  if (styleId === 'linear-operator') return `${stage.name} · ${stage.subtitle}`;
  return stage.name;
}

function columnMeta(styleId, stage) {
  if (styleId === 'fate-loom') return stage.approval ? 'Gate required' : 'Thread may advance';
  if (styleId === 'control-room') return stage.approval ? 'HUMAN GATE' : 'AUTO-ADVANCE';
  if (styleId === 'linear-operator') return stage.approval ? 'Approval' : 'Auto';
  return stage.approval ? 'Needs review' : 'Auto-advance';
}

function approveLabel(styleId) {
  if (styleId === 'fate-loom') return 'Advance the thread';
  if (styleId === 'control-room') return 'Approve · next stage';
  if (styleId === 'review-bench') return 'Approve and advance';
  return 'Approve';
}

function pick(id) {
  state.picked = id;
  localStorage.setItem(STORAGE_KEY, id);
  render();
}

function setView(view) {
  state.view = view;
  if (view !== 'compare' && !state.openCardId) {
    state.openCardId = 'norn-04';
  }
  render();
}

function openCard(id) {
  state.openCardId = id;
  render();
}

function renderTabs() {
  const tabs = [
    `<button type="button" data-view="compare" class="${state.view === 'compare' ? 'is-active' : ''}">Compare all</button>`,
    ...ORDER.map((id) => {
      const rec = STYLES[id].recommended ? ' · rec' : '';
      const active = state.view === id ? 'is-active' : '';
      return `<button type="button" data-view="${id}" class="${active}">${escapeHtml(STYLES[id].name)}${rec}</button>`;
    })
  ];
  document.getElementById('tabs').innerHTML = tabs.join('');
}

function renderPicked() {
  const el = document.getElementById('picked');
  if (!state.picked) {
    el.className = 'lab-picked is-empty';
    el.innerHTML = 'Nothing selected yet. Open a style and press Select.';
    return;
  }
  el.className = 'lab-picked';
  const previewing =
    state.view !== 'compare' && state.view !== state.picked
      ? ` — you are previewing ${escapeHtml(STYLES[state.view].name)}`
      : '';
  el.innerHTML = `Selected: <strong>${escapeHtml(STYLES[state.picked].name)}</strong>${previewing}`;
}

function inspectorHtml(styleId, card) {
  if (!card) return '';
  const waiting = card.status === 'waiting_approval';
  const canRun = card.status === 'idle' || card.status === 'blocked';
  const docked = styleId === 'review-bench';
  const actions = [
    canRun ? '<button type="button">Run this stage</button>' : '',
    waiting
      ? `<button type="button" class="is-primary">${escapeHtml(approveLabel(styleId))}</button><button type="button">Reject</button>`
      : '',
    !canRun && !waiting ? '<span class="mock-idle-action">No gate action</span>' : ''
  ].join('');

  return `
    <aside class="mock-inspector${docked ? ' is-docked' : ''}">
      <header class="mock-inspector-head">
        <div>
          <p class="mock-kicker">${escapeHtml(card.external)}</p>
          <h3>${escapeHtml(card.title)}</h3>
        </div>
        ${docked ? '' : '<button type="button" class="mock-close" data-close-inspector>Close</button>'}
      </header>
      <p class="status status-${card.status}">${STATUS_LABEL[card.status]}</p>
      <section>
        <h4>Handoff</h4>
        <p class="mock-handoff">
          Session cookies are HttpOnly and expire in 8 hours. Next stage should
          write the login screen and wire <code>POST /api/auth/login</code>. Do
          not share agent memory — this paragraph is the only context.
        </p>
      </section>
      <section>
        <h4>Run log</h4>
        <pre class="mock-log">stage: ${escapeHtml(card.stage)}
model: gpt-4o
status: ${escapeHtml(card.status)}
${escapeHtml(card.preview)}</pre>
      </section>
      <footer class="mock-actions">${actions}</footer>
    </aside>
  `;
}

function boardHtml(styleId, compact) {
  const split = styleId === 'review-bench';
  const openCard = compact ? null : CARDS.find((card) => card.id === state.openCardId) ?? null;
  const waitingCount = CARDS.filter((card) => card.status === 'waiting_approval').length;
  const queue = CARDS.filter((card) => card.status === 'waiting_approval' || card.status === 'blocked');

  const queueHtml =
    split && !compact
      ? `<aside class="mock-queue">
          <p class="mock-queue-label">Review queue</p>
          ${queue
            .map(
              (card) => `
            <button type="button" class="mock-queue-item${state.openCardId === card.id ? ' is-active' : ''}" data-open-card="${card.id}">
              <span>${escapeHtml(card.title)}</span>
              <span class="status status-${card.status}">${STATUS_LABEL[card.status]}</span>
            </button>`
            )
            .join('')}
        </aside>`
      : '';

  const columns = STAGES.map((stage) => {
    const cards = CARDS.filter((card) => card.stage === stage.id);
    const add = stage.id === 'urd' ? `<div class="mock-add">${compact ? '+ Add card' : 'Add card to Urd'}</div>` : '';
    const tag = compact ? 'div' : 'button';
    const type = compact ? '' : ' type="button"';
    const items = cards
      .map((card) => {
        const live =
          !compact && card.status === 'running'
            ? '<span class="mock-live">Agent running this stage</span>'
            : !compact && card.status === 'waiting_approval'
              ? `<span class="mock-live">${escapeHtml(card.preview)}</span>`
              : '';
        return `
          <${tag}${type} class="mock-card status-${card.status}${state.openCardId === card.id && !compact ? ' is-open' : ''}" ${compact ? '' : `data-open-card="${card.id}"`}>
            <div class="mock-card-top">
              <strong>${escapeHtml(card.title)}</strong>
              <span class="status status-${card.status}">${STATUS_LABEL[card.status]}</span>
            </div>
            ${compact ? '' : `<span class="mock-ext">${escapeHtml(card.external)}</span>`}
            ${live}
          </${tag}>`;
      })
      .join('');

    return `
      <section class="mock-column">
        <header class="mock-column-head">
          <div>
            <h3>${escapeHtml(columnTitle(styleId, stage))}</h3>
            <p>${escapeHtml(columnMeta(styleId, stage))}</p>
          </div>
          <span class="mock-count">${cards.length}</span>
        </header>
        ${add}
        ${items}
      </section>`;
  }).join('');

  const inspectorShown = !compact && openCard ? inspectorHtml(styleId, openCard) : '';

  return `
    <div class="mock${compact ? ' is-compact' : ''}${split ? ' is-split' : ''}" data-theme="${styleId}">
      <header class="mock-header">
        <div class="mock-brand">
          <span class="mock-mark">Norns</span>
          <span class="mock-board-name">Default board</span>
        </div>
        <div class="mock-header-meta">
          <span class="mock-wait">${waitingCount} waiting</span>
          <span class="mock-user">admin</span>
        </div>
      </header>
      <div class="mock-body">
        ${queueHtml}
        <div class="mock-board">${columns}</div>
        ${!compact && openCard && !split ? inspectorShown : ''}
        ${!compact && split && openCard ? inspectorShown : ''}
      </div>
    </div>
  `;
}

function compareHtml() {
  return `<div class="compare-grid">${ORDER.map((id) => {
    const selected = state.picked === id;
    const rec = STYLES[id].recommended ? '<span class="rec">Recommended</span>' : '';
    return `
      <article class="compare-card${selected ? ' is-picked' : ''}">
        <header class="compare-head">
          <div>
            <h2>${escapeHtml(STYLES[id].name)}${rec}</h2>
            <p>${escapeHtml(STYLES[id].tagline)}</p>
          </div>
          <div class="compare-actions">
            <button type="button" class="lab-btn" data-view="${id}">Open</button>
            <button type="button" class="lab-btn lab-btn-primary${selected ? ' is-on' : ''}" data-pick="${id}">
              ${selected ? 'Selected' : 'Select'}
            </button>
          </div>
        </header>
        <div class="compare-preview" data-view="${id}" role="button" tabindex="0">
          ${boardHtml(id, true)}
        </div>
      </article>`;
  }).join('')}</div>`;
}

function fullHtml(styleId) {
  const meta = STYLES[styleId];
  const selected = state.picked === styleId;
  return `
    <section class="full-preview">
      <div class="full-meta">
        <button type="button" class="lab-btn" data-view="compare">All four</button>
        <div>
          <h2>${escapeHtml(meta.name)}</h2>
          <p>${escapeHtml(meta.tagline)}</p>
        </div>
        <button type="button" class="lab-btn lab-btn-primary${selected ? ' is-on' : ''}" data-pick="${styleId}">
          ${selected ? `Selected · ${escapeHtml(meta.name)}` : `Select ${escapeHtml(meta.name)}`}
        </button>
      </div>
      ${boardHtml(styleId, false)}
    </section>
  `;
}

function render() {
  renderTabs();
  renderPicked();
  document.getElementById('stage').innerHTML =
    state.view === 'compare' ? compareHtml() : fullHtml(state.view);
}

document.addEventListener('click', (event) => {
  const target = event.target.closest('[data-view], [data-pick], [data-open-card], [data-close-inspector]');
  if (!target) return;

  if (target.hasAttribute('data-close-inspector')) {
    state.openCardId = '';
    render();
    return;
  }
  if (target.dataset.pick) {
    pick(target.dataset.pick);
    return;
  }
  if (target.dataset.view) {
    setView(target.dataset.view);
    return;
  }
  if (target.dataset.openCard) {
    if (state.view === 'compare') return;
    openCard(target.dataset.openCard);
  }
});

document.addEventListener('keydown', (event) => {
  if (event.key !== 'Enter' && event.key !== ' ') return;
  const preview = event.target.closest?.('.compare-preview');
  if (!preview?.dataset.view) return;
  event.preventDefault();
  setView(preview.dataset.view);
});

render();
