/* ══════════════════════════════════════════════
   WAR ROOM — LIVE PIPELINE
   Agent definitions, live state, SSE helpers,
   callAgent, runPipeline, scheduleSide.
   ══════════════════════════════════════════════ */

require('dotenv').config();
const path = require('path');
const fs = require('fs');
const { buildPrompt } = require('./prompts');
const { createMessage, getModels } = require('./llm');

const sleep = ms => new Promise(r => setTimeout(r, ms));

/* ── Agent definitions ── */
const LIVE_AGENTS = {
  ceo: {
    name: 'CEO', abbr: 'CEO', role: 'Chief Executive',
    color: '#00e676', maxTokens: 600,
    communicatesWith: ['lead-eng'],
  },
  'lead-eng': {
    name: 'Lead Engineer', abbr: 'LE', role: 'Lead Engineer',
    color: '#4fc3f7', maxTokens: 500,
    communicatesWith: ['builder'],
  },
  designer: {
    name: 'UI Designer', abbr: 'UID', role: 'UI Designer',
    color: '#ce93d8', maxTokens: 400,
    communicatesWith: ['builder'],
  },
  builder: {
    name: 'Developer', abbr: 'DEV', role: 'Full-Stack Developer',
    color: '#ffb74d', maxTokens: 12000,
    communicatesWith: [],
  },
  qa: {
    name: 'QA Engineer', abbr: 'QA', role: 'QA Engineer',
    color: '#80cbc4', maxTokens: 400,
    communicatesWith: ['lead-eng'],
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

/* ── Core agent call (returns promise) ── */
async function callAgent(agentId) {
  if (!live.running || live.paused) return;
  const agent = LIVE_AGENTS[agentId];
  emit('agent-status', { agentId, status: 'thinking' });

  try {
    const usesSmart = agentId === 'builder';
    const promptText = buildPrompt(agentId, live);
    const provider = live.provider || 'anthropic';
    const apiKey   = live.apiKey   || process.env.ANTHROPIC_API_KEY;
    const models   = getModels(provider);
    const model    = usesSmart ? models.smart : models.fast;

    // Builder + CEO get a screenshot if available (Anthropic-style; llm.js translates for Gemini)
    const useScreenshot = ['builder', 'ceo'].includes(agentId);
    const userContent = (useScreenshot && live.previewScreenshot)
      ? [
          { type: 'image', source: { type: 'base64', media_type: live.previewScreenshot.mediaType, data: live.previewScreenshot.base64 } },
          { type: 'text', text: `This is a screenshot of the current website state.\n\n${promptText}` },
        ]
      : promptText;

    const { text: raw, inputTokens, outputTokens } = await createMessage({
      provider, apiKey, model,
      maxTokens: agent.maxTokens,
      messages: [{ role: 'user', content: userContent }],
    });

    live.tokens += inputTokens + outputTokens;
    emit('token-update', { total: live.tokens, delta: inputTokens + outputTokens });

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

        const safePath = filename.replace(/\.\./g, '').replace(/[^a-zA-Z0-9.\-_/]/g, '-');
        const fullPath = path.join(live.workspaceDir, safePath);
        fs.mkdirSync(path.dirname(fullPath), { recursive: true });

        // Cycles 2+: merge content into existing files
        const isBuilder = agentId === 'builder';
        const isUpdate  = (live.cycle || 1) > 1 && isBuilder && fs.existsSync(fullPath);
        const isFixCycle = (live.featurePriority || '').trim().startsWith('FIX:');
        if (isUpdate && safePath === 'public/style.css' && !isFixCycle) {
          filecontent = fs.readFileSync(fullPath, 'utf8') + '\n\n' + filecontent;
        } else if (isUpdate && safePath === 'public/app.js' && !isFixCycle) {
          filecontent = fs.readFileSync(fullPath, 'utf8') + '\n\n' + filecontent;
        } else if (isUpdate && safePath.startsWith('public/') && safePath.endsWith('.html') && !isFixCycle) {
          const existing = fs.readFileSync(fullPath, 'utf8');
          filecontent = existing.includes('</body>')
            ? existing.replace(/<\/body>/i, '\n' + filecontent + '\n</body>')
            : existing + '\n' + filecontent;
        }
        // FIX mode: write the complete replacement as-is (no append)

        fs.writeFileSync(fullPath, filecontent, 'utf8');
        const lines = filecontent.split('\n').length;
        const entry = { path: safePath, content: filecontent, agentId, ts: Date.now(), lines };
        const idx = live.files.findIndex(f => f.path === safePath);
        if (idx >= 0) live.files[idx] = entry; else live.files.push(entry);
        if (agentId === 'sales') live.salesV++;
        if (safePath === 'docs/feature-priority.md') {
          live.pastPriorities.push(filecontent.slice(0, 120));
          live.featurePriority = filecontent.trim();
        }
        emit('new-file', entry);
        if (safePath.startsWith('public/')) emit('preview-refresh', { path: safePath, ts: Date.now() });
        pushMsg({ from: agentId, to: null, type: 'file',
          message: `📄 \`${safePath}\` — ${lines} lines · ${task}` });
        pushContext(agentId, agentId, `produced ${safePath}: ${task}`);
        didWork = true;
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
        // Builder always should produce files — surface first 200 chars of raw for debugging
        pushMsg({ from: 'system', to: null, type: 'system',
          message: `⚠️ DEVELOPER produced no files. Raw: ${raw.slice(0, 200).replace(/\n/g, ' ')}` });
      }
    }
  } catch (err) {
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

  await runStep('ceo');
  if (!live.running) return;
  // Keep customerFeedback alive so lead-eng, designer, builder all see it this cycle
  // It gets cleared AFTER builder runs below

  pushMsg({ from: 'system', to: null, type: 'system', message: `⚙️ LEAD ENG + DESIGNER planning in parallel...` });
  await Promise.all([callAgent('lead-eng'), callAgent('designer')]);
  if (!live.running) return;

  while (live.paused) await sleep(500);
  pushMsg({ from: 'system', to: null, type: 'system', message: `⚙️ CYCLE ${cycle} · DEVELOPER building...` });
  await callAgent('builder');
  if (!live.running) return;
  live.customerFeedback = '';  // consumed — full cycle addressed it
  live._feedbackPending = false;

  if (live.agents?.includes('qa')) {
    await runStep('qa');
  }

  // If new feedback arrived mid-cycle, skip the gap and act immediately
  const gap = live._feedbackPending ? 0 : Math.round(10000 / live.speed);
  const msg = live._feedbackPending
    ? `✅ CYCLE ${cycle} COMPLETE — feedback detected, acting immediately`
    : `✅ CYCLE ${cycle} COMPLETE — next round in 10s`;
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
  callAgent,
  runPipeline,
  scheduleSide,
  addClient,
  removeClient,
};
