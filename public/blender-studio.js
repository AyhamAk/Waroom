/* ══════════════════════════════════════════════
   WAR ROOM — BLENDER STUDIO
   Mode switching, input form, SSE events,
   render preview, agent status panel.
   Depends on: data.js, state.js, utils.js, app.js
   ══════════════════════════════════════════════ */

/* ── API key helper — reads from same inputs as game studio ── */
function _getApiKey() {
  // Blender Studio's own key field takes priority
  const bsKey = document.getElementById('bs-api-key');
  if (bsKey && bsKey.value.trim()) return bsKey.value.trim();
  // Fall back to game studio state
  if (typeof state !== 'undefined' && state.apiKey) return state.apiKey;
  // Fall back to game studio key inputs
  const el = document.getElementById('key-anthropic') || document.getElementById('key-gemini');
  return el ? el.value.trim() : '';
}

/* ── Blender Studio state ── */
const blenderState = {
  active: false,           // is Blender Studio the current UI mode?
  selectedStyle: 'commercial',
  uploadedImageBase64: null,
  frameCount: 0,
  startTime: null,
  timerInterval: null,
  sse: null,               // shares phase4 SSE or owns its own when in BS mode
};

/* ── Blender agent definitions ── */
const BLENDER_AGENTS = [
  { id: 'director_3d',       icon: '🎬', name: 'DIRECTOR',   role: 'Scene Vision & Direction',       color: '#c084fc' },
  { id: 'scene_architect_3d',icon: '🏛️', name: 'ARCHITECT',  role: 'Scene Layout & Camera Setup',    color: '#60a5fa' },
  { id: 'blender_artist',    icon: '🎨', name: '3D ARTIST',  role: 'Materials, Lighting & Assets',   color: '#f0abfc' },
  { id: 'animator_3d',       icon: '🎭', name: 'ANIMATOR',   role: 'Keyframes & Motion',             color: '#fbbf24' },
  { id: 'renderer_3d',       icon: '🖥️', name: 'RENDERER',   role: 'Final Render & Compositing',     color: '#34d399' },
];

/* ══════════════════════════════════════════════
   MODE SWITCHING
   ══════════════════════════════════════════════ */

/**
 * Switch between 'game' and 'blender' studio modes.
 * In Game mode  — shows the normal phase flow (phase-1 through phase-4).
 * In Blender mode — hides all phases, shows #blender-studio.
 */
function switchStudioMode(mode) {
  const isBlender = mode === 'blender';
  const isGame3d  = mode === 'game3d';
  const isGame    = mode === 'game';
  blenderState.active = isBlender;

  // Tab UI
  document.getElementById('tab-game-studio').classList.toggle('active', isGame);
  document.getElementById('tab-blender-studio').classList.toggle('active', isBlender);
  const $g3tab = document.getElementById('tab-game3d-studio');
  if ($g3tab) $g3tab.classList.toggle('active', isGame3d);

  // Phase indicators in topbar — only meaningful for legacy Game Studio
  const $phaseIndicators = document.getElementById('phase-indicators');
  if ($phaseIndicators) $phaseIndicators.style.display = isGame ? '' : 'none';

  // Studio sections
  const $bs = document.getElementById('blender-studio');
  const $g3 = document.getElementById('game3d-studio');
  if ($bs) $bs.hidden = !isBlender;
  if ($g3) $g3.hidden = !isGame3d;

  if (isGame) {
    showPhase(state.currentPhase || 1);
  } else {
    // Hide all phases while in any non-game-studio mode
    document.querySelectorAll('.phase').forEach(el => el.classList.remove('active'));
  }

  // Lazy-init the 3D game studio UI on first switch.
  if (isGame3d && typeof game3dInit === 'function') {
    game3dInit();
  }
}

/* ══════════════════════════════════════════════
   AGENT STATUS PANEL — BUILD
   ══════════════════════════════════════════════ */

function buildBlenderAgentDesks() {
  const $container = document.getElementById('bs-agent-desks');
  if (!$container) return;
  $container.innerHTML = '';

  BLENDER_AGENTS.forEach(agent => {
    const row = document.createElement('div');
    row.className = 'bs-agent-row';
    row.id = `bs-agent-${agent.id}`;
    row.style.setProperty('--bs-agent-color', agent.color);

    row.innerHTML = `
      <div class="bs-agent-icon">${agent.icon}</div>
      <div class="bs-agent-info">
        <div class="bs-agent-name" style="color:${agent.color}">${agent.name}</div>
        <div class="bs-agent-role">${agent.role}</div>
        <div class="bs-agent-msg" id="bs-agent-msg-${agent.id}">Standing by...</div>
      </div>
      <div class="bs-agent-badge" id="bs-agent-badge-${agent.id}">IDLE</div>
      <div class="bs-agent-typing" id="bs-agent-typing-${agent.id}">
        <span></span><span></span><span></span>
      </div>`;

    $container.appendChild(row);
  });
}

/**
 * Update a specific Blender agent's status indicator.
 * Status values mirror the game studio: idle, thinking, working, talking.
 */
function updateBlenderAgentStatus(agentId, status, message) {
  // Normalise: backend uses hyphens ("director-3d"), DOM uses underscores ("director_3d")
  const normId = agentId.replace(/-/g, '_');
  const row   = document.getElementById(`bs-agent-${normId}`) || document.getElementById(`bs-agent-${agentId}`);
  const badge = document.getElementById(`bs-agent-badge-${normId}`) || document.getElementById(`bs-agent-badge-${agentId}`);
  const msg   = document.getElementById(`bs-agent-msg-${normId}`) || document.getElementById(`bs-agent-msg-${agentId}`);

  if (!row) return;

  const labels = { idle: 'IDLE', thinking: 'THINKING', working: 'WORKING', talking: 'TALKING', rendering: 'RENDERING' };
  const statusClass = status === 'rendering' ? 'status-working' : `status-${status}`;

  // Strip any previous status classes
  row.className = 'bs-agent-row ' + statusClass;

  if (badge) badge.textContent = labels[status] || status.toUpperCase();
  if (msg && message) msg.textContent = String(message).slice(0, 100);
}

/* ══════════════════════════════════════════════
   IMAGE UPLOAD
   ══════════════════════════════════════════════ */

function initBlenderDropzone() {
  const $zone      = document.getElementById('bs-dropzone');
  const $inner     = document.getElementById('bs-dropzone-inner');
  const $fileInput = document.getElementById('bs-file-input');
  const $thumb     = document.getElementById('bs-thumb');
  const $clearBtn  = document.getElementById('bs-thumb-clear');

  if (!$zone) return;

  // Click opens file picker
  $zone.addEventListener('click', e => {
    if (e.target === $clearBtn || $clearBtn.contains(e.target)) return;
    $fileInput.click();
  });

  // Keyboard accessibility
  $zone.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $fileInput.click(); }
  });

  $fileInput.addEventListener('change', () => {
    if ($fileInput.files && $fileInput.files[0]) {
      handleBlenderImageFile($fileInput.files[0]);
    }
  });

  // Drag & drop
  $zone.addEventListener('dragover', e => {
    e.preventDefault();
    $zone.classList.add('dragover');
  });

  $zone.addEventListener('dragleave', e => {
    if (!$zone.contains(e.relatedTarget)) $zone.classList.remove('dragover');
  });

  $zone.addEventListener('drop', e => {
    e.preventDefault();
    $zone.classList.remove('dragover');
    const file = e.dataTransfer.files && e.dataTransfer.files[0];
    if (file && file.type.startsWith('image/')) handleBlenderImageFile(file);
  });

  // Clear button
  $clearBtn.addEventListener('click', e => {
    e.stopPropagation();
    clearBlenderImage();
  });
}

function handleBlenderImageFile(file) {
  if (file.size > 10 * 1024 * 1024) {
    alert('Image must be under 10 MB.');
    return;
  }

  const reader = new FileReader();
  reader.onload = ev => {
    const dataUrl = ev.target.result;
    // Strip the "data:image/...;base64," prefix for the API
    blenderState.uploadedImageBase64 = dataUrl.split(',')[1] || null;

    const $thumb     = document.getElementById('bs-thumb');
    const $inner     = document.getElementById('bs-dropzone-inner');
    const $clearBtn  = document.getElementById('bs-thumb-clear');

    if ($thumb) { $thumb.src = dataUrl; $thumb.hidden = false; }
    if ($inner)    $inner.hidden = true;
    if ($clearBtn) $clearBtn.hidden = false;
  };
  reader.readAsDataURL(file);
}

function clearBlenderImage() {
  blenderState.uploadedImageBase64 = null;

  const $thumb    = document.getElementById('bs-thumb');
  const $inner    = document.getElementById('bs-dropzone-inner');
  const $clearBtn = document.getElementById('bs-thumb-clear');
  const $fileInput= document.getElementById('bs-file-input');

  if ($thumb)    { $thumb.src = ''; $thumb.hidden = true; }
  if ($inner)    $inner.hidden = false;
  if ($clearBtn) $clearBtn.hidden = true;
  if ($fileInput) $fileInput.value = '';
}

/* ══════════════════════════════════════════════
   STYLE PICKER
   ══════════════════════════════════════════════ */

function initBlenderStylePicker() {
  const $grid = document.getElementById('bs-style-grid');
  if (!$grid) return;

  $grid.querySelectorAll('.bs-style-card').forEach(card => {
    card.addEventListener('click', () => {
      $grid.querySelectorAll('.bs-style-card').forEach(c => {
        c.classList.remove('selected');
        c.setAttribute('aria-pressed', 'false');
      });
      card.classList.add('selected');
      card.setAttribute('aria-pressed', 'true');
      blenderState.selectedStyle = card.dataset.style;
    });

    // Keyboard: Space/Enter to select
    card.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); card.click(); }
    });
  });
}

/* ══════════════════════════════════════════════
   DEPLOY
   ══════════════════════════════════════════════ */

async function startBlenderStudio() {
  const $desc   = document.getElementById('blender-description');
  const $btn    = document.getElementById('bs-deploy-btn');
  const $status = document.getElementById('bs-render-status');

  const desc = $desc ? $desc.value.trim() : '';
  if (!desc) {
    $desc && $desc.focus();
    return;
  }

  // Disable button during request
  if ($btn) { $btn.disabled = true; $btn.innerHTML = '<span class="deploy-icon">⏳</span> DEPLOYING AGENTS...'; }
  if ($status) { $status.textContent = 'DEPLOYING...'; $status.classList.add('active'); }

  // Show idle pulsing state
  setBlenderIdleMessage('AGENTS BUILDING YOUR SCENE...');
  showBlenderIdleState();

  // Reset frame counter
  blenderState.frameCount = 0;
  const $frameCounter = document.getElementById('bs-frame-counter');
  if ($frameCounter) $frameCounter.textContent = '—';

  // Start session timer
  blenderState.startTime = Date.now();
  startBlenderTimer();

  // Reset all agents to idle
  BLENDER_AGENTS.forEach(a => updateBlenderAgentStatus(a.id, 'idle', 'Initialising...'));

  try {
    const resp = await fetch('/api/blender/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        productDescription: desc,
        style:    blenderState.selectedStyle,
        imageBase64: blenderState.uploadedImageBase64 || null,
        apiKey:   _getApiKey(),
      }),
    });

    if (!resp.ok) throw new Error(`Server returned ${resp.status}`);

    // Connect SSE to listen for Blender events
    connectBlenderSSE();

  } catch (err) {
    console.error('[Blender Studio] Deploy error:', err);
    if ($btn) { $btn.disabled = false; $btn.innerHTML = '<span class="deploy-icon">🎬</span> BUILD SCENE'; }
    if ($status) { $status.textContent = 'ERROR — RETRY'; $status.classList.remove('active'); }
    setBlenderIdleMessage('DEPLOYMENT FAILED — CHECK CONSOLE');
  }
}

/* ══════════════════════════════════════════════
   SSE — Blender Studio events
   ══════════════════════════════════════════════ */

/**
 * Connect (or reuse) an SSE stream that listens for Blender Studio events.
 * The server can emit on /api/stream (same endpoint as game studio) — Blender
 * events are simply distinguished by their event type names.
 */
function connectBlenderSSE() {
  // Reuse an existing SSE connection if phase4's connectSSE already opened one,
  // otherwise open a fresh one.  We attach our handlers to liveState.sse if it
  // exists, otherwise we create our own under blenderState.sse.
  let es = (typeof liveState !== 'undefined' && liveState.sse) ? liveState.sse : null;

  if (!es) {
    if (blenderState.sse) blenderState.sse.close();
    es = new EventSource('/api/stream');
    blenderState.sse = es;

    es.onerror = () => {
      setTimeout(() => { if (blenderState.active) connectBlenderSSE(); }, 3000);
    };
  }

  es.addEventListener('blender-frame',        handleBlenderFrame);
  es.addEventListener('video-ready',          handleBlenderVideoReady);
  es.addEventListener('blender-agent-status', handleBlenderAgentStatus);
  // Backend emits generic agent-status — catch it too
  es.addEventListener('agent-status',         handleBlenderAgentStatus);
  es.addEventListener('blender-start',        handleBlenderStart);
  es.addEventListener('blender-done',         handleBlenderDone);
  es.addEventListener('blender-error',        handleBlenderErrorEvent);
  es.addEventListener('new-message',          handleBlenderMessage);
}

function disconnectBlenderSSE() {
  // Only close if we own the SSE connection (not shared with phase 4)
  if (blenderState.sse) {
    blenderState.sse.removeEventListener('blender-frame', handleBlenderFrame);
    blenderState.sse.removeEventListener('video-ready',   handleBlenderVideoReady);
    blenderState.sse.removeEventListener('blender-agent-status', handleBlenderAgentStatus);
    blenderState.sse.close();
    blenderState.sse = null;
  }
}

function handleBlenderFrame(e) {
  try {
    const d = JSON.parse(e.data);
    const renderUrl = d.renderUrl || d.url;
    if (!renderUrl) return;

    blenderState.frameCount++;

    const $img          = document.getElementById('bs-render-img');
    const $idleState    = document.getElementById('bs-idle-state');
    const $frameCounter = document.getElementById('bs-frame-counter');
    const $previewLabel = document.getElementById('bs-preview-label');
    const $status       = document.getElementById('bs-render-status');

    // Show render image, hide idle
    if ($idleState) $idleState.hidden = true;
    if ($img) {
      $img.src = renderUrl;
      $img.hidden = false;
    }

    if ($frameCounter) $frameCounter.textContent = String(blenderState.frameCount);
    if ($previewLabel) $previewLabel.textContent = `frame ${blenderState.frameCount}`;
    if ($status) { $status.textContent = 'RENDERING'; $status.classList.add('active'); }
  } catch (err) {
    console.error('[Blender Studio] blender-frame parse error:', err);
  }
}

function handleBlenderVideoReady(e) {
  try {
    const { videoUrl } = JSON.parse(e.data);

    const $overlay     = document.getElementById('bs-video-overlay');
    const $dlBtn       = document.getElementById('bs-video-dl-btn');
    const $topDlBtn    = document.getElementById('bs-download-btn');
    const $status      = document.getElementById('bs-render-status');
    const $previewLabel= document.getElementById('bs-preview-label');

    if ($overlay) $overlay.hidden = false;

    if (videoUrl) {
      if ($dlBtn)    { $dlBtn.href = videoUrl; $dlBtn.hidden = false; }
      if ($topDlBtn) { $topDlBtn.href = videoUrl; $topDlBtn.hidden = false; }
    }

    if ($status) { $status.textContent = 'COMPLETE'; $status.classList.remove('active'); $status.classList.add('complete'); }
    if ($previewLabel) $previewLabel.textContent = 'scene complete';

    // Mark all agents idle
    BLENDER_AGENTS.forEach(a => updateBlenderAgentStatus(a.id, 'idle', 'Done.'));

    stopBlenderTimer();

    // Re-enable deploy button
    const $btn = document.getElementById('bs-deploy-btn');
    if ($btn) { $btn.disabled = false; $btn.innerHTML = '<span class="deploy-icon">🎬</span> BUILD SCENE'; }

  } catch (err) {
    console.error('[Blender Studio] video-ready parse error:', err);
  }
}

function handleBlenderAgentStatus(e) {
  try {
    const { agentId, status, message } = JSON.parse(e.data);
    updateBlenderAgentStatus(agentId, status, message || '');
    if (status === 'thinking' || status === 'working') {
      _bsLogAppend(`◈ ${agentId} → ${status}`, 'bs-log-sys');
    }
  } catch (err) {}
}

function handleBlenderStart(e) {
  const $btn = document.getElementById('bs-deploy-btn');
  const $status = document.getElementById('bs-render-status');
  if ($btn) { $btn.disabled = true; $btn.innerHTML = '<span class="deploy-icon">⚙️</span> BUILDING...'; }
  if ($status) { $status.textContent = 'RUNNING'; $status.classList.add('active'); }
  _bsLogAppend('🟢 Pipeline started', 'bs-log-ok');
}

function handleBlenderDone(e) {
  const $btn = document.getElementById('bs-deploy-btn');
  const $status = document.getElementById('bs-render-status');
  if ($btn) { $btn.disabled = false; $btn.innerHTML = '<span class="deploy-icon">🎬</span> BUILD SCENE'; }
  if ($status) { $status.textContent = 'DONE'; $status.classList.remove('active'); }
  stopBlenderTimer();
}

function handleBlenderErrorEvent(e) {
  try {
    const { message } = JSON.parse(e.data);
    const $btn = document.getElementById('bs-deploy-btn');
    const $status = document.getElementById('bs-render-status');
    if ($btn) { $btn.disabled = false; $btn.innerHTML = '<span class="deploy-icon">🎬</span> BUILD SCENE'; }
    if ($status) { $status.textContent = 'ERROR'; $status.classList.remove('active'); }
    setBlenderIdleMessage('⚠️ ' + (message || 'Pipeline error — check console'));
    stopBlenderTimer();
  } catch (_) {}
}

function handleBlenderMessage(e) {
  if (!blenderState.active) return;
  try {
    const { from, message, type } = JSON.parse(e.data);
    if (!message) return;
    const isError = message.includes('API error') || message.includes('⚠️') || message.includes('error');
    const isTool  = message.includes('🔧') || message.includes('↩');
    const isOk    = message.includes('✅') || message.includes('RENDER_OK');
    const cls = isError ? 'bs-log-err' : isTool ? 'bs-log-tool' : isOk ? 'bs-log-ok' : 'bs-log-msg';
    const prefix = from ? `[${from}] ` : '';
    _bsLogAppend(prefix + message.slice(0, 200), cls);

    if (isError && message.includes('API error')) {
      setBlenderIdleMessage('⚠️ ' + message.slice(0, 120));
      const $btn = document.getElementById('bs-deploy-btn');
      if ($btn) { $btn.disabled = false; $btn.innerHTML = '<span class="deploy-icon">🎬</span> BUILD SCENE'; }
    }
  } catch (_) {}
}

function _bsLogAppend(text, cls = 'bs-log-msg') {
  const feed = document.getElementById('bs-log-feed');
  if (!feed) return;
  // Clear "Waiting..." placeholder on first real message
  if (feed.children.length === 1 && feed.children[0].classList.contains('bs-log-sys')) {
    feed.innerHTML = '';
  }
  const el = document.createElement('div');
  el.className = 'bs-log-entry ' + cls;
  el.textContent = text;
  feed.appendChild(el);
  // Cap at 200 entries
  while (feed.children.length > 200) feed.removeChild(feed.firstChild);
  feed.scrollTop = feed.scrollHeight;
}

/* ══════════════════════════════════════════════
   PREVIEW HELPERS
   ══════════════════════════════════════════════ */

function showBlenderIdleState() {
  const $idle    = document.getElementById('bs-idle-state');
  const $img     = document.getElementById('bs-render-img');
  const $overlay = document.getElementById('bs-video-overlay');
  if ($idle)    $idle.hidden = false;
  if ($img)     $img.hidden = true;
  if ($overlay) $overlay.hidden = true;
}

function setBlenderIdleMessage(msg) {
  const $el = document.getElementById('bs-idle-msg');
  if ($el) $el.textContent = msg;
}

/* ══════════════════════════════════════════════
   RESET
   ══════════════════════════════════════════════ */

function blenderStudioReset() {
  // Stop SSE
  disconnectBlenderSSE();
  stopBlenderTimer();

  // Reset UI to idle
  blenderState.frameCount = 0;
  blenderState.uploadedImageBase64 = null;
  blenderState.startTime = null;

  const $desc         = document.getElementById('blender-description');
  const $btn          = document.getElementById('bs-deploy-btn');
  const $status       = document.getElementById('bs-render-status');
  const $frameCounter = document.getElementById('bs-frame-counter');
  const $previewLabel = document.getElementById('bs-preview-label');
  const $topDlBtn     = document.getElementById('bs-download-btn');
  const $timer        = document.getElementById('bs-timer');

  if ($desc)         $desc.value = '';
  if ($btn)          { $btn.disabled = false; $btn.innerHTML = '<span class="deploy-icon">🎬</span> BUILD SCENE'; }
  if ($status)       { $status.textContent = 'STANDBY'; $status.classList.remove('active', 'complete'); }
  if ($frameCounter) $frameCounter.textContent = '—';
  if ($previewLabel) $previewLabel.textContent = 'no render yet';
  if ($topDlBtn)     $topDlBtn.hidden = true;
  if ($timer)        $timer.textContent = '00:00:00';

  // Reset style picker to commercial
  const $grid = document.getElementById('bs-style-grid');
  if ($grid) {
    $grid.querySelectorAll('.bs-style-card').forEach(c => {
      const isCommercial = c.dataset.style === 'commercial';
      c.classList.toggle('selected', isCommercial);
      c.setAttribute('aria-pressed', isCommercial ? 'true' : 'false');
    });
  }
  blenderState.selectedStyle = 'commercial';

  // Clear image
  clearBlenderImage();

  // Reset agents
  BLENDER_AGENTS.forEach(a => updateBlenderAgentStatus(a.id, 'idle', 'Standing by...'));

  // Reset idle state
  setBlenderIdleMessage('AGENTS BUILDING YOUR SCENE...');
  showBlenderIdleState();

  // Update the idle sub-text to original
  const $idleSub = document.querySelector('#bs-idle-state .bs-idle-sub');
  if ($idleSub) $idleSub.textContent = 'Submit a brief to begin rendering';
}

/* ══════════════════════════════════════════════
   SESSION TIMER
   ══════════════════════════════════════════════ */

function startBlenderTimer() {
  stopBlenderTimer();
  blenderState.timerInterval = setInterval(() => {
    if (!blenderState.startTime) return;
    const s   = Math.floor((Date.now() - blenderState.startTime) / 1000);
    const h   = String(Math.floor(s / 3600)).padStart(2, '0');
    const m   = String(Math.floor((s % 3600) / 60)).padStart(2, '0');
    const sec = String(s % 60).padStart(2, '0');
    const $el = document.getElementById('bs-timer');
    if ($el) $el.textContent = `${h}:${m}:${sec}`;
  }, 1000);
}

function stopBlenderTimer() {
  if (blenderState.timerInterval) {
    clearInterval(blenderState.timerInterval);
    blenderState.timerInterval = null;
  }
}

/* ══════════════════════════════════════════════
   INIT — runs after DOM is ready
   ══════════════════════════════════════════════ */

(function initBlenderStudio() {
  buildBlenderAgentDesks();
  initBlenderDropzone();
  initBlenderStylePicker();
})();
