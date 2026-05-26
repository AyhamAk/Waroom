/* ═══════════════════════════════════════════════════════════════
   QA STUDIO — Multi-Agent Bug Hunter
   Live agent desks with speech bubbles, typing dots, glow rings,
   mini-map pipeline graph, screenshot feed, and bug tracker.
═══════════════════════════════════════════════════════════════ */

const qaState = {
  running: false,
  sessionId: null,
  sse: null,
  bugs: [],
  screenshots: {},
  _mmInitialized: false,
};

const QA_AGENTS = [
  { id: 'scout-qa',      icon: '🔍', name: 'SCOUT',       role: 'Maps routes & forms',          abbr: 'SCT', color: '#22d3ee' },
  { id: 'visual-qa',     icon: '👁',  name: 'VISUAL',      role: 'Screenshots + scroll capture', abbr: 'VIS', color: '#c084fc' },
  { id: 'console-qa',    icon: '⚡',  name: 'CONSOLE',     role: 'JS errors & 404s',             abbr: 'CON', color: '#fbbf24' },
  { id: 'a11y-qa',       icon: '♿',  name: 'A11Y',        role: 'Accessibility scan',           abbr: 'A11', color: '#34d399' },
  { id: 'security-qa',   icon: '🔒',  name: 'SECURITY',    role: 'Headers & secrets',            abbr: 'SEC', color: '#f87171' },
  { id: 'functional-qa', icon: '🖱',  name: 'FUNCTIONAL',  role: 'Links, forms, flows',          abbr: 'FUN', color: '#fb923c' },
  { id: 'style-qa',      icon: '🎨',  name: 'STYLE',       role: 'Contrast, typography, targets',abbr: 'STY', color: '#e879f9' },
  { id: 'synthesis-qa',  icon: '📋',  name: 'SYNTHESIS',   role: 'Aggregates & reports',         abbr: 'SYN', color: '#00e676' },
];

const SEV_COLOR = { critical:'#ff4444', high:'#ff8800', medium:'#ffcc00', low:'#44aaff', info:'#888888' };
const SEV_EMOJI = { critical:'🔴', high:'🟠', medium:'🟡', low:'🔵', info:'⚪' };

// Mini-map node positions (SVG 320×130 viewBox)
const QA_MM_POS = {
  'scout-qa':      { x: 160, y: 20  },
  'visual-qa':     { x: 25,  y: 72  },
  'console-qa':    { x: 73,  y: 72  },
  'a11y-qa':       { x: 121, y: 72  },
  'security-qa':   { x: 199, y: 72  },
  'functional-qa': { x: 247, y: 72  },
  'style-qa':      { x: 295, y: 72  },
  'synthesis-qa':  { x: 160, y: 115 },
};

// Parallel agents that fan out from scout
const QA_PARALLEL = ['visual-qa','console-qa','a11y-qa','security-qa','functional-qa','style-qa'];

// ── Init ──────────────────────────────────────────────────────

function initQAStudio() {
  _renderAgentDesks();
  _renderScreenshotGrid();
  _initMiniMap();
}

function _renderAgentDesks() {
  const container = document.getElementById('qa-agent-desks');
  if (!container) return;
  container.innerHTML = QA_AGENTS.map(a => `
    <div class="g3-desk-card qa-desk-card" id="qa-desk-${a.id}"
         data-agent="${a.id}" style="--agent-color:${a.color}">
      <div class="g3-desk-portrait-wrap">
        <div class="g3-desk-portrait">
          <span class="g3-desk-emoji">${a.icon}</span>
          <span class="g3-desk-abbr">${a.abbr}</span>
        </div>
        <div class="g3-desk-status-ring"></div>
      </div>
      <div class="g3-desk-info">
        <div class="g3-desk-header-row">
          <div class="g3-desk-name" style="color:${a.color}">${a.name}</div>
          <span class="g3-desk-badge" id="qa-badge-${a.id}">IDLE</span>
        </div>
        <div class="g3-desk-role">${a.role}</div>
        <div class="g3-desk-bubble" id="qa-bubble-${a.id}">
          <span class="g3-desk-typing" id="qa-typing-${a.id}">
            <span></span><span></span><span></span>
          </span>
          <span class="g3-desk-bubble-text" id="qa-line-${a.id}">Standing by.</span>
        </div>
        <div class="qa-desk-bug-count" id="qa-count-${a.id}"></div>
      </div>
    </div>
  `).join('');
}

function _renderScreenshotGrid() {
  const grid = document.getElementById('qa-screenshot-grid');
  if (!grid) return;
  const parallel = QA_AGENTS.filter(a => a.id !== 'synthesis-qa' && a.id !== 'scout-qa');
  grid.innerHTML = parallel.map(a => `
    <div class="qa-shot-panel" id="qa-shot-${a.id}">
      <div class="qa-shot-label" style="color:${a.color}">${a.icon} ${a.name}</div>
      <div class="qa-shot-idle" id="qa-shot-idle-${a.id}">awaiting...</div>
      <img class="qa-shot-img" id="qa-img-${a.id}" src="" alt="" hidden />
    </div>
  `).join('');
}

// ── Mini-Map ──────────────────────────────────────────────────

function _initMiniMap() {
  const $nodes = document.getElementById('qa-mm-nodes');
  const $edges = document.getElementById('qa-mm-edges');
  if (!$nodes || !$edges) return;

  // Draw edges: scout → each parallel agent, each parallel → synthesis
  const edgeDefs = [
    ...QA_PARALLEL.map(id => ({ from: 'scout-qa', to: id })),
    ...QA_PARALLEL.map(id => ({ from: id, to: 'synthesis-qa' })),
  ];

  $edges.innerHTML = edgeDefs.map(({ from, to }) => {
    const a = QA_MM_POS[from], b = QA_MM_POS[to];
    const ag = QA_AGENTS.find(x => x.id === from);
    const gradId = `qag-${from.replace(/-/g,'_')}_${to.replace(/-/g,'_')}`;
    return `
      <defs>
        <linearGradient id="${gradId}" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stop-color="${ag ? ag.color : '#444'}" stop-opacity="0.7"/>
          <stop offset="100%" stop-color="#1a1a2e" stop-opacity="0.2"/>
        </linearGradient>
      </defs>
      <line class="g3-mm-edge" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"
            stroke="url(#${gradId})" stroke-width="1.4" opacity="0.5"/>
    `;
  }).join('');

  // Draw nodes
  $nodes.innerHTML = QA_AGENTS.map(a => {
    const p = QA_MM_POS[a.id];
    return `
      <g class="g3-mm-node" id="qa-mm-${a.id}" data-agent="${a.id}"
         style="--agent-color:${a.color}">
        <circle class="g3-mm-halo" cx="${p.x}" cy="${p.y}" r="12" fill="${a.color}" opacity="0"/>
        <circle class="g3-mm-circle" cx="${p.x}" cy="${p.y}" r="7"
                fill="#080a14" stroke="${a.color}" stroke-width="1.5" opacity="0.7"/>
        <text class="g3-mm-abbr" x="${p.x}" y="${p.y + 17}"
              text-anchor="middle" fill="${a.color}" font-size="7"
              font-family="'Share Tech Mono',monospace" opacity="0.8">${a.abbr}</text>
      </g>
    `;
  }).join('');

  qaState._mmInitialized = true;
}

function _mmSetActive(agentId, active) {
  const $node = document.getElementById(`qa-mm-${agentId}`);
  if (!$node) return;
  const $halo = $node.querySelector('.g3-mm-halo');
  const $circle = $node.querySelector('.g3-mm-circle');
  if (active) {
    $node.classList.add('active');
    if ($halo) { $halo.style.opacity = '0.35'; $halo.style.animation = 'g3MmHaloPulse 1.4s ease-in-out infinite'; }
    if ($circle) $circle.style.opacity = '1';
  } else {
    $node.classList.remove('active');
    if ($halo) { $halo.style.opacity = '0'; $halo.style.animation = ''; }
    if ($circle) $circle.style.opacity = '0.7';
  }
}

function _mmEmitPulse(fromId, toId, label) {
  const $pulses = document.getElementById('qa-mm-pulses');
  if (!$pulses) return;
  const a = QA_MM_POS[fromId], b = QA_MM_POS[toId];
  if (!a || !b) return;
  const ag = QA_AGENTS.find(x => x.id === fromId);
  const color = ag ? ag.color : '#00e676';
  const dur = 700;
  const id = `qap-${Date.now()}-${Math.random().toString(36).slice(2,6)}`;

  const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
  g.id = id;
  g.innerHTML = `
    <line class="g3-mm-comet-trail"
          x1="${a.x}" y1="${a.y}" x2="${a.x}" y2="${a.y}"
          stroke="${color}" stroke-width="2.5" opacity="0.6"/>
    <circle class="g3-mm-comet-head" cx="${a.x}" cy="${a.y}" r="3.5"
            fill="${color}" filter="url(#g3-mm-glow)" opacity="0.95"/>
    ${label ? `<text x="${(a.x+b.x)/2}" y="${(a.y+b.y)/2 - 5}" text-anchor="middle"
               font-size="6" fill="${color}" opacity="0.7"
               font-family="'Share Tech Mono',monospace">${label.slice(0,12)}</text>` : ''}
  `;
  $pulses.appendChild(g);

  const head = g.querySelector('.g3-mm-comet-head');
  const trail = g.querySelector('.g3-mm-comet-trail');
  const start = performance.now();

  function frame(now) {
    const t = Math.min((now - start) / dur, 1);
    const ease = t < 0.5 ? 2*t*t : -1+(4-2*t)*t;
    const cx = a.x + (b.x - a.x) * ease;
    const cy = a.y + (b.y - a.y) * ease;
    if (head) { head.setAttribute('cx', cx); head.setAttribute('cy', cy); }
    if (trail) { trail.setAttribute('x2', cx); trail.setAttribute('y2', cy); }
    if (t < 1) { requestAnimationFrame(frame); }
    else {
      // Burst at destination
      const burst = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      burst.setAttribute('cx', b.x); burst.setAttribute('cy', b.y);
      burst.setAttribute('r', '4'); burst.setAttribute('fill', 'none');
      burst.setAttribute('stroke', color); burst.setAttribute('stroke-width', '1.5');
      burst.style.opacity = '0.9';
      $pulses.appendChild(burst);
      setTimeout(() => {
        burst.style.transition = 'all 0.6s ease-out';
        burst.setAttribute('r', '12'); burst.style.opacity = '0';
        setTimeout(() => { try { $pulses.removeChild(burst); } catch(_) {} }, 650);
      }, 20);
      setTimeout(() => { try { $pulses.removeChild(g); } catch(_) {} }, 200);
    }
  }
  requestAnimationFrame(frame);
}

// ── Start / Stop ──────────────────────────────────────────────

async function qaStart() {
  const urlEl  = document.getElementById('qa-url-input');
  const keyEl  = document.getElementById('qa-api-key');
  const url    = urlEl?.value.trim() || '';
  const apiKey = keyEl?.value.trim() || (typeof state !== 'undefined' ? state.apiKey : '') || '';

  if (!url)    { alert('Enter a URL to test.');           return; }
  if (!apiKey) { alert('Enter your Anthropic API key.'); return; }

  // Reset
  qaState.bugs = [];
  qaState.screenshots = {};
  _clearBugFeed();
  _resetAgentDesks();
  _resetScreenshots();
  _updateStats();

  document.getElementById('qa-start-btn').disabled = true;
  document.getElementById('qa-stop-btn').hidden = false;
  _setStatus('SCANNING');

  // Reset mini-map
  QA_AGENTS.forEach(a => _mmSetActive(a.id, false));

  try {
    const res  = await fetch('/api/qa/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, apiKey }),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || 'Start failed');
    qaState.sessionId = data.sessionId;
    qaState.running   = true;
    _connectSSE();
  } catch (err) {
    alert('Failed to start QA: ' + err.message);
    document.getElementById('qa-start-btn').disabled = false;
    document.getElementById('qa-stop-btn').hidden    = true;
    _setStatus('ERROR');
  }
}

async function qaStop() {
  await fetch('/api/qa/stop', { method: 'POST' });
  _disconnectSSE();
  qaState.running = false;
  document.getElementById('qa-start-btn').disabled = false;
  document.getElementById('qa-stop-btn').hidden    = true;
  _setStatus('STOPPED');
}

// ── SSE ───────────────────────────────────────────────────────

function _connectSSE() {
  _disconnectSSE();
  const es = new EventSource('/api/stream');
  qaState.sse = es;

  es.addEventListener('qa-start', () => {
    _setStatus('SCANNING');
    _mmSetActive('scout-qa', true);
    _updateBubble('scout-qa', 'Mapping target URL...');
  });

  es.addEventListener('qa-done', (ev) => {
    const d = JSON.parse(ev.data);
    _setStatus('COMPLETE');
    document.getElementById('qa-start-btn').disabled = false;
    document.getElementById('qa-stop-btn').hidden    = true;
    qaState.running = false;
    QA_AGENTS.forEach(a => _mmSetActive(a.id, false));
    _mmSetActive('synthesis-qa', false);
    _addLog(`✅ Scan complete — ${d.totalBugs || 0} bugs found`, '#44ff88');
    _updateBubble('synthesis-qa', `Report done. ${d.totalBugs || 0} bugs found.`);
  });

  es.addEventListener('qa-stopped', () => {
    _setStatus('STOPPED');
    document.getElementById('qa-start-btn').disabled = false;
    document.getElementById('qa-stop-btn').hidden    = true;
    QA_AGENTS.forEach(a => _mmSetActive(a.id, false));
  });

  es.addEventListener('qa-error', (ev) => {
    const d = JSON.parse(ev.data);
    _setStatus('ERROR');
    document.getElementById('qa-start-btn').disabled = false;
    document.getElementById('qa-stop-btn').hidden    = true;
    _addLog(`❌ ${d.message}`, '#ff4444');
  });

  es.addEventListener('agent-status', (ev) => {
    const d = JSON.parse(ev.data);
    if (!d.agentId || !QA_MM_POS[d.agentId]) return; // only handle QA agents
    _setAgentStatus(d.agentId, d.status);
  });

  es.addEventListener('new-message', (ev) => {
    const d = JSON.parse(ev.data);
    if (!d) return;
    const msg = (d.message || '').slice(0, 200);

    // Route message to the agent's speech bubble if it's a QA agent
    const agentFrom = d.from || '';
    if (QA_MM_POS[agentFrom]) {
      _updateBubble(agentFrom, msg);
      // Emit mini-map pulse based on who spoke
      if (agentFrom === 'scout-qa') {
        // Scout broadcasting to parallel agents
        QA_PARALLEL.forEach((id, i) =>
          setTimeout(() => _mmEmitPulse('scout-qa', id), i * 80)
        );
      } else if (agentFrom === 'synthesis-qa') {
        QA_PARALLEL.forEach((id, i) =>
          setTimeout(() => _mmEmitPulse(id, 'synthesis-qa'), i * 60)
        );
      } else if (QA_PARALLEL.includes(agentFrom)) {
        // Parallel agent sending data onward
        if (Math.random() > 0.6) _mmEmitPulse(agentFrom, 'synthesis-qa');
      }
    }
    _addLog(msg, '#778899');
  });

  es.addEventListener('qa-bug', (ev) => {
    const bug = JSON.parse(ev.data);
    if (!bug?.id) return;
    qaState.bugs.push(bug);
    _addBugToFeed(bug);
    _incrementAgentCount(bug.agentId);
    _updateStats();
    // Flash mini-map node when bug found
    const $node = document.getElementById(`qa-mm-${bug.agentId}`);
    if ($node) {
      $node.classList.add('mm-flash');
      setTimeout(() => $node.classList.remove('mm-flash'), 600);
    }
    // Update bubble with find
    const sev = bug.severity || 'info';
    _updateBubble(bug.agentId, `${SEV_EMOJI[sev]} Found: ${(bug.title || '').slice(0, 60)}`);
  });

  es.addEventListener('qa-screenshot', (ev) => {
    const d = JSON.parse(ev.data);
    if (!d.agentId || !d.url) return;
    qaState.screenshots[d.agentId] = d.url;
    _updateScreenshot(d.agentId, d.url, d.viewport || '');
  });

  es.onerror = () => { if (!qaState.running) es.close(); };
}

function _disconnectSSE() {
  if (qaState.sse) { qaState.sse.close(); qaState.sse = null; }
}

// ── Agent desk helpers ────────────────────────────────────────

function _setAgentStatus(agentId, status) {
  const $card  = document.getElementById(`qa-desk-${agentId}`);
  const $badge = document.getElementById(`qa-badge-${agentId}`);
  const $typing = document.getElementById(`qa-typing-${agentId}`);

  if ($card) {
    $card.classList.remove('status-idle','status-thinking','status-working');
    $card.classList.add(`status-${status}`);
  }
  if ($badge) {
    $badge.textContent = status.toUpperCase();
    $badge.style.color = status === 'idle' ? '#556' : '#000';
    $badge.style.background = { thinking:'#ffcc00', working:'#00e676', idle:'' }[status] || '';
  }
  if ($typing) {
    $typing.style.display = (status === 'thinking' || status === 'working') ? 'flex' : 'none';
  }

  const isActive = status === 'thinking' || status === 'working';
  _mmSetActive(agentId, isActive);

  // When scout goes idle, fan out comets to parallel agents
  if (agentId === 'scout-qa' && status === 'idle') {
    QA_PARALLEL.forEach((id, i) =>
      setTimeout(() => _mmEmitPulse('scout-qa', id), i * 100)
    );
  }
  // When a parallel agent goes idle, send comet to synthesis
  if (QA_PARALLEL.includes(agentId) && status === 'idle') {
    setTimeout(() => _mmEmitPulse(agentId, 'synthesis-qa'), 200);
  }
}

function _updateBubble(agentId, text) {
  const $line = document.getElementById(`qa-line-${agentId}`);
  if ($line && text) $line.textContent = text.slice(0, 100);
}

function _resetAgentDesks() {
  QA_AGENTS.forEach(a => {
    _setAgentStatus(a.id, 'idle');
    _updateBubble(a.id, 'Standing by.');
    const cnt = document.getElementById(`qa-count-${a.id}`);
    if (cnt) cnt.textContent = '';
  });
}

function _incrementAgentCount(agentId) {
  const el = document.getElementById(`qa-count-${agentId}`);
  if (!el) return;
  const n = (parseInt(el.dataset.count) || 0) + 1;
  el.dataset.count = n;
  el.textContent = `${n} bug${n !== 1 ? 's' : ''}`;
  el.style.color = SEV_COLOR['high'];
}

// ── Screenshot helpers ────────────────────────────────────────

function _updateScreenshot(agentId, url, viewport) {
  const $idle = document.getElementById(`qa-shot-idle-${agentId}`);
  const $img  = document.getElementById(`qa-img-${agentId}`);
  if (!$img) return;
  $img.src    = url + '?t=' + Date.now();
  $img.hidden = false;
  if ($idle) $idle.hidden = true;
  const $panel = document.getElementById(`qa-shot-${agentId}`);
  const $label = $panel?.querySelector('.qa-shot-label');
  if ($label && viewport) $label.title = viewport;
}

function _resetScreenshots() {
  QA_AGENTS.forEach(a => {
    const $idle = document.getElementById(`qa-shot-idle-${a.id}`);
    const $img  = document.getElementById(`qa-img-${a.id}`);
    if ($idle) { $idle.hidden = false; $idle.textContent = 'awaiting...'; }
    if ($img)  { $img.hidden = true; $img.src = ''; }
  });
}

// ── Bug feed ──────────────────────────────────────────────────

function _addBugToFeed(bug) {
  const feed = document.getElementById('qa-bug-feed');
  if (!feed) return;
  const sev       = bug.severity || 'info';
  const emoji     = SEV_EMOJI[sev] || '⚪';
  const color     = SEV_COLOR[sev] || '#888';
  const agent     = QA_AGENTS.find(a => a.id === bug.agentId);
  const agentName = agent ? agent.name : (bug.agentId || '?').toUpperCase();
  const hasShot   = !!bug.screenshot;
  const hasRepro  = !!bug.reproduction;

  // Screenshot section — only when a path exists
  const shotHtml = hasShot ? `
    <div class="qa-bug-screenshot-wrap">
      <img class="qa-bug-screenshot-img" src="${bug.screenshot}" alt="Bug screenshot"
           loading="lazy" onclick="this.classList.toggle('qa-img-zoom')" title="Click to zoom" />
      <a class="qa-dl-btn" href="${bug.screenshot}" download="bug_${_esc(bug.id || 'screenshot')}.png"
         title="Download screenshot">
        ⬇ Download Screenshot
      </a>
    </div>` : '';

  // Reproduction steps section
  const reproHtml = hasRepro ? `
    <div class="qa-repro-section">
      <div class="qa-repro-label">↳ HOW TO REPRODUCE</div>
      <pre class="qa-repro-steps">${_esc(bug.reproduction)}</pre>
    </div>` : '';

  const div = document.createElement('div');
  div.className = 'qa-bug-entry';
  div.style.borderLeft = `3px solid ${color}`;
  div.style.animation  = 'qaBugSlideIn 0.25s ease-out';
  div.innerHTML = `
    <details class="qa-bug-details">
      <summary class="qa-bug-summary">
        <div class="qa-bug-header">
          <span class="qa-bug-sev" style="color:${color}">${emoji} ${sev.toUpperCase()}</span>
          <span class="qa-bug-agent" style="color:${agent?.color || '#888'}">[${agentName}]</span>
          ${hasShot ? '<span class="qa-has-shot" title="Has screenshot">📸</span>' : ''}
        </div>
        <div class="qa-bug-title">${_esc(bug.title || '')}</div>
      </summary>
      <div class="qa-bug-expanded">
        ${bug.description ? `<div class="qa-bug-desc">${_esc(bug.description)}</div>` : ''}
        ${reproHtml}
        ${shotHtml}
      </div>
    </details>
  `;
  feed.prepend(div);
  while (feed.children.length > 80) feed.removeChild(feed.lastChild);
}

function _clearBugFeed() {
  const feed = document.getElementById('qa-bug-feed');
  if (feed) feed.innerHTML = '';
  const log = document.getElementById('qa-log-feed');
  if (log) log.innerHTML = '';
}

// ── Log ───────────────────────────────────────────────────────

function _addLog(msg, color) {
  const log = document.getElementById('qa-log-feed');
  if (!log) return;
  const div = document.createElement('div');
  div.className = 'bs-log-entry';
  div.style.color = color || '#667';
  div.textContent = msg;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  while (log.children.length > 120) log.removeChild(log.firstChild);
}

// ── Stats ─────────────────────────────────────────────────────

function _updateStats() {
  const bugs = qaState.bugs;
  const c = { critical:0, high:0, medium:0, low:0 };
  bugs.forEach(b => { if (c[b.severity] !== undefined) c[b.severity]++; });
  const el = document.getElementById('qa-stats');
  if (!el) return;
  el.innerHTML =
    `<span class="qa-stat-total">${bugs.length} BUGS</span>` +
    (c.critical ? `<span style="color:#ff4444">🔴 ${c.critical} CRIT</span>` : '') +
    (c.high     ? `<span style="color:#ff8800">🟠 ${c.high} HIGH</span>`     : '') +
    (c.medium   ? `<span style="color:#ffcc00">🟡 ${c.medium} MED</span>`    : '') +
    (c.low      ? `<span style="color:#44aaff">🔵 ${c.low} LOW</span>`       : '');
}

function _setStatus(text) {
  const el = document.getElementById('qa-status');
  if (el) el.textContent = text;
}

// ── Utils ─────────────────────────────────────────────────────

function _esc(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
