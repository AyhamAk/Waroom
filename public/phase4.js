/* ══════════════════════════════════════════════
   WAR ROOM — PHASE 4: LIVE MODE
   SSE, agent desks, comm feed, file tree, preview.
   Depends on: data.js, state.js, utils.js, app.js
   ══════════════════════════════════════════════ */

/* ── Phase 4 DOM refs ── */
const $liveTokens  = document.getElementById('live-tokens');
const $sessionTimer= document.getElementById('session-timer');
const $agentDesks  = document.getElementById('agent-desks');
const $commFeed    = document.getElementById('comm-feed');
const $fileTree    = document.getElementById('file-tree');
const $msgCount    = document.getElementById('msg-count');
const $ppBtn       = document.getElementById('play-pause-btn');
const $crisisBtn   = document.getElementById('crisis-btn');
const $exportBtn   = document.getElementById('export-all-btn');
const $countdownOv = document.getElementById('countdown-overlay');
const $countdownNo = document.getElementById('countdown-number');
const $crisisBanner= document.getElementById('crisis-banner');
const $fileModal   = document.getElementById('file-modal');
const $modalBg     = document.getElementById('modal-backdrop');
const $modalFile   = document.getElementById('modal-filename');
const $modalCode   = document.getElementById('modal-code');
const $modalDl     = document.getElementById('modal-download-btn');
const $modalClose  = document.getElementById('modal-close-btn');

/* ── Speed buttons ── */
document.querySelectorAll('.speed-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.speed-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const s = parseFloat(btn.dataset.s);
    liveState.speed = s;
    fetch('/api/speed', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ multiplier: s }) });
  });
});

$ppBtn.addEventListener('click', () => {
  if (liveState.paused) {
    fetch('/api/resume', { method: 'POST' });
    liveState.paused = false;
    $ppBtn.textContent = '⏸ PAUSE';
    $ppBtn.classList.remove('paused');
  } else {
    fetch('/api/pause', { method: 'POST' });
    liveState.paused = true;
    $ppBtn.textContent = '▶ RESUME';
    $ppBtn.classList.add('paused');
  }
});

$crisisBtn.addEventListener('click', () => {
  fetch('/api/inject-crisis', { method: 'POST' });
});

const $customerBtn   = document.getElementById('customer-btn');
const $customerModal = document.getElementById('customer-modal');
const $customerClose = document.getElementById('customer-modal-close');
const $customerBg    = document.getElementById('customer-modal-backdrop');
const $customerInput = document.getElementById('customer-feedback-input');
const $customerSend  = document.getElementById('customer-send-btn');

$customerBtn.addEventListener('click', () => {
  $customerModal.hidden = false;
  $customerInput.focus();
});

function closeCustomerModal() { $customerModal.hidden = true; }
$customerClose.addEventListener('click', closeCustomerModal);
$customerBg.addEventListener('click', closeCustomerModal);

$customerSend.addEventListener('click', () => {
  const msg = $customerInput.value.trim();
  if (!msg) return;
  fetch('/api/customer-feedback', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: msg }),
  });
  $customerInput.value = '';
  closeCustomerModal();
});

$exportBtn.addEventListener('click', exportZip);
$modalBg.addEventListener('click', closeModal);
$modalClose.addEventListener('click', closeModal);

/* ── New Mission — stop server session then go home ── */
function stopAndReset() {
  const $iframe = document.getElementById('preview-iframe');
  if ($iframe) $iframe.src = 'about:blank';

  if (liveState.timerInterval) { clearInterval(liveState.timerInterval); liveState.timerInterval = null; }
  if (liveState.sse) { liveState.sse.close(); liveState.sse = null; }

  // Reset live state so next session starts clean
  liveState.tokens = 0;
  liveState.files = {};
  liveState.msgCount = 0;
  liveState.startTime = null;
  liveState.paused = false;
  liveState.speed = 1;

  // Clear live UI
  if ($commFeed)   $commFeed.innerHTML = '';
  if ($fileTree)   $fileTree.innerHTML = '';
  if ($liveTokens) $liveTokens.textContent = '0';
  if ($sessionTimer) $sessionTimer.textContent = '00:00';
  if ($msgCount)   $msgCount.textContent = '0 messages';

  fetch('/api/reset', { method: 'POST' }).finally(() => resetToPhase1());
}
document.getElementById('new-mission-btn').addEventListener('click', stopAndReset);
document.getElementById('new-mission-live-btn').addEventListener('click', stopAndReset);

/* ── Continue — resume last session with optional feedback ── */
async function continueSession() {
  const $btn      = document.getElementById('continue-btn');
  const $feedback = document.getElementById('continue-feedback');
  const feedback  = $feedback ? $feedback.value.trim() : '';
  if ($btn) { $btn.disabled = true; $btn.textContent = 'RESUMING...'; }
  await fetch('/api/continue', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ apiKey: state.apiKey, feedback: feedback || null }),
  });
  if ($btn) { $btn.disabled = false; $btn.textContent = '▶ CONTINUE'; $btn.hidden = true; }
  if ($feedback) { $feedback.value = ''; $feedback.hidden = true; }
}

/* ── Preview pause toggle ── */
liveState.previewPaused = false;
function togglePreviewPause() {
  liveState.previewPaused = !liveState.previewPaused;
  const $btn = document.getElementById('preview-pause-btn');
  if ($btn) $btn.textContent = liveState.previewPaused ? '▶ RESUME PREVIEW' : '⏸ PAUSE PREVIEW';
}

/* ── Reconnect to an already-running session (after page refresh) ── */
function reconnectLiveMode(status) {
  state.brief = status.brief;
  showPhase(4);
  buildAgentDesks();
  connectSSE();
  const $iframe = document.getElementById('preview-iframe');
  if ($iframe) $iframe.src = `/preview-now?t=${Date.now()}`;
}

/* ── Start live mode ── */
async function startLiveMode() {
  showPhase(4);
  buildAgentDesks();
  connectSSE();
  await fetch('/api/start-live', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      brief: state.brief, agents: state.selectedAgents, category: state.selectedCategory,
      provider: state.llmMode, apiKey: state.apiKey,
    }),
  });
}

function connectSSE() {
  if (liveState.sse) liveState.sse.close();
  const es = new EventSource('/api/stream');
  liveState.sse = es;

  es.addEventListener('state', e => {
    const d = JSON.parse(e.data);
    liveState.tokens = d.tokens;
    liveState.startTime = d.startTime;
    liveState.paused = d.paused;
    $liveTokens.textContent = fmtNum(d.tokens);
    if (d.files?.length) {
      d.files.forEach(f => { liveState.files[f.path] = f; });
      rebuildFileTree();
    }
    // Sync pause button label to actual server state
    if (d.paused) {
      $ppBtn.textContent = '▶ RESUME'; $ppBtn.classList.add('paused');
    } else {
      $ppBtn.textContent = '⏸ PAUSE'; $ppBtn.classList.remove('paused');
    }
    startSessionTimer();
  });

  es.addEventListener('countdown', e => {
    const { count } = JSON.parse(e.data);
    $countdownOv.hidden = false;
    $countdownNo.textContent = count;
    void $countdownNo.offsetWidth;
    $countdownNo.style.animation = 'none';
    void $countdownNo.offsetWidth;
    $countdownNo.style.animation = '';
  });

  es.addEventListener('live-start', e => {
    $countdownOv.hidden = true;
    liveState.startTime = JSON.parse(e.data).startTime;
    startSessionTimer();
    const $iframe = document.getElementById('preview-iframe');
    const $status = document.getElementById('preview-status');
    const $link   = document.getElementById('preview-tab-btn');
    if ($iframe) $iframe.src = `/preview-now?t=${Date.now()}`;
    if ($status) { $status.textContent = 'LIVE'; $status.classList.add('live'); }
    if ($link)   $link.href = '/preview-now';
  });

  es.addEventListener('preview-refresh', () => {
    schedulePreviewReload();
    // Capture screenshot after preview reloads (backup — screenshot-request is primary)
    setTimeout(capturePreviewScreenshot, 3500);
  });

  // Server requests a fresh screenshot right before CEO runs — capture immediately
  es.addEventListener('screenshot-request', () => {
    capturePreviewScreenshot();
  });

  es.addEventListener('agent-status', e => {
    const { agentId, status } = JSON.parse(e.data);
    updateDeskStatus(agentId, status);
  });

  es.addEventListener('new-message', e => {
    const msg = JSON.parse(e.data);
    appendFeedMessage(msg);
    if (msg.from && msg.from !== 'system') updateDeskBubble(msg.from, msg.message);
  });

  // Live token streaming — append deltas to a single bubble per call so
  // viewers watch characters appear as Claude types them. Bubble is only
  // created on the first non-empty delta to avoid empty-cursor flicker.
  es.addEventListener('agent-stream', e => {
    const d = JSON.parse(e.data);
    if (!d.from || !d.messageId) return;
    let el = $commFeed.querySelector(`[data-stream-id="${d.messageId}"]`);
    if (d.delta) {
      if (!el) {
        const fromMeta = LIVE_AGENT_META[d.from] || { name: d.from, color: '#888', bg: 'rgba(128,128,128,0.1)', abbr: '?' };
        const pid = PORTRAIT_ID_MAP[d.from] || d.from;
        const time = new Date().toTimeString().slice(0, 8);
        el = document.createElement('div');
        el.className = 'feed-msg type-communicate g3-streaming';
        el.dataset.streamId = d.messageId;
        el.innerHTML = `
          <div class="feed-avatar-sm" style="background:${fromMeta.bg};color:${fromMeta.color};border:1px solid ${fromMeta.color}">
            <div style="width:100%;height:100%;border-radius:50%;overflow:hidden">${PORTRAITS[pid]||fromMeta.abbr}</div>
          </div>
          <div class="feed-body">
            <div class="feed-meta">
              <span class="feed-sender" style="color:${fromMeta.color}">${fromMeta.name}</span>
              <span class="feed-time">${time}</span>
            </div>
            <div class="feed-text" data-stream-text></div>
          </div>`;
        $commFeed.appendChild(el);
        liveState.msgCount++;
        $msgCount.textContent = `${liveState.msgCount} message${liveState.msgCount !== 1 ? 's' : ''}`;
      }
      const $text = el.querySelector('[data-stream-text]');
      if ($text) $text.textContent += d.delta;
      $commFeed.scrollTop = $commFeed.scrollHeight;
      if (d.from !== 'system') updateDeskBubble(d.from, d.delta);
    }
    if (d.done && el) {
      el.classList.remove('g3-streaming');
    }
  });

  es.addEventListener('new-file', e => {
    const f = JSON.parse(e.data);
    liveState.files[f.path] = f;
    rebuildFileTree();
    flashDeskFileBadge(f.agentId, f.path);
  });

  es.addEventListener('token-update', e => {
    const d = JSON.parse(e.data);
    liveState.tokens = d.total;
    $liveTokens.textContent = fmtNum(d.total);
    updateTopbarBudget(TOTAL_BUDGET - d.total);
    _liveUpdateDashboard(d);
  });

  es.addEventListener('crisis', e => {
    const { message } = JSON.parse(e.data);
    showCrisisBanner(message);
  });

  es.addEventListener('customer-feedback', e => {
    const { message } = JSON.parse(e.data);
    showCustomerBanner(message);
  });

  es.addEventListener('stopped', () => {
    const $btn      = document.getElementById('continue-btn');
    const $feedback = document.getElementById('continue-feedback');
    if ($btn)      $btn.hidden = false;
    if ($feedback) $feedback.hidden = false;
  });

  // ── Blender Studio events (forwarded from shared stream) ──
  es.addEventListener('blender-frame', e => {
    if (typeof handleBlenderFrame === 'function') handleBlenderFrame(e);
  });

  es.addEventListener('video-ready', e => {
    if (typeof handleBlenderVideoReady === 'function') handleBlenderVideoReady(e);
  });

  es.addEventListener('blender-agent-status', e => {
    if (typeof handleBlenderAgentStatus === 'function') handleBlenderAgentStatus(e);
  });

  es.onerror = () => {
    setTimeout(connectSSE, 3000);
  };
}

/* ── Agent desk cards ── */
function buildAgentDesks() {
  $agentDesks.innerHTML = '';
  Object.entries(LIVE_AGENT_META).forEach(([id, a]) => {
    const pid = PORTRAIT_ID_MAP[id] || id;
    const card = document.createElement('div');
    card.className = 'desk-card';
    card.id = `desk-${id}`;
    card.style.setProperty('--agent-color', a.color);
    card.innerHTML = `
      <div class="desk-portrait-wrap">
        <div class="desk-portrait-img" id="desk-portrait-${id}">${PORTRAITS[pid] || `<svg viewBox="0 0 72 88"><text y="56" x="36" text-anchor="middle" font-size="32" fill="${a.color}">${a.abbr[0]}</text></svg>`}</div>
        <div class="desk-status-ring" id="desk-ring-${id}"></div>
      </div>
      <div class="desk-name" style="color:${a.color}">${a.name}</div>
      <div class="desk-role">${a.abbr}</div>
      <div class="desk-state-row">
        <span class="desk-badge" id="desk-badge-${id}">IDLE</span>
        <span class="desk-typing" id="desk-typing-${id}"><span></span><span></span><span></span></span>
      </div>
      <div class="desk-bubble" id="desk-bubble-${id}">Standing by...</div>
      <div class="desk-file-badge" id="desk-file-${id}"></div>`;

    card.addEventListener('mousemove', e => {
      const r = card.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width  - 0.5;
      const y = (e.clientY - r.top)  / r.height - 0.5;
      card.style.transform = `perspective(520px) rotateY(${x * 14}deg) rotateX(${-y * 10}deg) scale(1.04)`;
    });
    card.addEventListener('mouseleave', () => { card.style.transform = ''; });

    $agentDesks.appendChild(card);
  });
}

function updateDeskStatus(agentId, status) {
  const card  = document.getElementById(`desk-${agentId}`);
  const badge = document.getElementById(`desk-badge-${agentId}`);
  if (!card) return;
  const labels = { idle:'IDLE', thinking:'THINKING', working:'WORKING', talking:'TALKING' };
  card.className = `desk-card status-${status}`;
  card.style.setProperty('--agent-color', LIVE_AGENT_META[agentId]?.color || '#00e676');
  if (badge) badge.textContent = labels[status] || status.toUpperCase();
}

function updateDeskBubble(agentId, message) {
  const el = document.getElementById(`desk-bubble-${agentId}`);
  if (el) el.textContent = message.replace(/`/g, '').slice(0, 120);
}

function flashDeskFileBadge(agentId, filePath) {
  const el = document.getElementById(`desk-file-${agentId}`);
  if (!el) return;
  el.textContent = `📄 ${filePath.split('/').pop()}`;
  el.classList.add('visible');
  setTimeout(() => el.classList.remove('visible'), 6000);
}

/* ── Comm feed ── */
// ── Live cost + speed dashboard ─────────────────────────────────────────
const LIVE_RATES = {
  'claude-sonnet-4-6':   { in: 3.00, cache_w: 3.75, cache_r: 0.30, out: 15.00 },
  'claude-sonnet-4-5':   { in: 3.00, cache_w: 3.75, cache_r: 0.30, out: 15.00 },
  'claude-opus-4-7':     { in: 15.00, cache_w: 18.75, cache_r: 1.50, out: 75.00 },
  'claude-opus-4-6':     { in: 15.00, cache_w: 18.75, cache_r: 1.50, out: 75.00 },
  'claude-haiku-4-5':    { in: 0.80, cache_w: 1.00, cache_r: 0.08, out: 4.00 },
};
const _LIVE_DEFAULT_RATE = LIVE_RATES['claude-sonnet-4-6'];
const _liveTpsWindow = [];

function _liveFormatCost(usd) {
  if (usd < 0.01) return '$' + usd.toFixed(4);
  if (usd < 1)    return '$' + usd.toFixed(3);
  return '$' + usd.toFixed(2);
}

function _liveUpdateDashboard(d) {
  const $cost  = document.getElementById('live-cost');
  const $cache = document.getElementById('live-cache');
  const $tps   = document.getElementById('live-tps');
  const usage  = d.totalUsage;

  if ($cost && usage) {
    const r = LIVE_RATES[d.model] || _LIVE_DEFAULT_RATE;
    const cost =
      (usage.raw_input    || 0) * r.in       / 1e6 +
      (usage.cache_create || 0) * r.cache_w  / 1e6 +
      (usage.cache_read   || 0) * r.cache_r  / 1e6 +
      (usage.output       || 0) * r.out      / 1e6;
    $cost.textContent = _liveFormatCost(cost);
  }
  if ($cache && usage) {
    const total = (usage.raw_input || 0) + (usage.cache_create || 0) + (usage.cache_read || 0);
    const rate = total > 0 ? (usage.cache_read || 0) / total : 0;
    $cache.textContent = total > 0 ? Math.round(rate * 100) + '%' : '—';
  }
  if ($tps && d.delta) {
    const now = Date.now();
    _liveTpsWindow.push({ t: now, tokens: d.delta });
    const cutoff = now - 5000;
    while (_liveTpsWindow.length && _liveTpsWindow[0].t < cutoff) _liveTpsWindow.shift();
    if (_liveTpsWindow.length >= 2) {
      const span = (now - _liveTpsWindow[0].t) / 1000;
      const sum = _liveTpsWindow.reduce((a, e) => a + e.tokens, 0);
      const tps = span > 0 ? Math.round(sum / span) : 0;
      $tps.textContent = tps.toLocaleString();
    }
  }
}

function appendFeedMessage(msg) {
  liveState.msgCount++;
  $msgCount.textContent = `${liveState.msgCount} message${liveState.msgCount !== 1 ? 's' : ''}`;

  const el = document.createElement('div');
  const time = new Date(msg.timestamp).toTimeString().slice(0, 8);

  if (msg.type === 'system') {
    el.className = 'feed-msg type-system';
    el.innerHTML = `<div class="feed-system-msg">${escHtml(msg.message)}</div>`;
  } else if (msg.type === 'crisis') {
    el.className = 'feed-msg type-crisis';
    el.innerHTML = `<div class="feed-crisis-msg">${escHtml(msg.message)}</div>`;
  } else {
    const fromMeta = LIVE_AGENT_META[msg.from] || { name: msg.from, color: '#888', bg: 'rgba(128,128,128,0.1)', abbr: '?' };
    const pid = PORTRAIT_ID_MAP[msg.from] || msg.from;
    const toMeta = msg.to ? LIVE_AGENT_META[msg.to] : null;
    const isFile = msg.type === 'file';

    el.className = `feed-msg ${isFile ? 'type-file' : 'type-' + msg.type}`;
    el.innerHTML = `
      <div class="feed-avatar-sm" style="background:${fromMeta.bg};color:${fromMeta.color};border:1px solid ${fromMeta.color}">
        <div style="width:100%;height:100%;border-radius:50%;overflow:hidden">${PORTRAITS[pid]||fromMeta.abbr}</div>
      </div>
      <div class="feed-body">
        <div class="feed-meta">
          <span class="feed-sender" style="color:${fromMeta.color}">${fromMeta.name}</span>
          ${toMeta ? `<span class="feed-arrow">→</span><span class="feed-target" style="color:${toMeta.color}">${toMeta.name}</span>` : ''}
          <span class="feed-time">${time}</span>
        </div>
        <div class="feed-text">${formatFeedText(msg.message)}</div>
      </div>`;
  }

  $commFeed.appendChild(el);
  while ($commFeed.children.length > 80) $commFeed.removeChild($commFeed.firstChild);
  $commFeed.scrollTop = $commFeed.scrollHeight;
}

function formatFeedText(txt) {
  return escHtml(txt).replace(/`([^`]+)`/g, '<code>$1</code>');
}

/* ── File tree ── */
function rebuildFileTree() {
  const folders = {};
  Object.values(liveState.files).forEach(f => {
    const parts = f.path.split('/');
    const folder = parts.length > 1 ? parts[0] : 'root';
    const name   = parts[parts.length - 1];
    if (!folders[folder]) folders[folder] = [];
    folders[folder].push({ ...f, name });
  });

  $fileTree.innerHTML = '';

  const icons = { js:'📄', ts:'📄', html:'🎨', css:'🎨', md:'📝', json:'📋', txt:'📄' };
  const folderIcons = { src:'⚙️', design:'🎨', docs:'📝', tests:'🧪', sales:'💼', root:'📁' };

  Object.entries(folders).sort().forEach(([folder, files]) => {
    const fdiv = document.createElement('div');
    fdiv.className = 'file-folder';
    fdiv.innerHTML = `<div class="folder-name"><span class="folder-icon">${folderIcons[folder]||'📁'}</span>${folder}/</div>`;

    files.sort((a, b) => b.ts - a.ts).forEach(f => {
      const ext  = f.name.split('.').pop() || '';
      const icon = icons[ext] || '📄';
      const ago  = timeAgo(f.ts);
      const item = document.createElement('div');
      item.className = 'file-item';
      item.innerHTML = `
        <span class="file-icon">${icon}</span>
        <div class="file-info">
          <div class="file-name">${f.name}</div>
          <div class="file-meta">${f.lines} lines · ${ago}</div>
        </div>
        <button class="file-dl-btn" title="Download">⬇</button>`;
      item.addEventListener('click', e => {
        if (e.target.classList.contains('file-dl-btn')) { downloadFile(f); return; }
        previewFile(f);
      });
      fdiv.appendChild(item);
    });

    $fileTree.appendChild(fdiv);
  });
}

/* ── File preview modal ── */
async function previewFile(f) {
  $modalFile.textContent = f.path;
  $modalCode.textContent = 'Loading...';
  $modalCode.removeAttribute('data-highlighted');
  $fileModal.hidden = false;
  document.body.style.overflow = 'hidden';

  if (!f.content) {
    try {
      const res = await fetch(`/api/file?path=${encodeURIComponent(f.path)}`);
      const data = await res.json();
      f.content = data.content || '';
      liveState.files[f.path] = { ...liveState.files[f.path], content: f.content };
    } catch (e) {
      f.content = '// Could not load file content';
    }
  }

  $modalCode.textContent = f.content;
  $modalCode.removeAttribute('data-highlighted');
  if (window.hljs) {
    $modalCode.className = '';
    hljs.highlightElement($modalCode);
  }
  $modalDl.onclick = () => downloadFile(f);
}

function closeModal() {
  $fileModal.hidden = true;
  document.body.style.overflow = '';
}

/* ── File download ── */
function downloadFile(f) {
  const blob = new Blob([f.content], { type: 'text/plain' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href = url;
  a.download = f.name || f.path.split('/').pop();
  a.click();
  URL.revokeObjectURL(url);
}

/* ── Export all as ZIP ── */
async function exportZip() {
  if (!window.JSZip || !Object.keys(liveState.files).length) return;
  $exportBtn.textContent = '⏳ ZIPPING...';
  const zip = new JSZip();
  Object.values(liveState.files).forEach(f => zip.file(f.path, f.content));
  const blob = await zip.generateAsync({ type: 'blob' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href = url; a.download = `warroom-export-${Date.now()}.zip`; a.click();
  URL.revokeObjectURL(url);
  $exportBtn.textContent = '⬇ EXPORT ZIP';
}

/* ── Crisis banner ── */
function showCrisisBanner(message) {
  $crisisBanner.textContent = message;
  $crisisBanner.className = 'crisis-banner';
  $crisisBanner.hidden = false;
  setTimeout(() => { $crisisBanner.hidden = true; }, 8000);
}

/* ── Customer feedback banner ── */
function showCustomerBanner(message) {
  $crisisBanner.textContent = `👤 CUSTOMER: ${message}`;
  $crisisBanner.className = 'crisis-banner customer-banner';
  $crisisBanner.hidden = false;
  setTimeout(() => { $crisisBanner.hidden = true; }, 10000);
}

/* ── Preview panel ── */
let _previewRefreshTimer = null;

function reloadPreview() {
  const $iframe = document.getElementById('preview-iframe');
  const $status = document.getElementById('preview-status');
  const $link   = document.getElementById('preview-tab-btn');
  if (!$iframe) return;
  const url = `/preview-now?t=${Date.now()}`;
  $iframe.src = url;
  if ($status) { $status.textContent = 'LIVE'; $status.classList.add('live'); }
  if ($link)   $link.href = '/preview/';

  // After iframe loads, intercept console errors and send to server
  $iframe.onload = () => {
    const errors = [];
    try {
      const iwin = $iframe.contentWindow;
      if (!iwin) return;

      // Intercept errors
      iwin.onerror = (msg, src, line, col) => {
        errors.push(`JS Error: ${msg} (line ${line}:${col})`);
        sendConsoleErrors(errors);
        return false;
      };

      // Intercept console.error and console.warn
      const origError = iwin.console.error.bind(iwin.console);
      const origWarn  = iwin.console.warn.bind(iwin.console);
      iwin.console.error = (...args) => {
        errors.push(`console.error: ${args.join(' ')}`);
        sendConsoleErrors(errors);
        origError(...args);
      };
      iwin.console.warn = (...args) => {
        errors.push(`console.warn: ${args.join(' ')}`);
        origWarn(...args);
      };

      // Intercept unhandled promise rejections
      iwin.addEventListener('unhandledrejection', e => {
        errors.push(`Unhandled Promise: ${e.reason}`);
        sendConsoleErrors(errors);
      });
    } catch { /* cross-origin safety */ }
  };
}

function sendConsoleErrors(errors) {
  if (!errors.length) return;
  const unique = [...new Set(errors)].slice(0, 10);
  fetch('/api/console-errors', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ errors: unique }),
  }).catch(() => {});
}

function schedulePreviewReload() {
  if (liveState.previewPaused) return;
  if (_previewRefreshTimer) clearTimeout(_previewRefreshTimer);
  _previewRefreshTimer = setTimeout(() => {
    _previewRefreshTimer = null;
    if (!liveState.previewPaused) reloadPreview();
  }, 800);
}

/* ── Capture iframe screenshot and send to server ── */
async function capturePreviewScreenshot() {
  try {
    const iframe = document.getElementById('preview-iframe');
    if (!iframe || !iframe.contentDocument || !iframe.contentDocument.body) return;
    if (typeof html2canvas === 'undefined') return;
    const canvas = await html2canvas(iframe.contentDocument.body, {
      backgroundColor: '#07090f', scale: 0.5,
      width: 900, height: 600, windowWidth: 900, windowHeight: 600,
      logging: false, useCORS: true,
    });
    const base64 = canvas.toDataURL('image/jpeg', 0.7).split(',')[1];
    fetch('/api/preview-screenshot', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ base64, mediaType: 'image/jpeg' }),
    });
  } catch (e) { /* silent */ }
}

/* ── Session timer ── */
function startSessionTimer() {
  if (liveState.timerInterval) clearInterval(liveState.timerInterval);
  liveState.timerInterval = setInterval(() => {
    if (!liveState.startTime) return;
    const s = Math.floor((Date.now() - liveState.startTime) / 1000);
    const h = String(Math.floor(s / 3600)).padStart(2, '0');
    const m = String(Math.floor((s % 3600) / 60)).padStart(2, '0');
    const sec = String(s % 60).padStart(2, '0');
    $sessionTimer.textContent = `${h}:${m}:${sec}`;
  }, 1000);
}
