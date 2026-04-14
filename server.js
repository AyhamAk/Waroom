/* ══════════════════════════════════════════════
   WAR ROOM — SERVER (Express routes)
   All HTTP/SSE endpoints. Logic lives in
   pipeline.js (live loop) and prompts.js (agent prompts).
   ══════════════════════════════════════════════ */

require('dotenv').config();
const express = require('express');
const path = require('path');
const fs = require('fs');

const {
  live, setLive,
  LIVE_AGENTS, sleep,
  emit, pushContext, pushMsg, stopAll,
  callAgent, runPipeline, scheduleSide,
  addClient, removeClient,
} = require('./pipeline');

const { streamMessage, getModels } = require('./llm');

const app = express();
app.use(express.json({ limit: '4mb' }));
app.use(express.static(path.join(__dirname, 'public')));

/* ── /preview-now — animated loading screen or inlined real site ── */
app.get('/preview-now', (req, res) => {
  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store');

  const loadingScreen = (sub) => `<!DOCTYPE html><html><head><meta charset="UTF-8"><style>
    *{margin:0;padding:0;box-sizing:border-box}
    body{background:#07090f;color:#00e676;font-family:'Share Tech Mono','Courier New',monospace;display:flex;align-items:center;justify-content:center;height:100vh;overflow:hidden}
    .w{text-align:center}
    .ic{font-size:2.5rem;margin-bottom:1.2rem;animation:pulse 2s ease-in-out infinite}
    .tt{font-size:.95rem;letter-spacing:.15em;margin-bottom:1.5rem}
    .bt{width:220px;height:2px;background:#0d1420;margin:0 auto .75rem;border-radius:1px}
    .bf{height:100%;background:#00e676;border-radius:1px;animation:ld 2.5s ease-in-out infinite;transform-origin:left}
    .sb{font-size:.62rem;color:#2d4a3a;letter-spacing:.1em}
    @keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}
    @keyframes ld{0%{width:0}60%{width:85%}100%{width:100%}}
  </style></head><body><div class="w">
    <div class="ic">⚡</div>
    <div class="tt">AGENTS DEPLOYING...</div>
    <div class="bt"><div class="bf"></div></div>
    <div class="sb">${sub}</div>
  </div><script>setTimeout(()=>location.reload(),3000)</script></body></html>`;

  if (!live.workspaceDir) return res.send(loadingScreen('AWAITING MISSION BRIEF'));
  const indexFile = path.join(live.workspaceDir, 'public', 'index.html');
  if (!fs.existsSync(indexFile)) return res.send(loadingScreen('CYCLE 1 IN PROGRESS'));
  let html = fs.readFileSync(indexFile, 'utf8');

  // Rewrite all relative asset URLs to /preview/... so they resolve correctly
  // from within the iframe, regardless of the parent page's URL.
  // This avoids inlining JS into <script> tags entirely — which was causing
  // SyntaxError when generated JS contained </script> inside strings or templates.
  html = html.replace(
    /((?:src|href)=["'])(?!https?:|\/\/|\/|data:|#)([^"']*)(["'])/gi,
    '$1/preview/$2$3'
  );

  // Inject auto-reload
  const reloadScript = '<script>setTimeout(function(){location.reload()},5000)</script>';

  if (!/<html[\s>]/i.test(html)) {
    // Bare HTML fragment — wrap in a full document with asset references
    html = `<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Preview</title><link rel="stylesheet" href="/preview/style.css"></head><body>\n${html}\n<script src="/preview/data.js"></script>\n<script src="/preview/app.js"></script>\n${reloadScript}\n</body></html>`;
  } else {
    html = html.includes('</body>')
      ? html.replace('</body>', reloadScript + '</body>')
      : html + reloadScript;
  }

  res.send(html);
});

/* ── /preview/* — direct file access (export, open in tab) ── */
app.use('/preview', (req, res) => {
  if (!live.workspaceDir) return res.status(404).send('No active session');
  const rel  = (req.path === '/' || req.path === '') ? 'index.html' : req.path.replace(/^\//, '').split('?')[0];
  const file = path.join(live.workspaceDir, 'public', rel);
  if (!fs.existsSync(file)) return res.status(404).send('File not found: ' + rel);
  const ext  = (rel.split('.').pop() || '').toLowerCase();
  const mime = { html:'text/html', js:'text/javascript', css:'text/css', json:'application/json' }[ext] || 'text/plain';
  res.setHeader('Content-Type', mime + '; charset=utf-8');
  res.send(fs.readFileSync(file, 'utf8'));
});

/* ══════════════════════════════════════════════
   PLANNING CHAIN (phases 1-3)
   ══════════════════════════════════════════════ */
app.post('/api/run-agent', async (req, res) => {
  const { systemPrompt, context, maxTokens, provider = 'anthropic', apiKey } = req.body;
  if (!systemPrompt || !context) return res.status(400).json({ error: 'Missing fields' });
  if (!apiKey) return res.status(400).json({ error: 'API key required' });

  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.setHeader('X-Accel-Buffering', 'no');
  res.flushHeaders();

  const send = obj => res.write(`data: ${JSON.stringify(obj)}\n\n`);
  try {
    const model = getModels(provider).fast;
    const { inputTokens, outputTokens } = await streamMessage({
      provider, apiKey, model,
      maxTokens: maxTokens || 1000,
      system: systemPrompt,
      messages: [{ role: 'user', content: context }],
      onText: text => send({ type: 'text', text }),
    });
    send({ type: 'done', inputTokens, outputTokens });
  } catch (err) {
    send({ type: 'error', message: err.message });
  } finally {
    res.end();
  }
});

/* ══════════════════════════════════════════════
   LIVE MODE: SSE + control endpoints
   ══════════════════════════════════════════════ */

/* Status — used by client on page load to detect a running session */
app.get('/api/status', (req, res) => {
  res.json({
    running: live.running,
    brief: live.brief || '',
    tokens: live.tokens || 0,
    category: live.category || 'tech-startup',
    agents: live.agents || [],
  });
});

/* SSE stream */
app.get('/api/stream', (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.setHeader('X-Accel-Buffering', 'no');
  res.flushHeaders();
  addClient(res);

  const pl = require('./pipeline').live;
  res.write(`event: state\ndata: ${JSON.stringify({
    running: pl.running, paused: pl.paused, speed: pl.speed,
    tokens: pl.tokens, startTime: pl.startTime,
    files: pl.files, brief: pl.brief, cycle: pl.cycle || 0,
  })}\n\n`);

  req.on('close', () => removeClient(res));
});

/* Store console errors from preview iframe */
app.post('/api/console-errors', (req, res) => {
  const { errors } = req.body;
  if (Array.isArray(errors) && errors.length) {
    live.consoleErrors = errors;
  }
  res.json({ ok: true });
});

/* Store preview screenshot from client */
app.post('/api/preview-screenshot', (req, res) => {
  const { base64, mediaType } = req.body;
  if (base64) live.previewScreenshot = { base64, mediaType: mediaType || 'image/png' };
  res.json({ ok: true });
});

/* Start live */
app.post('/api/start-live', (req, res) => {
  const { brief, agents: rawAgents, category, provider = 'anthropic', apiKey } = req.body;
  if (!brief) return res.status(400).json({ error: 'brief required' });
  if (!apiKey) return res.status(400).json({ error: 'API key required' });

  const ID_MAP = { pm: 'ceo', cto: 'ceo', 'junior-dev': 'builder', 'lead-dev': 'builder' };
  const agents = Array.isArray(rawAgents)
    ? [...new Set(rawAgents.map(id => ID_MAP[id] || id))]
    : Object.keys(LIVE_AGENTS);
  console.log('[start-live] selected agents (normalized):', agents);

  stopAll();
  const sessionId = Date.now().toString();
  const wsDir = path.join(__dirname, 'workspace', sessionId);
  // Only create directories actually needed — no React/TS scaffold that confuses agents
  ['docs', 'public', 'logs'].forEach(d => fs.mkdirSync(path.join(wsDir, d), { recursive: true }));

  setLive({
    running: true, paused: false, speed: 1,
    brief, sessionId, workspaceDir: wsDir,
    category: category || 'tech-startup',
    provider: provider || 'anthropic',
    apiKey,
    agents: Array.isArray(agents) ? agents : Object.keys(LIVE_AGENTS),
    contexts: {}, timers: {}, tokens: 0,
    startTime: Date.now(), clients: require('./pipeline').live.clients,
    files: [], salesV: 1, msgCount: 0, cycle: 0, pastPriorities: [],
    previewScreenshot: null, consoleErrors: [],
  });

  res.json({ ok: true, sessionId });

  (async () => {
    for (let i = 3; i >= 1; i--) {
      emit('countdown', { count: i });
      await sleep(1000);
    }
    emit('live-start', { startTime: live.startTime });
    pushMsg({ from: 'system', to: null, type: 'system',
      message: `🟢 STARTUP IS LIVE — pipeline starting` });
    Object.keys(LIVE_AGENTS).forEach(id => emit('agent-status', { agentId: id, status: 'idle' }));
    runPipeline();
  })();
});

/* Stop / new mission */
app.post('/api/stop', (req, res) => {
  stopAll();
  live.running = false;
  live.workspaceDir = null;
  live.brief = '';
  emit('stopped', {});
  res.json({ ok: true });
});

/* Pause */
app.post('/api/pause', (req, res) => {
  live.paused = true;
  emit('paused', {});
  res.json({ ok: true });
});

/* Resume */
app.post('/api/resume', (req, res) => {
  live.paused = false;
  emit('resumed', {});
  res.json({ ok: true });
});

/* Speed */
app.post('/api/speed', (req, res) => {
  live.speed = parseFloat(req.body.multiplier) || 1;
  emit('speed-change', { speed: live.speed });
  res.json({ ok: true });
});

/* Customer feedback */
app.post('/api/customer-feedback', (req, res) => {
  const { message } = req.body;
  if (!message || !message.trim()) return res.status(400).json({ error: 'empty' });
  const text = message.trim().slice(0, 400);
  live.customerFeedback = text;
  pushContext('ceo', 'CUSTOMER FEEDBACK', text);
  emit('customer-feedback', { message: text });
  pushMsg({ from: 'system', to: 'ceo', type: 'customer', message: `👤 CUSTOMER: ${text}` });

  live._feedbackPending = true;

  if (live.timers['pipeline']) {
    // Waiting between cycles — cancel the gap and fire immediately
    clearTimeout(live.timers['pipeline']);
    live.timers['pipeline'] = null;
    pushMsg({ from: 'system', to: null, type: 'system', message: `⚡ FEEDBACK RECEIVED — CEO acting now` });
    runPipeline();
  } else {
    // Mid-cycle (builder running) — current cycle will finish then immediately start next with feedback
    pushMsg({ from: 'system', to: null, type: 'system', message: `⚡ FEEDBACK RECEIVED — CEO acts as soon as builder finishes` });
  }

  res.json({ ok: true });
});

/* Inject crisis */
app.post('/api/inject-crisis', (req, res) => {
  const crises = [
    '🚨 Competitor just launched an identical product with $10M in VC funding!',
    '🔥 PRODUCTION IS DOWN — 500 errors, all users affected. Fix NOW.',
    '💔 Our top enterprise client just churned — $60k ARR gone overnight.',
    '📰 TechCrunch published a negative piece on our data privacy practices.',
    '💸 Runway is 6 weeks. Investor meeting fell through this morning.',
    '⚠️ Critical SQL injection vulnerability found in our auth system.',
    '🎯 Y Combinator just reached out — application deadline in 24 hours!',
    '📉 App Store removed our app for guideline violation. Resubmission needed.',
  ];
  const crisis = crises[Math.floor(Math.random() * crises.length)];
  pushContext('ceo', 'CRISIS ALERT', crisis);
  emit('crisis', { message: crisis });
  pushMsg({ from: 'system', to: 'ceo', type: 'crisis', message: `🚨 CRISIS: ${crisis}` });

  clearTimeout(live.timers['ceo']);
  live.timers['ceo'] = setTimeout(() => callAgent('ceo'), 800);
  res.json({ ok: true, crisis });
});

/* Get file content */
app.get('/api/file', (req, res) => {
  const p = (req.query.path || '').replace(/\.\./g, '');
  if (!p || !live.workspaceDir) return res.status(404).json({ error: 'not found' });
  const full = path.join(live.workspaceDir, p);
  if (!fs.existsSync(full)) return res.status(404).json({ error: 'not found' });
  res.json({ content: fs.readFileSync(full, 'utf8'), path: p });
});

/* List all files */
app.get('/api/files', (_req, res) => {
  res.json({ files: live.files });
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`\n  WAR ROOM online → http://localhost:${PORT}\n`));
