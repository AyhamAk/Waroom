/* ══════════════════════════════════════════════
   WAR ROOM — LIVE PIPELINE
   Agent definitions, live state, SSE helpers,
   callAgent, runPipeline, scheduleSide.
   ══════════════════════════════════════════════ */

require('dotenv').config();
const path = require('path');
const fs = require('fs');
const vm = require('vm');
const { spawn } = require('child_process');

// Sucrase: real TypeScript → JavaScript transpiler (permanent TS fix)
let sucraseTransform = null;
try { sucraseTransform = require('sucrase').transform; } catch { /* optional dep */ }

/* ── Auto-close truncated JS ──
   When the builder hits a token limit mid-IIFE, the file ends without closing
   braces/parens. Try progressively more closing tokens until vm.Script passes. */
function autoCloseJS(code) {
  if (!code || !code.trim()) return code;
  const attempts = [
    '', '\n}', '\n}\n}', '\n}\n}\n}', '\n}\n}\n}\n}',
    '\n})();', '\n}\n})();', '\n}\n}\n})();', '\n}\n}\n}\n})();',
    '\n  }\n})();', '\n    }\n  }\n})();',
  ];
  for (const closer of attempts) {
    try { new (require('vm').Script)(code + closer); return code + closer; } catch {}
  }
  return code; // return unchanged if nothing works
}
const { buildPrompt } = require('./prompts');
const { createMessage, getModels } = require('./llm');
const { validateJS, retryBuilderFile } = require('./tools/validator');
const { resolveCDNs } = require('./tools/cdnResolver');
const { webSearch, buildSearchQuery } = require('./tools/search');

const sleep = ms => new Promise(r => setTimeout(r, ms));

/* ── Agent logger ── */
function writeAgentLog(agentId, cycle, promptText, rawResponse, inputTokens, outputTokens) {
  if (!live.workspaceDir) return;
  try {
    const logDir = path.join(live.workspaceDir, 'logs');
    fs.mkdirSync(logDir, { recursive: true });
    const logFile = path.join(logDir, 'session.log');
    const ts = new Date().toISOString().replace('T', ' ').slice(0, 19);
    const divider = '═'.repeat(60);
    const entry = [
      `\n${divider}`,
      `CYCLE ${cycle} | ${(LIVE_AGENTS[agentId]?.name || agentId).toUpperCase()} | ${ts}`,
      `TOKENS: ${inputTokens} in / ${outputTokens} out`,
      divider,
      '── PROMPT ──',
      promptText,
      '',
      '── RESPONSE ──',
      rawResponse,
      '',
    ].join('\n');
    fs.appendFileSync(logFile, entry, 'utf8');
  } catch { /* logging is non-critical */ }
}

/* ── Agent definitions ── */
const LIVE_AGENTS = {
  ceo: {
    name: 'CEO', abbr: 'CEO', role: 'Chief Executive',
    color: '#00e676', maxTokens: 800,
    communicatesWith: ['lead-eng'],
  },
  'lead-eng': {
    name: 'Lead Engineer', abbr: 'LE', role: 'Lead Engineer',
    color: '#4fc3f7', maxTokens: 2000,
    communicatesWith: ['builder'],
  },
  designer: {
    name: 'UI Designer', abbr: 'UID', role: 'UI Designer',
    color: '#ce93d8', maxTokens: 800,
    communicatesWith: ['builder'],
  },
  builder: {
    name: 'Developer', abbr: 'DEV', role: 'Full-Stack Developer',
    color: '#ffb74d', maxTokens: 4000,
    communicatesWith: [],
  },
  qa: {
    name: 'QA Engineer', abbr: 'QA', role: 'QA Engineer',
    color: '#80cbc4', maxTokens: 400,
    communicatesWith: ['lead-eng'],
  },
  'backend-eng': {
    name: 'Backend Engineer', abbr: 'BE', role: 'Backend Engineer',
    color: '#a5d6a7', maxTokens: 6000,
    communicatesWith: ['builder'],
  },
  sales: {
    name: 'Sales Lead', abbr: 'SL', role: 'Sales Lead',
    color: '#f06292', maxTokens: 600,
    communicatesWith: ['ceo'],
  },
};

/* ── Live state ── */
let live = {
  running: false,
  paused: false,
  speed: 1,
  brief: '',
  sessionId: null,
  workspaceDir: null,
  contexts: {},
  timers: {},
  tokens: 0,
  startTime: null,
  clients: [],
  files: [],
  salesV: 1,
  msgCount: 0,
  pastPriorities: [],
  featurePriority: '',
};

/* ── SSE helpers ── */
function emit(event, data) {
  const chunk = `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
  live.clients = live.clients.filter(c => {
    try { c.write(chunk); return true; } catch { return false; }
  });
}

function pushContext(agentId, fromLabel, text) {
  if (!live.contexts[agentId]) live.contexts[agentId] = [];
  live.contexts[agentId].push(`${fromLabel}: ${text}`);
  if (live.contexts[agentId].length > 6) live.contexts[agentId].shift();
}

function pushMsg(msg) {
  live.msgCount++;
  emit('new-message', { ...msg, id: live.msgCount, timestamp: Date.now() });
}

function stopAll() {
  Object.values(live.timers).forEach(t => clearTimeout(t));
  live.timers = {};
}

/* ── Backend child-process management ── */
let _backendProc = null;

function killBackend() {
  if (_backendProc) { try { _backendProc.kill('SIGTERM'); } catch {} _backendProc = null; }
  live.backendPort = null;
}

async function spawnBackend(wsDir) {
  const apiDir    = path.join(wsDir, 'api');
  const serverJs  = path.join(apiDir, 'server.js');
  if (!fs.existsSync(serverJs)) return;
  if (_backendProc) return; // already running

  // Validate server.js before spawning — truncated files crash Node immediately
  const serverCode = fs.readFileSync(serverJs, 'utf8');
  const { valid, error } = validateJS(serverCode);
  if (!valid) {
    const healed = autoCloseJS(serverCode);
    if (validateJS(healed).valid) {
      fs.writeFileSync(serverJs, healed, 'utf8');
      pushMsg({ from: 'system', to: null, type: 'system',
        message: `🩹 api/server.js: auto-closed truncated braces before spawn` });
    } else {
      pushMsg({ from: 'system', to: null, type: 'system',
        message: `⚠️ api/server.js has syntax errors (${error.slice(0, 80)}) — backend not spawned` });
      return;
    }
  }

  _backendProc = spawn('node', ['server.js'], {
    cwd: apiDir,
    env: { ...process.env, PORT: '3001' },
    stdio: 'pipe',
  });
  _backendProc.stderr.on('data', d => {
    const m = d.toString().trim();
    if (m) console.error('[backend]', m);
  });
  _backendProc.on('exit', code => {
    _backendProc = null;
    live.backendPort = null;
    if (live.running) pushMsg({ from: 'system', to: null, type: 'system', message: `⚠️ Backend exited (code ${code})` });
  });
  await sleep(800); // give node a moment to start
  live.backendPort = 3001;
  emit('backend-ready', { port: 3001 });
  pushMsg({ from: 'system', to: null, type: 'system', message: `🚀 Real backend running on :3001 — APIs live` });
}

/* ── Post-build validator: auto-generate any missing required files ── */
async function ensureRequiredFiles() {
  if (!live.running || !live.workspaceDir) return;

  // Always require index.html, style.css, app.js. data.js is generated by builder — not auto-patched.
  const required = ['public/index.html', 'public/style.css', 'public/app.js'];
  const missing = required.filter(p => !live.files.find(f => f.path === p));
  if (!missing.length) return;

  const provider  = live.provider || 'anthropic';
  const apiKey    = live.apiKey   || process.env.ANTHROPIC_API_KEY;
  const model     = getModels(provider).smart;

  // Give the LLM context of what was already built
  const builtCtx = live.files
    .filter(f => f.path.startsWith('public/'))
    .map(f => `=== ${f.path} (${f.lines} lines) ===\n${(f.content || '').slice(0, 600)}`)
    .join('\n\n') || '(no files built yet)';

  for (const filename of missing) {
    pushMsg({ from: 'system', to: null, type: 'system',
      message: `⚠️ ${filename} missing after builder — auto-generating...` });

    const hasDataJs = live.files.some(f => f.path === 'public/data.js');
    const designSpec = (() => { try { return fs.readFileSync(path.join(live.workspaceDir, 'docs/design-spec.md'), 'utf8').slice(0, 800); } catch { return ''; } })();
    const hint = filename.endsWith('.html')
      ? `Complete HTML page. Must include <link rel="stylesheet" href="style.css">${hasDataJs ? ', <script src="data.js"></script>' : ''} and <script src="app.js"></script>. Use element IDs that match the JavaScript above.`
      : filename.endsWith('.css')
      ? `Complete production stylesheet. Extract every element ID and class from the index.html above and style ALL of them. Use CSS custom properties (--variables) for colors. Dark theme. Make it look polished — proper spacing, card shadows, typography, color-coded values, smooth transitions. ${designSpec ? `\nDESIGN SPEC:\n${designSpec}` : ''}`
      : `Complete JavaScript. Target the element IDs in index.html above.${hasDataJs ? ' State and simulation already live in data.js — app.js handles DOM updates, rendering, and events only.' : ' Implement all interactive features from the project brief.'} No stubs.`;

    const prompt = `You are a developer fixing an incomplete build.

PROJECT: ${live.brief}
FEATURE: ${live.featurePriority || 'build complete app'}

FILES ALREADY BUILT:
${builtCtx}

The file "${filename}" was NOT generated. You MUST output it now.
${hint}

Respond in this EXACT format only — no other text:
TYPE: work
FILENAME: ${filename}
TASK: generate missing file
---
[complete file content here]`;

    try {
      const { text: raw, inputTokens, outputTokens } = await createMessage({
        provider, apiKey, model, maxTokens: 6000,
        messages: [{ role: 'user', content: prompt }],
      });
      live.tokens += inputTokens + outputTokens;
      emit('token-update', { total: live.tokens, delta: inputTokens + outputTokens });

      const sepM = raw.match(/\n-{3,}\r?\n/);
      const filecontent = sepM ? raw.slice(raw.indexOf(sepM[0]) + sepM[0].length).trim() : raw.trim();
      if (!filecontent) continue;

      // CDN resolve if HTML
      const content = filename.endsWith('.html') ? resolveCDNs(filecontent) : filecontent;
      const safePath = filename;
      const fullPath = path.join(live.workspaceDir, safePath);
      fs.mkdirSync(path.dirname(fullPath), { recursive: true });
      fs.writeFileSync(fullPath, content, 'utf8');
      const lines = content.split('\n').length;
      const entry = { path: safePath, content, agentId: 'builder', ts: Date.now(), lines };
      const idx = live.files.findIndex(f => f.path === safePath);
      if (idx >= 0) live.files[idx] = entry; else live.files.push(entry);
      emit('new-file', entry);
      emit('preview-refresh', { path: safePath, ts: Date.now() });
      pushMsg({ from: 'builder', to: null, type: 'file',
        message: `📄 \`${safePath}\` — ${lines} lines · auto-generated (was missing)` });
    } catch (err) {
      pushMsg({ from: 'system', to: null, type: 'system',
        message: `⚠️ Could not generate ${filename}: ${err.message.slice(0, 80)}` });
    }
  }
}

/* ── CSS Specialist: dedicated call that generates perfect CSS from the actual HTML ──
   Called after every cycle 1 builder run. Reads the HTML already on disk, extracts
   every ID/class, and writes a COMPLETE stylesheet targeting exactly those selectors.
   This is separate from ensureCSSCoverage (which patches when coverage < 60%) — this
   one runs unconditionally on cycle 1 to guarantee CSS quality from the start.        */
async function runCSSSpecialist() {
  if (!live.running || !live.workspaceDir) return;

  const htmlPath = path.join(live.workspaceDir, 'public/index.html');
  if (!fs.existsSync(htmlPath)) return;

  const html = fs.readFileSync(htmlPath, 'utf8');
  const cleanHtml = html.replace(/<script[\s\S]*?<\/script>/gi, '').replace(/<style[\s\S]*?<\/style>/gi, '');

  // Extract all unique IDs and classes
  const ids      = [...new Set([...cleanHtml.matchAll(/\bid="([^"]+)"/g)].map(m => m[1]))];
  const classes  = [...new Set([...cleanHtml.matchAll(/\bclass="([^"]+)"/g)].flatMap(m => m[1].split(/\s+/)).filter(Boolean))];
  if (!ids.length && !classes.length) return;

  const designSpec = (() => { try { return fs.readFileSync(path.join(live.workspaceDir, 'docs/design-spec.md'), 'utf8').slice(0, 1200); } catch { return ''; } })();

  pushMsg({ from: 'system', to: null, type: 'system',
    message: `🎨 CSS Specialist running — writing complete stylesheet for ${ids.length} IDs + ${classes.length} classes...` });

  const provider = live.provider || 'anthropic';
  const apiKey   = live.apiKey   || process.env.ANTHROPIC_API_KEY;
  const model    = getModels(provider).smart;

  // Snapshot the cycle and the builder's cycle-1 CSS BEFORE the async LLM call.
  // If cycle 2 runs and appends new CSS while we're waiting, we'll merge rather than overwrite.
  const cycleAtStart = live.cycle;
  const cycle1BuilderCss = live._cycle1Css || '';

  const prompt = `You are an expert CSS engineer. Write a COMPLETE, production-quality stylesheet for this exact HTML page.

PROJECT: ${live.brief}

${designSpec ? `DESIGN SPEC:\n${designSpec}\n` : ''}

FULL HTML (read every element ID and class from here):
${html}

ELEMENT IDs present in the HTML: ${ids.join(', ')}
CSS CLASSES present in the HTML: ${classes.join(', ')}

REQUIREMENTS — every single one is mandatory:
1. Declare :root CSS custom properties (--bg, --surface, --accent, --text, --border, etc.)
2. Style EVERY element ID listed above — none can be missing
3. Style EVERY CSS class listed above — none can be missing
4. Dark theme with rich visual hierarchy: gradients, card shadows, subtle glows
5. Full layout: header fixed/sticky, hero section with grid, content sections with flex/grid
6. Typography scale: headings, body, labels, captions all differentiated
7. Interactive states: :hover, :active, :focus — all buttons and links
8. Smooth transitions (0.2s ease) on all interactive elements
9. Mobile responsive: @media (max-width: 768px) breakpoints for all major sections
10. Animations: at least fade-in on load, pulse on CTAs

Output ONLY plain CSS. No markdown code fences. No explanations. Start directly with :root {`;

  try {
    const { text, inputTokens, outputTokens } = await createMessage({
      provider, apiKey, model, maxTokens: 10000,
      messages: [{ role: 'user', content: prompt }],
    });
    live.tokens += inputTokens + outputTokens;
    emit('token-update', { total: live.tokens, delta: inputTokens + outputTokens });

    let css = text.trim().replace(/^```[^\n]*\n?/, '').replace(/\n?```$/, '');
    if (!css || css.length < 200) return;

    // Race-condition guard: if cycle advanced while we were waiting for the LLM,
    // cycle 2 may have already appended new CSS rules to style.css. We must
    // preserve those additions rather than overwriting them.
    const cssPath = path.join(live.workspaceDir, 'public/style.css');
    if (live.cycle !== cycleAtStart && cycle1BuilderCss) {
      const currentCss = fs.existsSync(cssPath) ? fs.readFileSync(cssPath, 'utf8') : '';
      // Extract anything appended beyond the original cycle-1 builder CSS
      const additions = currentCss.length > cycle1BuilderCss.length
        ? currentCss.slice(cycle1BuilderCss.length).trim()
        : '';
      if (additions) {
        css = css + '\n\n/* ── Cycle additions (preserved) ── */\n' + additions;
        pushMsg({ from: 'system', to: null, type: 'system',
          message: `🎨 CSS Specialist: cycle advanced during run — merged specialist + ${additions.split('\n').length} lines of new additions` });
      }
    }

    fs.writeFileSync(cssPath, css, 'utf8');

    const entry = { path: 'public/style.css', content: css, agentId: 'css-specialist', ts: Date.now(), lines: css.split('\n').length };
    const idx = live.files.findIndex(f => f.path === 'public/style.css');
    if (idx >= 0) live.files[idx] = entry; else live.files.push(entry);
    emit('new-file', entry);
    emit('preview-refresh', { path: 'public/style.css', ts: Date.now() });

    pushMsg({ from: 'system', to: null, type: 'system',
      message: `✅ CSS Specialist complete — ${css.split('\n').length} lines, all ${ids.length + classes.length} selectors covered` });
  } catch (err) {
    pushMsg({ from: 'system', to: null, type: 'system',
      message: `⚠️ CSS Specialist failed: ${err.message.slice(0, 80)}` });
  }
}

/* ── Post-build CSS coverage validator ── */
// After every cycle, extract all IDs and classes from index.html and check
// that style.css has rules for them. If major selectors are uncovered, patch
// style.css automatically with a targeted LLM call.
async function ensureCSSCoverage() {
  if (!live.running || !live.workspaceDir) return;

  const htmlPath = path.join(live.workspaceDir, 'public/index.html');
  const cssPath  = path.join(live.workspaceDir, 'public/style.css');
  if (!fs.existsSync(htmlPath) || !fs.existsSync(cssPath)) return;

  const html = fs.readFileSync(htmlPath, 'utf8');
  const css  = fs.readFileSync(cssPath,  'utf8');

  // Extract every id="..." and class="..." from HTML (skip <script> and <style> blocks)
  const cleanHtml = html.replace(/<script[\s\S]*?<\/script>/gi, '').replace(/<style[\s\S]*?<\/style>/gi, '');
  const ids      = [...cleanHtml.matchAll(/\bid="([^"]+)"/g)].map(m => '#' + m[1].trim());
  const classes  = [...cleanHtml.matchAll(/\bclass="([^"]+)"/g)]
    .flatMap(m => m[1].trim().split(/\s+/))
    .filter(Boolean)
    .map(c => '.' + c);

  const allSelectors = [...new Set([...ids, ...classes])];
  if (!allSelectors.length) return;

  // A selector is "covered" if it literally appears in the CSS (e.g. #header, .feature-card)
  const uncovered = allSelectors.filter(sel => !css.includes(sel));

  const coveragePct = Math.round(((allSelectors.length - uncovered.length) / allSelectors.length) * 100);

  // Only patch if coverage is below 60%
  if (coveragePct >= 60) return;

  pushMsg({ from: 'system', to: null, type: 'system',
    message: `⚠️ CSS coverage ${coveragePct}% (${uncovered.length}/${allSelectors.length} selectors missing) — auto-patching...` });

  const provider = live.provider || 'anthropic';
  const apiKey   = live.apiKey   || process.env.ANTHROPIC_API_KEY;
  const model    = getModels(provider).smart;

  const prompt = `You are a CSS expert. The following HTML page has selectors with NO CSS rules yet.
Write CSS ONLY for the missing selectors listed below — do not repeat rules that already exist.

HTML (for structure context):
${html.slice(0, 4000)}

EXISTING CSS THEME (match this color scheme / style exactly):
${css.slice(0, 800)}

SELECTORS THAT ARE MISSING CSS RULES (write rules for ALL of them):
${uncovered.join('\n')}

Rules:
- Output PLAIN CSS only — no markdown fences, no explanations, no comments except /* section labels */
- Match the existing dark theme and color variables
- Every selector must have at least display, color, and spacing rules
- Make the page look polished and production-ready`;

  try {
    const { text, inputTokens, outputTokens } = await createMessage({
      provider, apiKey, model, maxTokens: 4000,
      messages: [{ role: 'user', content: prompt }],
    });
    live.tokens += inputTokens + outputTokens;
    emit('token-update', { total: live.tokens, delta: inputTokens + outputTokens });

    const patch = text.trim().replace(/^```[^\n]*\n?/, '').replace(/\n?```$/, '');
    if (!patch) return;

    fs.appendFileSync(cssPath, '\n\n/* ═══ AUTO-PATCHED MISSING SELECTORS ═══ */\n' + patch, 'utf8');

    // Update live.files entry
    const newCss = fs.readFileSync(cssPath, 'utf8');
    const entry = { path: 'public/style.css', content: newCss, agentId: 'system', ts: Date.now(), lines: newCss.split('\n').length };
    const idx = live.files.findIndex(f => f.path === 'public/style.css');
    if (idx >= 0) live.files[idx] = entry; else live.files.push(entry);
    emit('new-file', entry);
    emit('preview-refresh', { path: 'public/style.css', ts: Date.now() });

    pushMsg({ from: 'system', to: null, type: 'system',
      message: `✅ CSS coverage patched — ${uncovered.length} selectors added to style.css (now ~${Math.min(100, coveragePct + Math.round(uncovered.length / allSelectors.length * 100))}% covered)` });
  } catch (err) {
    pushMsg({ from: 'system', to: null, type: 'system',
      message: `⚠️ CSS patch failed: ${err.message.slice(0, 80)}` });
  }
}

/* ── Cycle-start JS healer ──
   Before each cycle, validate existing JS files on disk. If any are invalid
   (truncated from a prior failed cycle), auto-close or LLM-repair them before
   the builder tries to append new code. Appending to a broken file = broken file. */
async function ensureValidJS() {
  if (!live.running || !live.workspaceDir) return;
  for (const rel of ['public/app.js', 'public/data.js']) {
    const fullPath = path.join(live.workspaceDir, rel);
    if (!fs.existsSync(fullPath)) continue;
    const code = fs.readFileSync(fullPath, 'utf8');
    const { valid, error } = validateJS(code);
    if (valid) continue;

    pushMsg({ from: 'system', to: null, type: 'system',
      message: `⚠️ ${rel} invalid on disk (${error.slice(0, 60)}) — healing before cycle starts...` });

    // Fast path: try auto-closing unclosed braces
    const healed = autoCloseJS(code);
    if (validateJS(healed).valid) {
      fs.writeFileSync(fullPath, healed, 'utf8');
      const idx = live.files.findIndex(f => f.path === rel);
      const entry = { path: rel, content: healed, agentId: 'system', ts: Date.now(), lines: healed.split('\n').length };
      if (idx >= 0) live.files[idx] = entry; else live.files.push(entry);
      pushMsg({ from: 'system', to: null, type: 'system', message: `🩹 ${rel}: auto-closed and healed` });
      continue;
    }

    // Slow path: LLM repair
    try {
      const provider = live.provider || 'anthropic';
      const apiKey   = live.apiKey   || process.env.ANTHROPIC_API_KEY;
      const fixed = await retryBuilderFile({
        provider, apiKey, model: getModels(provider).smart,
        brokenCode: code, error, filename: rel, context: live.brief,
      });
      if (fixed && validateJS(fixed).valid) {
        fs.writeFileSync(fullPath, fixed, 'utf8');
        const idx = live.files.findIndex(f => f.path === rel);
        const entry = { path: rel, content: fixed, agentId: 'system', ts: Date.now(), lines: fixed.split('\n').length };
        if (idx >= 0) live.files[idx] = entry; else live.files.push(entry);
        emit('new-file', entry);
        pushMsg({ from: 'system', to: null, type: 'system', message: `✅ ${rel}: LLM-healed — now valid` });
      }
    } catch { /* healer is best-effort */ }
  }
}

/* ── Feature inventory — written after each builder run ──
   Extracts function names and state keys from the built JS files and saves
   them to docs/features.json. The builder reads this on cycle 2+ to know
   what it must preserve when it rewrites app.js / data.js from scratch. */
function updateFeaturesJson() {
  if (!live.running || !live.workspaceDir) return;
  try {
    const read = p => { try { return fs.readFileSync(path.join(live.workspaceDir, p), 'utf8'); } catch { return ''; } };
    const dataJs = read('public/data.js');
    const appJs  = read('public/app.js');
    const allJs  = dataJs + '\n' + appJs;

    const functions = [...new Set(
      [...allJs.matchAll(/^(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:function|\([^)]*\)\s*=>))/gm)]
        .map(m => m[1] || m[2]).filter(Boolean)
    )].slice(0, 40);

    // Vue 3: methods written as methodName() {} inside the options object
    const vueMethods = [...new Set(
      [...allJs.matchAll(/^\s{2,}(\w+)\s*\([^)]*\)\s*\{/gm)]
        .map(m => m[1])
        .filter(n => !['data','computed','methods','mounted','created','watch','setup','beforeMount','beforeUnmount'].includes(n))
    )];

    const stateMatch = allJs.match(/const\s+state\s*=\s*\{([^}]*)\}/s);
    const stateKeys = stateMatch
      ? [...new Set([...stateMatch[1].matchAll(/(\w+)\s*:/g)].map(m => m[1]))].slice(0, 20)
      : [];

    // Vue 3: state keys from data() { return { ... } }
    const dataReturnMatch = allJs.match(/data\s*\(\s*\)\s*\{[\s\S]*?return\s*\{([^{}]+)\}/s);
    const vueDataKeys = dataReturnMatch
      ? [...new Set([...dataReturnMatch[1].matchAll(/(\w+)\s*:/g)].map(m => m[1]))].slice(0, 20)
      : [];

    const allFunctions = [...new Set([...functions, ...vueMethods])].slice(0, 40);
    const allStateKeys = vueDataKeys.length ? vueDataKeys : stateKeys;

    const featPath = path.join(live.workspaceDir, 'docs/features.json');
    fs.writeFileSync(featPath, JSON.stringify({ cycle: live.cycle || 0, functions: allFunctions, stateKeys: allStateKeys }, null, 2), 'utf8');
  } catch { /* non-critical */ }
}

/* ── Cross-cycle agent memory ──
   Written after every cycle. Every agent reads this next cycle to prevent
   regressions, avoid repeating decisions, and remember the tech stack. */
function updateAgentMemory(cycle) {
  if (!live.running || !live.workspaceDir) return;
  try {
    const read = p => { try { return fs.readFileSync(path.join(live.workspaceDir, p), 'utf8'); } catch { return ''; } };
    const existing = (() => { try { return JSON.parse(read('docs/agent-memory.json')); } catch { return {}; } })();

    const qaReport = read(`docs/qa-cycle${cycle}.md`);
    // Clear open bugs after a FIX cycle — the builder addressed them this cycle.
    // Stale bugs cause CEO to re-order fixes that are already done.
    const wasFix = (live.featurePriority || '').trim().startsWith('FIX:');
    const openBugs = wasFix ? [] : [...qaReport.matchAll(/^BROKEN:\s*(.+)/gm)].map(m => m[1].trim()).slice(0, 3);

    const filesBuilt = live.files
      .filter(f => f.path.startsWith('public/'))
      .map(f => `${f.path}(${f.lines}L)`);

    const allJs = live.files
      .filter(f => f.path.endsWith('.js') && f.path.startsWith('public/'))
      .map(f => f.content || '').join('\n');
    const jsFunctions = [...new Set(
      [...allJs.matchAll(/^(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:function|\([^)]*\)\s*=>))/gm)]
        .map(m => m[1] || m[2]).filter(Boolean)
    )].slice(0, 30);

    const memory = {
      lastCycle: cycle,
      decisions: [...(existing.decisions || []).slice(-6), live.featurePriority].filter(Boolean),
      filesBuilt,
      jsFunctions,
      openBugs,
      hasBackend: !!live.backendPort,
      category: live.category,
    };
    fs.writeFileSync(path.join(live.workspaceDir, 'docs/agent-memory.json'), JSON.stringify(memory, null, 2), 'utf8');
  } catch { /* non-critical */ }
}

/* ── Persistent live state — survives server restarts ──
   Saves/loads the minimal state needed to resume a session.
   Clients/timers/preview buffers are intentionally excluded (not serializable). */
function saveLiveState() {
  if (!live.workspaceDir) return;
  try {
    const snapshot = {
      cycle:           live.cycle || 0,
      brief:           live.brief || '',
      category:        live.category || 'tech-startup',
      provider:        live.provider || 'anthropic',
      pastPriorities:  live.pastPriorities || [],
      featurePriority: live.featurePriority || '',
      tokens:          live.tokens || 0,
      startTime:       live.startTime || null,
      agents:          live.agents || [],
      backendPort:     live.backendPort || null,
      salesV:          live.salesV || 1,
      files: (live.files || []).map(f => ({ path: f.path, lines: f.lines, ts: f.ts, agentId: f.agentId })),
    };
    fs.writeFileSync(path.join(live.workspaceDir, 'docs/live-state.json'), JSON.stringify(snapshot, null, 2), 'utf8');
  } catch { /* non-critical */ }
}

function loadLiveState(wsDir) {
  try {
    const raw = fs.readFileSync(path.join(wsDir, 'docs/live-state.json'), 'utf8');
    const s = JSON.parse(raw);
    // Re-hydrate files from disk (content not stored in snapshot to keep it small)
    const files = (s.files || []).map(f => {
      try {
        const content = fs.readFileSync(path.join(wsDir, f.path), 'utf8');
        return { ...f, content };
      } catch { return null; }
    }).filter(Boolean);
    return { ...s, files };
  } catch { return null; }
}

/* ── Core agent call (returns promise) ── */
function isConnectionError(err) {
  const msg = (err.message || '').toLowerCase();
  return msg.includes('connection') || msg.includes('network') || msg.includes('econnreset')
    || msg.includes('socket') || msg.includes('timeout') || msg.includes('enotfound')
    || err.constructor?.name === 'APIConnectionError' || err.constructor?.name === 'APIConnectionTimeoutError';
}

async function callAgent(agentId, _retries = 0) {
  if (!live.running || live.paused) return;
  const agent = LIVE_AGENTS[agentId];
  emit('agent-status', { agentId, status: 'thinking' });

  try {
    // CEO and Lead Engineer use the smart model — their decisions/specs drive everything downstream
    const usesSmart = ['builder', 'ceo', 'lead-eng'].includes(agentId);
    const provider = live.provider || 'anthropic';
    const apiKey   = live.apiKey   || process.env.ANTHROPIC_API_KEY;
    const models   = getModels(provider);
    const model    = usesSmart ? models.smart : models.fast;
    // Builder gets more tokens in FIX mode; cycle 1 is split into 2 focused phases
    const isFix    = agentId === 'builder' && (live.featurePriority || '').trim().startsWith('FIX:');
    const maxTokens = agentId === 'builder'
      ? (isFix ? 16000 : live.cycle === 1
          ? (live._buildPhase === 1 ? 12000 : 16000)   // phase 1 = HTML+CSS; phase 2 = JS
          : 10000)
      : agent.maxTokens;

    // Tool 3: Web search for CEO and lead-eng before building prompt
    let searchResults = '';
    if (['ceo', 'lead-eng'].includes(agentId) && (live.searchApiKey || process.env.SERPER_API_KEY)) {
      const query = buildSearchQuery(agentId, live);
      if (query) searchResults = await webSearch(query, live.searchApiKey);
    }

    const promptText = await buildPrompt(agentId, live, searchResults);

    // Tool 4: Vision analysis — CEO gets a structured site health report before making decisions
    let visionNote = '';
    if (agentId === 'ceo' && live.previewScreenshot) {
      try {
        const prevReport = live.lastVisionReport ? `\nPREVIOUS CYCLE REPORT: ${live.lastVisionReport.slice(0, 200)}` : '';
        const { text: visionText, inputTokens: vi, outputTokens: vo } = await createMessage({
          provider, apiKey,
          model: models.fast,    // vision description only — fast model is sufficient
          maxTokens: 700,
          messages: [{
            role: 'user',
            content: [
              { type: 'image', source: { type: 'base64', media_type: live.previewScreenshot.mediaType, data: live.previewScreenshot.base64 } },
              { type: 'text', text: `You are reviewing a screenshot of a web app being built. The project brief is: "${(live.brief || '').slice(0, 150)}"
${prevReport}

Answer each question precisely:
1. SITE STATE: BROKEN or WORKING (broken = blank/spinner/error/placeholder; working = real content visible)
2. HEALTH SCORE: 1–10 (1=blank/broken, 10=polished and complete)
3. WHAT IS VISIBLE RIGHT NOW: List every distinct UI element you can actually see (panels, charts, cards, buttons, text, colors)
4. WHAT IS MISSING or BROKEN: Compare what you see against the project brief — what key features should be visible but aren't?
5. REGRESSION: Compared to the previous cycle report above, did things improve, stay the same, or get worse?
One sentence per point. Be brutally specific — not "content area empty" but "the chart canvas is black, no price data rendered, no coin cards in the top bar".` },
            ],
          }],
        });
        live.tokens += vi + vo;
        emit('token-update', { total: live.tokens, delta: vi + vo });
        live.lastVisionReport = visionText;
        visionNote = `👁 VISION REPORT (what the site looks like RIGHT NOW):\n${visionText}\n\n`;
        // Emit to feed so user sees what the CEO sees
        pushMsg({ from: 'ceo', to: null, type: 'communicate',
          message: `👁 Site check — ${visionText.slice(0, 400)}` });
      } catch { /* vision analysis is optional, skip on error */ }
    }

    // CEO gets the screenshot embedded in vision pre-analysis above — no need to send it again.
    // Builder gets the screenshot directly so it can see what to fix.
    const useScreenshot = agentId === 'builder';
    const fullPrompt = visionNote + promptText;

    // Anthropic prompt caching: split builder prompt on \x00CACHE_SPLIT\x00 marker.
    // Static suffix (CDN hints + stack rules) is marked cacheable — saves ~1300 tokens
    // on continuation calls and repeated builds of the same category.
    const CACHE_MARKER = '\x00CACHE_SPLIT\x00\n';
    const cacheIdx = (provider === 'anthropic' && agentId === 'builder')
      ? fullPrompt.indexOf(CACHE_MARKER) : -1;

    let userContent;
    if (cacheIdx !== -1) {
      const dynamicPart = fullPrompt.slice(0, cacheIdx);
      const staticPart  = fullPrompt.slice(cacheIdx + CACHE_MARKER.length);
      const textBlocks = [
        { type: 'text', text: dynamicPart },
        { type: 'text', text: staticPart, cache_control: { type: 'ephemeral' } },
      ];
      userContent = (useScreenshot && live.previewScreenshot)
        ? [
            { type: 'image', source: { type: 'base64', media_type: live.previewScreenshot.mediaType, data: live.previewScreenshot.base64 } },
            ...textBlocks,
          ]
        : textBlocks;
    } else {
      userContent = (useScreenshot && live.previewScreenshot)
        ? [
            { type: 'image', source: { type: 'base64', media_type: live.previewScreenshot.mediaType, data: live.previewScreenshot.base64 } },
            { type: 'text', text: `This is a screenshot of the current website state.\n\n${fullPrompt}` },
          ]
        : fullPrompt;
    }

    let { text: raw, inputTokens, outputTokens } = await createMessage({
      provider, apiKey, model,
      maxTokens,
      messages: [{ role: 'user', content: userContent }],
    });

    // Truncation detection: if output hit the exact limit, the response was cut off — continue it
    if (agentId === 'builder' && outputTokens >= maxTokens - 10) {
      pushMsg({ from: 'system', to: null, type: 'system',
        message: `⚠️ DEVELOPER output truncated at ${outputTokens} tokens — continuing...` });
      try {
        const { text: cont, inputTokens: ci, outputTokens: co } = await createMessage({
          provider, apiKey, model,
          maxTokens: 6000,
          messages: [
            { role: 'user', content: userContent },
            { role: 'assistant', content: raw },
            { role: 'user', content: 'The previous response was cut off mid-file. Continue writing EXACTLY from where it stopped. Do not repeat any code already written. Do not add any explanation.' },
          ],
        });
        raw = raw + cont;
        inputTokens += ci; outputTokens = co;
        pushMsg({ from: 'system', to: null, type: 'system', message: `✅ Continuation 1 received — ${co} additional tokens` });
        // If first continuation also hit its limit, do one more pass (cycle 1 complex apps can need ~24k tokens)
        if (co >= 6000 - 10) {
          try {
            const { text: cont2, inputTokens: ci2, outputTokens: co2 } = await createMessage({
              provider, apiKey, model,
              maxTokens: 6000,
              messages: [
                { role: 'user', content: userContent },
                { role: 'assistant', content: raw },
                { role: 'user', content: 'Still not finished. Continue writing EXACTLY from where it stopped. Do not repeat any code. Do not add explanations.' },
              ],
            });
            raw = raw + cont2;
            inputTokens += ci2; outputTokens += co2;
            pushMsg({ from: 'system', to: null, type: 'system', message: `✅ Continuation 2 received — ${co2} additional tokens` });
          } catch { /* second continuation is best-effort */ }
        }
      } catch { /* continuation is best-effort */ }
    }

    live.tokens += inputTokens + outputTokens;
    emit('token-update', { total: live.tokens, delta: inputTokens + outputTokens });
    writeAgentLog(agentId, live.cycle || 0, fullPrompt, raw, inputTokens, outputTokens);

    // Parse multiple FILE blocks separated by ===FILE===
    const fileBlocks = raw.split(/\n?={3,}FILE={3,}\n?/i);
    let didWork = false;

    for (const block of fileBlocks) {
      const typeM = block.match(/^TYPE\s*:\s*(\w+)/im);
      const type  = typeM?.[1]?.toLowerCase();
      if (type === 'work') {
        const filename    = block.match(/^FILENAME\s*:\s*(.+)/im)?.[1]?.trim();
        const task        = block.match(/^TASK\s*:\s*(.+)/im)?.[1]?.trim() || '';
        const sepM        = block.match(/\n-{3,}\r?\n/);
        let filecontent = sepM ? block.slice(block.indexOf(sepM[0]) + sepM[0].length).trim() : '';
        if (!filename || !filecontent) continue;

        // Skip trivially empty JS/CSS blocks
        if (filename.endsWith('.js') || filename.endsWith('.css')) {
          const meaningful = filecontent.replace(/\/\/[^\n]*/g, '').replace(/\/\*[\s\S]*?\*\//g, '').replace(/[\s;]/g, '');
          if (!meaningful) continue;
        }

        // Strip TypeScript syntax from JS/HTML files before validation.
        // Primary: sucrase (real transpiler). Fallback: regex stripper.
        function stripTS(code) {
          if (sucraseTransform) {
            try {
              return sucraseTransform(code, { transforms: ['typescript'] }).code;
            } catch { /* fall through to regex */ }
          }
          return code
            // Remove multi-line interface declarations
            .replace(/\binterface\s+\w[\w\s,<>]*\{[^{}]*\}/g, '')
            // Remove type alias lines
            .replace(/^\s*type\s+\w[\w<>, ]*\s*=.+;?\s*$/gm, '')
            // Remove import/export type lines
            .replace(/^(?:import|export)\s+type\b.+$/gm, '')
            // Remove 'as SomeType' casts
            .replace(/\s+as\s+(?:[A-Z]\w*|string|number|boolean|any|never|void)(?:<[^>]*>)?(?:\[\])?\b/g, '')
            // Remove return type annotations: ): Type {  ): Type =>  ): Type;
            .replace(/\)\s*:\s*(?:[A-Z]\w*|string|number|boolean|any|void|never|null|undefined)(?:<[^>]*>)?(?:\[\])?\s*(?=[{;(]|=>|\s*\n)/g, ') ')
            // Remove standalone class field declarations: "  fieldName: Type;" or "  fieldName: Type\n"
            .replace(/^(\s*)(\w+)\??\s*:\s*(?:[A-Z]\w*|string|number|boolean|any|void|never|null|undefined)(?:<[^>]*>)?(?:\[\])?(\s*[;,]?\s*$)/gm, '')
            // Remove parameter/variable type annotations: name: Type followed by , ) ; = { or end of line
            .replace(/(\w+)\??\s*:\s*(?:[A-Z]\w*|string|number|boolean|any|void|never|null|undefined)(?:<[^>]*>)?(?:\[\])?\s*(?=[,);={;]|\s*\n)/g, '$1')
            // Remove generic type params on function/arrow declarations
            .replace(/(\bfunction\s+\w+)<[\w\s,extends]+>(\s*\()/g, '$1$2')
            .replace(/(<[\w\s,extends]+>)(\s*\([^)]*\)\s*(?::\s*\w+\s*)?=>)/g, '$2')
            // Remove readonly, abstract, declare
            .replace(/\b(?:readonly|abstract|declare)\s+/g, '')
            // Remove access modifiers
            .replace(/\b(?:public|private|protected)\s+(?=\w)/g, '');
        }

        if (filename.endsWith('.js')) {
          filecontent = stripTS(filecontent);
        }
        // Also strip TypeScript from inline <script> blocks in HTML
        if (filename.endsWith('.html')) {
          filecontent = filecontent.replace(
            /(<script(?:\s[^>]*)?>)([\s\S]*?)(<\/script>)/gi,
            (_, open, code, close) => open + stripTS(code) + close
          );
        }

        // Tool 1: JS Syntax Validator — validate and auto-retry on syntax error
        if ((agentId === 'builder' || agentId === 'backend-eng') && filename.endsWith('.js')) {
          const { valid, error } = validateJS(filecontent);
          if (!valid) {
            pushMsg({ from: 'system', to: null, type: 'system',
              message: `🔧 SYNTAX ERROR in ${filename} — auto-fixing: ${error.slice(0, 80)}` });
            const fixed = await retryBuilderFile({
              provider, apiKey, model,
              brokenCode: filecontent,
              error,
              filename,
              context: live.featurePriority || live.brief,
            });
            if (fixed) {
              const { valid: fixedValid } = validateJS(fixed);
              if (fixedValid) {
                filecontent = fixed;
                pushMsg({ from: 'system', to: null, type: 'system', message: `✅ SYNTAX FIXED — ${filename} rewritten successfully` });
              } else {
                pushMsg({ from: 'system', to: null, type: 'system', message: `⚠️ Could not fix syntax — skipping ${filename}` });
                continue;
              }
            } else {
              continue;
            }
          }
        }

        // Tool 2: CDN Resolver — replace guessed library URLs with real cdnjs URLs
        if (filename.endsWith('.html')) {
          filecontent = resolveCDNs(filecontent);
        }

        const safePath = filename.replace(/\.\./g, '').replace(/[^a-zA-Z0-9.\-_/]/g, '-');
        const fullPath = path.join(live.workspaceDir, safePath);
        fs.mkdirSync(path.dirname(fullPath), { recursive: true });

        // Cycles 2+: merge content into existing files
        const isBuilder = agentId === 'builder';
        const isUpdate  = (live.cycle || 1) > 1 && isBuilder && fs.existsSync(fullPath);
        const isFixCycle = (live.featurePriority || '').trim().startsWith('FIX:');

        // HTML: inject new sections — Vue apps inject inside #app div, vanilla before </body>
        if (isUpdate && safePath.startsWith('public/') && safePath.endsWith('.html') && !isFixCycle) {
          const existing = fs.readFileSync(fullPath, 'utf8');
          const isVueApp = (live.category || 'tech-startup') !== 'game-studio';
          const endAppMarker = '<!-- END APP -->';
          if (isVueApp && existing.includes(endAppMarker)) {
            filecontent = existing.replace(endAppMarker, filecontent + '\n' + endAppMarker);
          } else {
            filecontent = existing.includes('</body>')
              ? existing.replace(/<\/body>/i, '\n' + filecontent + '\n</body>')
              : existing + '\n' + filecontent;
          }
        }
        // CSS: append new rules — coexistence and override are safe for stylesheets
        if (isUpdate && safePath === 'public/style.css' && !isFixCycle) {
          const existingCss = fs.readFileSync(fullPath, 'utf8');
          filecontent = existingCss + '\n\n' + filecontent;
        }
        // app.js / data.js: always full replacement — builder outputs complete files each cycle.
        // No append = no const redeclaration, no state model freeze, no growing bloat.

        fs.writeFileSync(fullPath, filecontent, 'utf8');
        const lines = filecontent.split('\n').length;
        const entry = { path: safePath, content: filecontent, agentId, ts: Date.now(), lines };
        const idx = live.files.findIndex(f => f.path === safePath);
        if (idx >= 0) live.files[idx] = entry; else live.files.push(entry);
        // Track cycle-1 builder CSS so CSS Specialist can detect/merge any cycle-2 additions
        if (safePath === 'public/style.css' && (live.cycle || 1) === 1 && agentId === 'builder') {
          live._cycle1Css = filecontent;
        }
        if (agentId === 'sales') live.salesV++;
        if (safePath === 'docs/feature-priority.md') {
          // CEO sometimes outputs verbose markdown instead of one line.
          // Extract just the operational decision line (FIX:/NEW PAGE:/SECTION:/DONE:)
          // so that isFix detection, DONE detection, pastPriorities all work correctly.
          const decisionMatch = filecontent.match(/^(FIX:|NEW PAGE:|SECTION:|DONE:).+/m);
          if (decisionMatch) filecontent = decisionMatch[0].trim();
          live.pastPriorities.push(filecontent.slice(0, 120));
          live.featurePriority = filecontent.trim();
        }
        emit('new-file', entry);
        if (safePath.startsWith('public/')) emit('preview-refresh', { path: safePath, ts: Date.now() });
        pushMsg({ from: agentId, to: null, type: 'file',
          message: `📄 \`${safePath}\` — ${lines} lines · ${task}` });
        pushContext(agentId, agentId, `produced ${safePath}: ${task}`);
        didWork = true;
      } else if (type === 'append') {
        const filename    = block.match(/^FILENAME\s*:\s*(.+)/im)?.[1]?.trim();
        const task        = block.match(/^TASK\s*:\s*(.+)/im)?.[1]?.trim() || '';
        const sepM        = block.match(/\n-{3,}\r?\n/);
        let filecontent = sepM ? block.slice(block.indexOf(sepM[0]) + sepM[0].length).trim() : '';
        if (!filename || !filecontent) continue;

        // Skip trivially empty JS blocks
        if (filename.endsWith('.js')) {
          const meaningful = filecontent.replace(/\/\/[^\n]*/g, '').replace(/\/\*[\s\S]*?\*\//g, '').replace(/[\s;]/g, '');
          if (!meaningful) continue;
        }

        const safePath = filename.replace(/\.\./g, '').replace(/[^a-zA-Z0-9.\-_/]/g, '-');
        const fullPath = path.join(live.workspaceDir, safePath);

        // For JS files: prepend existing file so we write the merged result
        if (safePath.endsWith('.js') && fs.existsSync(fullPath)) {
          const existing = fs.readFileSync(fullPath, 'utf8');
          filecontent = existing + '\n\n/* ── Cycle ' + live.cycle + ' addition ── */\n' + filecontent;
        }

        // Validate merged JS
        if (agentId === 'builder' && safePath.endsWith('.js')) {
          const { valid, error } = validateJS(filecontent);
          if (!valid) {
            const closed = autoCloseJS(filecontent);
            if (validateJS(closed).valid) {
              filecontent = closed;
            } else {
              pushMsg({ from: 'system', to: null, type: 'system',
                message: `⚠️ Append to ${safePath} invalid — skipping: ${error.slice(0, 80)}` });
              continue;
            }
          }
        }

        fs.mkdirSync(path.dirname(fullPath), { recursive: true });
        fs.writeFileSync(fullPath, filecontent, 'utf8');
        const lines = filecontent.split('\n').length;
        const entry = { path: safePath, content: filecontent, agentId, ts: Date.now(), lines };
        const idx = live.files.findIndex(f => f.path === safePath);
        if (idx >= 0) live.files[idx] = entry; else live.files.push(entry);
        emit('new-file', entry);
        if (safePath.startsWith('public/')) emit('preview-refresh', { path: safePath, ts: Date.now() });
        pushMsg({ from: agentId, to: null, type: 'file',
          message: `📄 \`${safePath}\` — ${lines} lines · ${task} (appended)` });
        pushContext(agentId, agentId, `appended to ${safePath}: ${task}`);
        didWork = true;
      }
    }

    // Clear console errors after builder runs — they've been addressed this cycle
    if (agentId === 'builder' && live.consoleErrors?.length) {
      live.consoleErrors = [];
    }

    // Update feature inventory after every builder run so the next cycle knows
    // exactly which functions and state keys to preserve in its full rewrite.
    if (agentId === 'builder' && didWork) {
      updateFeaturesJson();

      // Micro-correction loop: test immediately after build and fix errors within the same cycle.
      // Runs up to 3 fix passes before handing off to the next cycle.
      if (live.previewPort) {
        try {
          const { testBuild } = require('./tools/tester');
          const url = `http://localhost:${live.previewPort}/preview-now`;

          for (let microPass = 0; microPass <= 3; microPass++) {
            const { errors, screenshot, skipped } = await testBuild(url);
            if (skipped) break;
            if (screenshot) live.previewScreenshot = { base64: screenshot.toString('base64'), mediaType: 'image/jpeg' };

            if (errors.length === 0) {
              live.consoleErrors = [];
              pushMsg({ from: 'system', to: null, type: 'system', message: `✅ AUTO-TEST: no console errors` });
              break;
            }

            live.consoleErrors = errors;
            if (microPass === 0) {
              pushMsg({ from: 'system', to: null, type: 'system',
                message: `🔍 AUTO-TEST: ${errors.length} error(s) found:\n${errors.slice(0, 3).map((e, i) => `  ${i + 1}. ${e}`).join('\n')}` });
            }
            if (microPass >= 3) break;

            pushMsg({ from: 'system', to: null, type: 'system',
              message: `🔧 FIX PASS ${microPass + 1}/3 — fixing ${errors.length} console error(s)` });

            const rdFile = p => { try { return fs.readFileSync(path.join(live.workspaceDir, p), 'utf8'); } catch { return ''; } };
            const currentAppJs  = rdFile('public/app.js');
            const currentDataJs = rdFile('public/data.js');
            const currentHtml   = rdFile('public/index.html');
            const htmlIds = [...currentHtml.matchAll(/id=["']([^"']+)["']/gi)].map(m => m[1]).join(', ');

            const fixPrompt = `BROWSER CONSOLE ERRORS after your last build:\n${errors.map((e, i) => `${i + 1}. ${e}`).join('\n')}\n\nCURRENT FILES ON DISK:\n=== public/app.js ===\n${currentAppJs}\n${currentDataJs ? `\n=== public/data.js ===\n${currentDataJs}\n` : ''}ELEMENT IDs in index.html: ${htmlIds}\n\nFix ALL errors. Output the COMPLETE corrected file(s):\nTYPE: work\nFILENAME: public/app.js\nTASK: fix console errors pass ${microPass + 1}\n---\n[complete corrected app.js]${currentDataJs ? '\n\n===FILE===\nTYPE: work\nFILENAME: public/data.js\nTASK: fix\n---\n[complete corrected data.js if also needed]' : ''}`;

            const fixContent = screenshot
              ? [{ type: 'image', source: { type: 'base64', media_type: 'image/jpeg', data: screenshot.toString('base64') } },
                 { type: 'text', text: fixPrompt }]
              : fixPrompt;

            try {
              const { text: fixRaw, inputTokens: fi, outputTokens: fo } = await createMessage({
                provider, apiKey, model, maxTokens: 12000,
                messages: [{ role: 'user', content: fixContent }],
              });
              live.tokens += fi + fo;
              emit('token-update', { total: live.tokens, delta: fi + fo });

              const allowedPaths = new Set(['public/app.js', 'public/data.js', 'public/index.html', 'public/style.css']);
              for (const fixBlock of fixRaw.split(/\n?={3,}FILE={3,}\n?/i)) {
                if (fixBlock.match(/^TYPE\s*:\s*(\w+)/im)?.[1]?.toLowerCase() !== 'work') continue;
                const fname = fixBlock.match(/^FILENAME\s*:\s*(.+)/im)?.[1]?.trim();
                const sepM  = fixBlock.match(/\n-{3,}\r?\n/);
                let fc = sepM ? fixBlock.slice(fixBlock.indexOf(sepM[0]) + sepM[0].length).trim() : '';
                if (!fname || !fc) continue;
                const sp = fname.replace(/\.\./g, '').replace(/[^a-zA-Z0-9.\-_/]/g, '-');
                if (!allowedPaths.has(sp)) continue;

                if (sp.endsWith('.js')) {
                  const { valid } = validateJS(fc);
                  if (!valid) {
                    const healed = autoCloseJS(fc);
                    if (validateJS(healed).valid) fc = healed; else continue;
                  }
                }
                if (sp.endsWith('.html')) fc = resolveCDNs(fc);

                const fp = path.join(live.workspaceDir, sp);
                fs.mkdirSync(path.dirname(fp), { recursive: true });
                fs.writeFileSync(fp, fc, 'utf8');
                const lines = fc.split('\n').length;
                const entry = { path: sp, content: fc, agentId: 'builder', ts: Date.now(), lines };
                const idx2 = live.files.findIndex(f => f.path === sp);
                if (idx2 >= 0) live.files[idx2] = entry; else live.files.push(entry);
                emit('new-file', entry);
                if (sp.startsWith('public/')) emit('preview-refresh', { path: sp, ts: Date.now() });
                pushMsg({ from: 'builder', to: null, type: 'file',
                  message: `📄 \`${sp}\` — ${lines} lines · fix pass ${microPass + 1}` });
              }
            } catch (fixErr) {
              pushMsg({ from: 'system', to: null, type: 'system',
                message: `⚠️ Fix pass ${microPass + 1} failed: ${fixErr.message?.slice(0, 80)}` });
              break;
            }
          }
        } catch (testerErr) {
          pushMsg({ from: 'system', to: null, type: 'system',
            message: `⚠️ Auto-tester unavailable: ${testerErr.message?.slice(0, 80)} — install playwright for self-correction` });
        }
      }
    }

    if (!didWork) {
      const talkTo  = raw.match(/^TALKTO\s*:\s*(.+)/im)?.[1]?.trim();
      const message = raw.match(/^MESSAGE\s*:\s*(.+)/im)?.[1]?.trim() || raw.slice(0, 120);
      if (talkTo && message) {
        pushContext(talkTo, agent.name, message);
        pushMsg({ from: agentId, to: talkTo, type: 'communicate', message });
        emit('agent-status', { agentId, status: 'talking' });
      } else if (agentId === 'builder') {
        pushMsg({ from: 'system', to: null, type: 'system',
          message: `⚠️ DEVELOPER produced no files (wrote explanation/tutorial instead of code). Retrying with format correction...` });
        // Builder ignored the file format — likely wrote a markdown tutorial instead.
        // Send a strict correction prompt to extract actual files.
        try {
          const { text: corrected, inputTokens: ci3, outputTokens: co3 } = await createMessage({
            provider, apiKey, model, maxTokens: 10000,
            messages: [
              { role: 'user', content: typeof userContent === 'string' ? userContent : (userContent[userContent.length - 1]?.text || '') },
              { role: 'assistant', content: raw },
              { role: 'user', content: `You wrote an explanation/tutorial instead of code files. Output the ACTUAL CODE FILES now using ONLY this format — no markdown, no explanation, no npm commands, no TypeScript, no React:\n\nTYPE: work\nFILENAME: public/index.html\nTASK: html\n---\n[complete HTML here]\n\n===FILE===\nTYPE: work\nFILENAME: public/data.js\nTASK: data\n---\n[complete vanilla JS here]\n\n===FILE===\nTYPE: work\nFILENAME: public/app.js\nTASK: app\n---\n[complete vanilla JS here]\n\n===FILE===\nTYPE: work\nFILENAME: public/style.css\nTASK: css\n---\n[complete CSS here]` },
            ],
          });
          live.tokens += ci3 + co3;
          emit('token-update', { total: live.tokens, delta: ci3 + co3 });
          // Re-parse corrected output
          const correctedBlocks = corrected.split(/\n?={3,}FILE={3,}\n?/i);
          for (const block of correctedBlocks) {
            const typeM2 = block.match(/^TYPE\s*:\s*(\w+)/im);
            if (typeM2?.[1]?.toLowerCase() !== 'work') continue;
            const fname = block.match(/^FILENAME\s*:\s*(.+)/im)?.[1]?.trim();
            const sepM2 = block.match(/\n-{3,}\r?\n/);
            let fc = sepM2 ? block.slice(block.indexOf(sepM2[0]) + sepM2[0].length).trim() : '';
            if (!fname || !fc) continue;
            if (fname.endsWith('.js')) {
              const { valid, error } = validateJS(fc);
              if (!valid) { fc = (await retryBuilderFile({ provider, apiKey, model, brokenCode: fc, error, filename: fname, context: live.brief })) || fc; }
            }
            if (fname.endsWith('.html')) fc = resolveCDNs(fc);
            const sp = fname.replace(/\.\./g, '').replace(/[^a-zA-Z0-9.\-_/]/g, '-');
            const fp = require('path').join(live.workspaceDir, sp);
            require('fs').mkdirSync(require('path').dirname(fp), { recursive: true });
            require('fs').writeFileSync(fp, fc, 'utf8');
            const lines2 = fc.split('\n').length;
            const entry2 = { path: sp, content: fc, agentId, ts: Date.now(), lines: lines2 };
            const idx2 = live.files.findIndex(f => f.path === sp);
            if (idx2 >= 0) live.files[idx2] = entry2; else live.files.push(entry2);
            emit('new-file', entry2);
            if (sp.startsWith('public/')) emit('preview-refresh', { path: sp, ts: Date.now() });
            pushMsg({ from: agentId, to: null, type: 'file', message: `📄 \`${sp}\` — ${lines2} lines · retry` });
          }
        } catch (retryErr) {
          pushMsg({ from: 'system', to: null, type: 'system', message: `⚠️ Retry also failed: ${retryErr.message?.slice(0, 80)}` });
        }
      }
    }
  } catch (err) {
    const is429 = err.status === 429
      || (err.message || '').toLowerCase().includes('rate_limit')
      || (err.message || '').toLowerCase().includes('rate limit')
      || (err.message || '').includes('429');
    const isRetryable = isConnectionError(err) || is429;
    const maxRetries = agentId === 'builder' ? 3 : 2;
    if (isRetryable && _retries < maxRetries) {
      // Rate limit: wait 60s. Connection error: exponential backoff 5s/10s/15s.
      const wait = is429 ? 60000 : ((_retries + 1) * 5000);
      const reason = is429 ? 'rate limit — waiting 60s' : `connection error — retry ${_retries + 1}/${maxRetries} in ${wait / 1000}s`;
      pushMsg({ from: 'system', to: null, type: 'system',
        message: `⚠️ ${LIVE_AGENTS[agentId]?.name || agentId} ${reason}` });
      await sleep(wait);
      return callAgent(agentId, _retries + 1);
    }
    console.error(`[${agentId}]`, err.message);
    pushMsg({ from: 'system', to: null, type: 'system',
      message: `⚠️ ${LIVE_AGENTS[agentId]?.name || agentId} error: ${err.message.slice(0, 120)}` });
  }

  emit('agent-status', { agentId, status: 'idle' });
}

async function runPipeline() {
  if (!live.running) return;
  live.cycle = (live.cycle || 0) + 1;
  const cycle = live.cycle;

  live.featurePriority = '';  // reset so previous cycle's FIX doesn't bleed in

  // Heal any JS files that got corrupted in the previous cycle before the builder rewrites them
  if (cycle > 1) await ensureValidJS();

  pushMsg({ from: 'system', to: null, type: 'system',
    message: `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━` });
  pushMsg({ from: 'system', to: null, type: 'system',
    message: `🔄 CYCLE ${cycle} — PLANNING...` });

  async function runStep(agentId) {
    while (live.paused) await sleep(500);
    if (!live.running) return;
    const name = LIVE_AGENTS[agentId]?.name.toUpperCase() || agentId;
    pushMsg({ from: 'system', to: null, type: 'system', message: `⚙️ ${name} planning...` });
    await callAgent(agentId);
  }

  // Fast-path: if customer feedback is waiting, skip planning and go straight to builder
  const isFastFeedback = !!(live.customerFeedback && live._feedbackPending);

  if (isFastFeedback) {
    pushMsg({ from: 'system', to: null, type: 'system',
      message: `⚡ CUSTOMER FEEDBACK — skipping planning, builder acting immediately` });
    while (live.paused) await sleep(500);
    await callAgent('builder');
    if (!live.running) return;
    live.customerFeedback = '';
    live._feedbackPending = false;
  } else if (cycle === 1) {
    // SOLO BUILD — split into 2 focused phases so each call is fast and precise
    live._soloMode = true;
    live.previewScreenshot = null;

    // Phase 1: HTML structure + complete CSS (~8K tokens, fast)
    // User sees the visual shell appear immediately
    live._buildPhase = 1;
    pushMsg({ from: 'system', to: null, type: 'system',
      message: `⚡ CYCLE 1 — PHASE 1/2: building HTML structure + CSS...` });
    while (live.paused) await sleep(500);
    await callAgent('builder');
    if (!live.running) return;

    // Phase 2: data.js + app.js — reads the ACTUAL HTML IDs just written (~12K tokens)
    // No ID guessing = no "getElementById returns null" bugs
    live._buildPhase = 2;
    pushMsg({ from: 'system', to: null, type: 'system',
      message: `⚡ CYCLE 1 — PHASE 2/2: building JavaScript logic...` });
    while (live.paused) await sleep(500);
    await callAgent('builder');
    if (!live.running) return;
    live._buildPhase = null;
  } else {
    // IMPROVEMENT LOOP (cycle 2+): CEO assesses, builder appends targeted feature
    if (!live.previewScreenshot) {
      pushMsg({ from: 'system', to: null, type: 'system', message: `📸 CEO reviewing site screenshot...` });
      for (let i = 0; i < 4; i++) {   // max 2s
        if (live.previewScreenshot) break;
        await sleep(500);
      }
    }

    await runStep('ceo');
    if (!live.running) return;

    // DONE detection: CEO signals the app is complete — stop the pipeline
    if ((live.featurePriority || '').trim().startsWith('DONE:')) {
      pushMsg({ from: 'system', to: null, type: 'system',
        message: `🎉 BUILD COMPLETE — ${live.featurePriority}` });
      emit('build-complete', { cycle, brief: live.brief });
      live.running = false;
      return;
    }

    // Backend Engineer: runs on cycle 2 for tech-startup categories,
    // only when no backend has been spawned yet this session.
    const needsBackend = cycle === 2
      && !live.backendPort
      && !fs.existsSync(path.join(live.workspaceDir || '', 'api/server.js'))
      && (!live.category || live.category === 'tech-startup');
    if (needsBackend) {
      pushMsg({ from: 'system', to: null, type: 'system', message: `⚙️ BACKEND ENG designing real API...` });
      await callAgent('backend-eng');
      if (!live.running) return;
      // Spawn the backend now so the builder can reference real /backend/... endpoints
      await spawnBackend(live.workspaceDir);
    }

    while (live.paused) await sleep(500);
    pushMsg({ from: 'system', to: null, type: 'system', message: `⚙️ CYCLE ${cycle} · DEVELOPER building...` });
    await callAgent('builder');
    if (!live.running) return;
    live.customerFeedback = '';  // consumed — full cycle addressed it
    live._feedbackPending = false;
  }

  // Safety net: auto-generate any required files the builder missed
  await ensureRequiredFiles();

  // Also try to spawn backend if api/server.js appeared this cycle (cycle 2+ safety net)
  if (live.workspaceDir && !live.backendPort) await spawnBackend(live.workspaceDir);

  // Persist cross-cycle memory so agents remember decisions and avoid regressions
  updateAgentMemory(cycle);
  // Save live state to disk — allows partial recovery if server restarts mid-session
  saveLiveState();

  // QA + CSS coverage run async — they don't block the next cycle start
  const postCycleWork = Promise.all([
    live.agents?.includes('qa') ? runStep('qa') : Promise.resolve(),
    ensureCSSCoverage(),
  ]);
  postCycleWork.catch(() => {}); // fire-and-forget

  // Pre-capture screenshot during the gap so CEO has it instantly next cycle
  emit('screenshot-request', {});
  live.previewScreenshot = null;

  // Gap reduced to 2s — screenshot arrives quickly; QA/CSS run in background
  const gap = live._feedbackPending ? 0 : Math.round(2000 / live.speed);
  const msg = live._feedbackPending
    ? `✅ CYCLE ${cycle} COMPLETE — feedback detected, acting immediately`
    : `✅ CYCLE ${cycle} COMPLETE — next in ~2s`;
  pushMsg({ from: 'system', to: null, type: 'system', message: msg });

  live.timers['pipeline'] = setTimeout(runPipeline, gap);
}

function scheduleSide(agentId) {
  if (!live.running) return;
  const delay = Math.round(LIVE_AGENTS[agentId].interval / live.speed);
  live.timers[agentId] = setTimeout(async () => {
    while (live.paused) await sleep(500);
    if (live.running) { await callAgent(agentId); scheduleSide(agentId); }
  }, delay);
}

function addClient(res) {
  live.clients.push(res);
  if (live._autoPaused) {
    live._autoPaused = false;
    live.paused = false;
    pushMsg({ from: 'system', to: null, type: 'system', message: '▶ CLIENT RECONNECTED — RESUMING' });
  }
}

function removeClient(res) {
  live.clients = live.clients.filter(c => c !== res);
  if (live.clients.length === 0 && live.running && !live.paused) {
    live.paused = true;
    live._autoPaused = true;
    console.log('[pipeline] no clients — auto-paused');
  }
}

module.exports = {
  get live() { return live; },
  setLive(s) {
    // Mutate in-place so server.js's destructured `live` reference stays valid
    Object.keys(live).forEach(k => delete live[k]);
    Object.assign(live, s);
  },
  LIVE_AGENTS,
  sleep,
  emit,
  pushContext,
  pushMsg,
  stopAll,
  killBackend,
  callAgent,
  runPipeline,
  scheduleSide,
  addClient,
  removeClient,
  loadLiveState,
};
