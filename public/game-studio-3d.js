/* ══════════════════════════════════════════════
   WAR ROOM — 3D GAME STUDIO controller
   Wires the 7-agent game pipeline to the new UI tab.
   Mirrors blender-studio.js conventions.
   ══════════════════════════════════════════════ */

const G3_AGENTS = [
  { id: 'game-director',       icon: '🎬', name: 'DIRECTOR',   role: 'Pillars + GDD',     abbr: 'DIR', color: '#c084fc' },
  { id: 'level-designer',      icon: '🗺️', name: 'LEVEL DSN',  role: 'level_01.json',     abbr: 'LVL', color: '#22d3ee' },
  { id: 'asset-lead',          icon: '📦', name: 'ASSET LEAD', role: 'glTF / procedural', abbr: 'AST', color: '#fb923c' },
  { id: 'engine-engineer',     icon: '⚙️', name: 'ENGINE',     role: 'Camera, Physics',   abbr: 'ENG', color: '#a78bfa' },
  { id: 'tech-art',            icon: '🎨', name: 'TECH-ART',   role: 'Materials, PostFX', abbr: 'ART', color: '#f0abfc' },
  { id: 'gameplay-programmer', icon: '🕹️', name: 'GAMEPLAY',   role: 'Three.js code',     abbr: 'GMP', color: '#fbbf24' },
  { id: 'vision-playtester',   icon: '🎮', name: 'PLAYTESTER', role: 'Plays + scores',    abbr: 'QA',  color: '#34d399' },
];

const game3dState = {
  initialised: false,
  running: false,
  paused: false,
  startTime: null,
  timer: null,
  sse: null,
  resumableSession: null,    // {sessionId, brief, paused_at, ...}
};

function _g3ApiKey() {
  const own = document.getElementById('g3-api-key');
  if (own && own.value.trim()) return own.value.trim();
  if (typeof state !== 'undefined' && state.apiKey) return state.apiKey;
  const el = document.getElementById('key-anthropic') || document.getElementById('bs-api-key');
  return el ? el.value.trim() : '';
}

function game3dInit() {
  if (game3dState.initialised) return;
  game3dState.initialised = true;

  const $desks = document.getElementById('g3-agent-desks');
  if ($desks) {
    $desks.innerHTML = G3_AGENTS.map(a => `
      <div class="g3-desk-card" id="g3-desk-${a.id}" data-agent="${a.id}" style="--agent-color:${a.color}">
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
            <span class="g3-desk-badge" id="g3-status-${a.id}">IDLE</span>
          </div>
          <div class="g3-desk-role">${a.role}</div>
          <div class="g3-desk-bubble" id="g3-statusline-${a.id}">
            <span class="g3-desk-typing"><span></span><span></span><span></span></span>
            <span class="g3-desk-bubble-text">Awaiting deployment.</span>
          </div>
        </div>
      </div>
    `).join('');

    // 3D tilt on hover — character without sacrificing pro feel.
    $desks.querySelectorAll('.g3-desk-card').forEach(card => {
      card.addEventListener('mousemove', e => {
        const r = card.getBoundingClientRect();
        const x = (e.clientX - r.left) / r.width  - 0.5;
        const y = (e.clientY - r.top)  / r.height - 0.5;
        card.style.transform = `perspective(620px) rotateY(${x * 6}deg) rotateX(${-y * 5}deg)`;
      });
      card.addEventListener('mouseleave', () => { card.style.transform = ''; });
    });
  }

  // Connect SSE — share whichever stream is open, otherwise open one.
  if (!game3dState.sse) {
    try {
      game3dState.sse = new EventSource('/api/stream');
      _wireG3SSE(game3dState.sse);
    } catch (e) {
      console.error('SSE failed', e);
    }
  }

  // Check for any paused-or-incomplete session waiting on disk.
  _g3CheckResumable();
}

async function _g3CheckResumable() {
  try {
    const res = await fetch('/api/game/sessions');
    if (!res.ok) return;
    const data = await res.json();
    const sessions = (data.sessions || []).filter(s => !s.completed);
    if (!sessions.length) {
      const banner = document.getElementById('g3-resume-banner');
      if (banner) banner.hidden = true;
      return;
    }
    const newest = sessions[0];
    game3dState.resumableSession = newest;
    const banner = document.getElementById('g3-resume-banner');
    const info = document.getElementById('g3-resume-info-line');
    if (banner && info) {
      const when = newest.paused_at
        ? `paused ${_g3RelativeTime(newest.paused_at)}`
        : `last touched ${_g3RelativeTime(newest.saved_at || Date.now())}`;
      const briefSnippet = (newest.brief || '').slice(0, 64) + (newest.brief?.length > 64 ? '…' : '');
      info.textContent = `${briefSnippet || newest.session_id} · ${newest.file_count || 0} files · ${(newest.tokens || 0).toLocaleString()} tokens · ${when}`;
      banner.hidden = false;
    }
  } catch (e) {
    console.warn('resumable session check failed', e);
  }
}

function _g3RelativeTime(ts) {
  const dt = Date.now() - ts;
  if (dt < 60000) return 'just now';
  if (dt < 3600000) return `${Math.floor(dt / 60000)}m ago`;
  if (dt < 86400000) return `${Math.floor(dt / 3600000)}h ago`;
  return `${Math.floor(dt / 86400000)}d ago`;
}

function _wireG3SSE(es) {
  es.addEventListener('agent-status', (ev) => {
    const d = JSON.parse(ev.data);
    const status = d.status || 'idle';
    const $card = document.getElementById('g3-desk-' + d.agentId);
    const $badge = document.getElementById('g3-status-' + d.agentId);
    if ($card) {
      $card.classList.remove('status-idle', 'status-thinking', 'status-working', 'status-talking');
      $card.classList.add('status-' + status);
    }
    if ($badge) $badge.textContent = status.toUpperCase();
    _g3UpdateActiveAgent(d.agentId, status);
  });

  es.addEventListener('new-message', (ev) => {
    const d = JSON.parse(ev.data);
    const feed = document.getElementById('g3-feed-' + d.from) ||
                 document.getElementById('g3-playtest-feed');
    if (feed) {
      const line = document.createElement('div');
      line.className = 'bs-feed-line';
      line.textContent = (d.message || '').slice(0, 240);
      feed.appendChild(line);
      feed.scrollTop = feed.scrollHeight;
      // Keep each feed bounded.
      while (feed.children.length > 60) feed.removeChild(feed.firstChild);
    }
    // Derive a friendly status line for the agent's card.
    if (d.from && d.message) _g3UpdateStatusLine(d.from, d.message);
  });

  // Live token streaming — append deltas to a single bubble per call so
  // viewers see characters appear as Claude types them.
  es.addEventListener('agent-stream', (ev) => {
    const d = JSON.parse(ev.data);
    const feed = document.getElementById('g3-feed-' + d.from);
    if (!feed) return;
    let line = feed.querySelector(`[data-stream-id="${d.messageId}"]`);
    if (!line) {
      line = document.createElement('div');
      line.className = 'bs-feed-line g3-streaming';
      line.dataset.streamId = d.messageId;
      feed.appendChild(line);
      while (feed.children.length > 60) feed.removeChild(feed.firstChild);
    }
    if (d.delta) {
      line.textContent += d.delta;
      // Keep the live bubble visible at the bottom of the feed.
      feed.scrollTop = feed.scrollHeight;
      // Also surface the latest sentence into the agent's status-line card.
      const accumulated = line.textContent;
      const lastSentence = accumulated.split('\n').pop().slice(-160);
      _g3UpdateStatusLine(d.from, lastSentence);
    }
    if (d.done) {
      line.classList.remove('g3-streaming');
    }
  });

  es.addEventListener('token-update', (ev) => {
    const d = JSON.parse(ev.data);
    const $t = document.getElementById('g3-tokens');
    if ($t) $t.textContent = (d.total || 0).toLocaleString();
  });

  es.addEventListener('game-start', () => {
    document.getElementById('g3-status').textContent = 'BUILDING';
    game3dState.running = true;
    game3dState.paused = false;
    game3dState.startTime = Date.now();
    if (game3dState.timer) clearInterval(game3dState.timer);
    game3dState.timer = setInterval(_g3UpdateTimer, 1000);
    _g3UpdatePauseButton();
    _g3CollapseBrief();
    const banner = document.getElementById('g3-resume-banner');
    if (banner) banner.hidden = true;
  });

  es.addEventListener('game-resumed', (ev) => {
    const d = JSON.parse(ev.data);
    document.getElementById('g3-status').textContent = d.mode === 'live' ? 'BUILDING' : 'RESUMED';
    game3dState.running = true;
    game3dState.paused = false;
    if (!game3dState.timer) {
      game3dState.startTime = Date.now();
      game3dState.timer = setInterval(_g3UpdateTimer, 1000);
    }
    _g3UpdatePauseButton();
    _g3CollapseBrief();
    const banner = document.getElementById('g3-resume-banner');
    if (banner) banner.hidden = true;
  });

  es.addEventListener('game-paused', () => {
    document.getElementById('g3-status').textContent = 'PAUSED';
    game3dState.paused = true;
    _g3UpdatePauseButton();
  });

  es.addEventListener('game-done', () => {
    document.getElementById('g3-status').textContent = 'COMPLETE';
    game3dState.running = false;
    game3dState.paused = false;
    if (game3dState.timer) clearInterval(game3dState.timer);
    _g3UpdatePauseButton();
    g3PreviewRefresh(true);
  });

  es.addEventListener('game-error', (ev) => {
    const d = JSON.parse(ev.data);
    document.getElementById('g3-status').textContent = 'ERROR';
    const feed = document.getElementById('g3-playtest-feed');
    if (feed) feed.innerHTML += `<div class="bs-feed-line" style="color:#ff5577">${(d.message || '').slice(0,300)}</div>`;
    _g3ShowPreviewError(d.message || 'Pipeline error');
  });

  es.addEventListener('game-stopped', () => {
    document.getElementById('g3-status').textContent = 'STOPPED';
    game3dState.running = false;
    game3dState.paused = false;
    if (game3dState.timer) clearInterval(game3dState.timer);
    _g3UpdatePauseButton();
    _g3ExpandBrief();
  });

  es.addEventListener('new-file', (ev) => {
    const d = JSON.parse(ev.data);
    if (!d.path) return;
    // Live-refresh the preview when public/* assets land. Debounced inside helper.
    if (/^public\//.test(d.path) && /\.(html|js|mjs|css)$/i.test(d.path)) {
      _g3SchedulePreviewRefresh();
    } else if (d.path.includes('playtest-report')) {
      _g3SchedulePreviewRefresh();
    }
  });

  // Wire the iframe load/error hooks once.
  const iframe = document.getElementById('g3-preview-iframe');
  if (iframe && !iframe._g3HookInstalled) {
    iframe._g3HookInstalled = true;
    iframe.addEventListener('load', _g3OnPreviewLoad);
  }
}

// ── Brief collapse / expand ─────────────────────────────────────────────

function _g3CollapseBrief() {
  const $form = document.getElementById('g3-form');
  const $summary = document.getElementById('g3-brief-summary');
  const $text = document.getElementById('g3-brief-summary-text');
  const $brief = document.getElementById('g3-brief');
  const $main = document.querySelector('.g3-live-main');
  if (!$form || !$summary || !$text) return;
  const text = (
    ($brief?.value || '').trim() ||
    game3dState.resumableSession?.brief ||
    '(no brief)'
  );
  $text.textContent = text.length > 140 ? text.slice(0, 137) + '…' : text;
  $form.hidden = true;
  $summary.hidden = false;
  if ($main) $main.classList.add('g3-running');
}

function _g3ExpandBrief() {
  const $form = document.getElementById('g3-form');
  const $summary = document.getElementById('g3-brief-summary');
  const $main = document.querySelector('.g3-live-main');
  if (!$form || !$summary) return;
  $form.hidden = false;
  $summary.hidden = true;
  if ($main) $main.classList.remove('g3-running');
}

function g3EditBrief() {
  if (game3dState.running && !confirm('A run is in progress. Stop it and start a new mission?')) return;
  if (game3dState.running) game3dStop();
  _g3ExpandBrief();
}

// ── Active agent + status line ───────────────────────────────────────────

const _g3ActiveAgents = new Set();

function _g3UpdateActiveAgent(agentId, status) {
  const isActive = status === 'thinking' || status === 'working';
  if (isActive) _g3ActiveAgents.add(agentId);
  else _g3ActiveAgents.delete(agentId);

  // Apply active/dimmed classes across all cards.
  const anyActive = _g3ActiveAgents.size > 0;
  document.querySelectorAll('.g3-desk-card').forEach(card => {
    const id = card.dataset.agent;
    const active = _g3ActiveAgents.has(id);
    card.classList.toggle('g3-active', active);
    card.classList.toggle('g3-dimmed', anyActive && !active);
  });

  if (status === 'idle') {
    const $line = document.getElementById('g3-statusline-' + agentId);
    if ($line && !$line._lockedAt) {
      const $text = $line.querySelector('.g3-desk-bubble-text') || $line;
      $text.textContent = 'Done.';
    }
  }
}

const _G3_TOOL_VERBS = {
  write_file: 'Writing',
  read_file: 'Reading',
  list_files: 'Listing files in',
  run_command: 'Running',
  web_search: 'Searching for',
};

function _g3DeriveStatus(rawMessage) {
  const msg = (rawMessage || '').trim();
  if (!msg) return null;
  // Tool call: 🔧 `tool_name` ← {...}  (the JSON is truncated to 120 chars upstream,
  // so we don't require a closing brace and fall back to regex extraction.)
  const toolCall = msg.match(/🔧\s*`([^`]+)`\s*←\s*(\{[\s\S]+)/);
  if (toolCall) {
    const tool = toolCall[1];
    const verb = _G3_TOOL_VERBS[tool] || `Calling ${tool}`;
    const blob = toolCall[2];
    let target = '';
    try {
      const args = JSON.parse(blob);
      target = args.path || args.command || args.query || args.subdir || '';
    } catch {
      const m = blob.match(/"(?:path|command|query|subdir)"\s*:\s*"([^"]+)"/);
      if (m) target = m[1];
    }
    return target ? `${verb} ${target}` : `${verb}…`;
  }
  // Tool result: ↩ {...}
  if (msg.startsWith('↩')) {
    const body = msg.slice(1).trim();
    try {
      const parsed = JSON.parse(body);
      if (parsed.ok && parsed.path) return `Wrote ${parsed.path}`;
      if (parsed.error) return `Tool error: ${parsed.error}`.slice(0, 120);
    } catch { /* not JSON — show first line */ }
    return body.split('\n')[0].slice(0, 120);
  }
  // Cache notice — boring, skip.
  if (msg.startsWith('cache_hit:')) return null;
  // Warning / API error — surface it.
  if (msg.startsWith('⚠️')) return msg.slice(0, 140);
  // Plain narration — first line, capped.
  return msg.split('\n')[0].slice(0, 140);
}

function _g3UpdateStatusLine(agentId, rawMessage) {
  const $line = document.getElementById('g3-statusline-' + agentId);
  if (!$line) return;
  const derived = _g3DeriveStatus(rawMessage);
  if (!derived) return;
  const $text = $line.querySelector('.g3-desk-bubble-text') || $line;
  $text.textContent = derived;
  $line._lockedAt = Date.now();
}

// ── Preview state machine ────────────────────────────────────────────────
function _g3SetPreviewBadge(state, label) {
  const $b = document.getElementById('g3-preview-badge');
  if (!$b) return;
  $b.className = 'g3-preview-badge g3-preview-' + state;
  $b.textContent = label;
}

function _g3HidePreviewError() {
  const $e = document.getElementById('g3-preview-error');
  if ($e) $e.hidden = true;
}

function _g3ShowPreviewError(message) {
  const $e = document.getElementById('g3-preview-error');
  const $m = document.getElementById('g3-preview-error-msg');
  if ($m) $m.textContent = (message || '').toString().slice(0, 800);
  if ($e) $e.hidden = false;
  _g3SetPreviewBadge('error-st', 'ERROR');
}

let _g3RefreshTimer = null;
function _g3SchedulePreviewRefresh() {
  // Debounce: a flurry of file writes triggers one reload ~1.2s after the last one.
  if (_g3RefreshTimer) clearTimeout(_g3RefreshTimer);
  _g3SetPreviewBadge('building', 'BUILDING…');
  _g3RefreshTimer = setTimeout(() => g3PreviewRefresh(false), 1200);
}

function g3PreviewRefresh(forceVisible) {
  const iframe = document.getElementById('g3-preview-iframe');
  if (!iframe) return;
  _g3HidePreviewError();
  _g3SetPreviewBadge('refreshing', 'REFRESHING…');
  iframe.src = '/preview-game?t=' + Date.now();
}

function _g3OnPreviewLoad() {
  const iframe = document.getElementById('g3-preview-iframe');
  if (!iframe) return;
  if ((iframe.src || '').startsWith('about:')) {
    _g3SetPreviewBadge('standby', 'STANDBY');
    return;
  }
  // Same-origin — we can read the iframe's window and listen for runtime errors.
  let win = null;
  try { win = iframe.contentWindow; } catch { win = null; }
  if (win && !win._g3ErrorHookInstalled) {
    win._g3ErrorHookInstalled = true;
    win.addEventListener('error', (ev) => {
      const msg = ev?.error?.stack || ev?.message || 'Runtime error in preview';
      _g3ShowPreviewError(msg);
    });
    win.addEventListener('unhandledrejection', (ev) => {
      const msg = ev?.reason?.stack || ev?.reason?.message || String(ev?.reason || 'Unhandled rejection');
      _g3ShowPreviewError(msg);
    });
  }
  // Detect the placeholder ("STANDING BY" / "VITE COMPILE IN PROGRESS") vs a real game.
  let isPlaceholder = false;
  try {
    const body = win?.document?.body?.textContent || '';
    isPlaceholder = /STANDING BY|VITE COMPILE IN PROGRESS|AWAITING/.test(body);
  } catch { /* cross-origin or not loaded */ }
  if (isPlaceholder) {
    _g3SetPreviewBadge('building', 'BUILDING…');
  } else {
    _g3SetPreviewBadge('ready', 'READY');
  }
}

function _g3UpdateTimer() {
  const $t = document.getElementById('g3-timer');
  if (!$t || !game3dState.startTime) return;
  const s = Math.floor((Date.now() - game3dState.startTime) / 1000);
  const h = String(Math.floor(s / 3600)).padStart(2, '0');
  const m = String(Math.floor((s % 3600) / 60)).padStart(2, '0');
  const ss = String(s % 60).padStart(2, '0');
  $t.textContent = `${h}:${m}:${ss}`;
}

async function game3dStart() {
  const apiKey = _g3ApiKey();
  if (!apiKey) {
    alert('Anthropic API key required.');
    return;
  }
  const brief = document.getElementById('g3-brief').value.trim();
  if (!brief) {
    alert('Describe the game first.');
    return;
  }
  const genre = document.getElementById('g3-genre').value;
  const artStyle = document.getElementById('g3-style').value;

  document.getElementById('g3-status').textContent = 'DEPLOYING';
  game3dState.running = true;

  try {
    const res = await fetch('/api/game/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ brief, genre, artStyle, target: 'web', apiKey }),
    });
    if (!res.ok) {
      const txt = await res.text();
      throw new Error(`HTTP ${res.status}: ${txt.slice(0,200)}`);
    }
  } catch (e) {
    document.getElementById('g3-status').textContent = 'ERROR';
    alert('Deploy failed: ' + e.message);
    game3dState.running = false;
  }
}

async function game3dStop() {
  try { await fetch('/api/game/stop', { method: 'POST' }); } catch (e) {}
}

async function game3dTogglePause() {
  // If currently paused → resume; else → pause.
  const url = game3dState.paused ? '/api/game/resume' : '/api/game/pause';
  try {
    const opts = { method: 'POST', headers: { 'Content-Type': 'application/json' } };
    if (game3dState.paused) {
      opts.body = JSON.stringify({ apiKey: _g3ApiKey() });
    }
    const res = await fetch(url, opts);
    if (!res.ok) {
      const txt = await res.text();
      console.warn('toggle pause failed', res.status, txt);
      return;
    }
    // SSE will flip the UI state — but flip optimistically so the button responds.
    game3dState.paused = !game3dState.paused;
    _g3UpdatePauseButton();
  } catch (e) {
    console.warn('toggle pause failed', e);
  }
}

async function game3dResumeFromDisk() {
  const apiKey = _g3ApiKey();
  if (!apiKey) {
    alert('Anthropic API key required to resume.');
    return;
  }
  const sessionId = game3dState.resumableSession?.session_id;
  try {
    const res = await fetch('/api/game/resume', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ apiKey, sessionId }),
    });
    if (!res.ok) {
      const txt = await res.text();
      throw new Error(`HTTP ${res.status}: ${txt.slice(0, 200)}`);
    }
    document.getElementById('g3-resume-banner').hidden = true;
    _g3UpdatePauseButton();
  } catch (e) {
    alert('Resume failed: ' + e.message);
  }
}

function _g3UpdatePauseButton() {
  const btn = document.getElementById('g3-pause-btn');
  if (!btn) return;
  if (!game3dState.running) {
    btn.hidden = true;
    return;
  }
  btn.hidden = false;
  if (game3dState.paused) {
    btn.textContent = '▶ RESUME';
    btn.classList.add('is-paused');
  } else {
    btn.textContent = '⏸ PAUSE';
    btn.classList.remove('is-paused');
  }
}
