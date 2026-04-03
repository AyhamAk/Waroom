/* ══════════════════════════════════════════════
   WAR ROOM — PHASE 2: BRIEFING ROOM
   Agent briefing loop, streaming, burn tracking.
   Depends on: data.js, state.js, utils.js, app.js
   ══════════════════════════════════════════════ */

function buildBriefingSeats(queue) {
  $agentsRow.innerHTML = '';
  queue.forEach((a, i) => {
    const seat = document.createElement('div');
    seat.className = 'agent-seat waiting';
    seat.id = `seat-${a.id}`;
    seat.style.setProperty('--ac', a.color);
    seat.style.setProperty('--float-delay', `${i * 0.35}s`);
    seat.style.setProperty('--float-dur', `${2.8 + i * 0.15}s`);
    seat.innerHTML = `
      <div class="seat-portrait-wrap">
        <div class="seat-portrait" style="border-color:${a.color}">${getPortrait(a)}</div>
        <div class="seat-ping" style="display:none"></div>
      </div>
      <div class="seat-label">${a.name}</div>`;
    $agentsRow.appendChild(seat);
  });
}

function setSeatState(agentId, st) {
  const seat = document.getElementById(`seat-${agentId}`);
  if (!seat) return;
  seat.className = `agent-seat ${st}`;
  const ping = seat.querySelector('.seat-ping');
  ping.style.display = st === 'active' ? 'block' : 'none';
  if (st === 'complete' && !seat.querySelector('.seat-check')) {
    const chk = document.createElement('div');
    chk.className = 'seat-check'; chk.textContent = '✓';
    seat.querySelector('.seat-portrait-wrap').appendChild(chk);
  }
}

function showActivePanel(agent) {
  $activePanel.style.setProperty('--panel-color', agent.color);
  $portraitRing.style.cssText = `border-color:${agent.color};box-shadow:0 0 24px ${agent.color},0 0 48px rgba(0,0,0,0.4),inset 0 0 16px rgba(0,0,0,0.3)`;
  $portraitWrap.innerHTML = getPortrait(agent);
  $activeName.textContent = agent.name;
  $activeName.style.color = agent.color;
  $activeRole.textContent = agent.role;
  $activeStatus.textContent = 'THINKING';
  $activeStatus.className = 'status-badge status-thinking';
  $bubbleLabel.textContent = `${agent.name.toUpperCase()} IS BRIEFING THE ROOM...`;
  $bubbleLabel.style.color = agent.color;
  $bubbleOutput.textContent = '';
  $thinkingDots.classList.remove('hidden');
  $activePanel.hidden = false;
  void $activePanel.offsetWidth;
  $activePanel.style.animation = '';
}

async function startMission() {
  state.results = []; state.totalBurned = 0;
  $burnList.innerHTML = ''; $totalBurned.textContent = '0';
  $burnFill.style.width = '0%'; $activityLog.innerHTML = '';
  $activePanel.hidden = true;
  $missionText.textContent = state.brief;
  updateTopbarBudget(TOTAL_BUDGET);
  showPhase(2);
  logActivity('MISSION INITIATED');

  const allAgents = Object.values(CATEGORY_AGENTS).flat();
  const queue = state.selectedAgents.map(id => allAgents.find(a => a.id === id)).filter(Boolean);
  buildBriefingSeats(queue);
  $btStatus.textContent = 'TEAM ASSEMBLED — STANDBY';
  queue.forEach((a, i) => setSeatState(a.id, i === 0 ? 'waiting' : 'idle'));

  let ctx = `PROJECT BRIEF:\n${state.brief}`;

  for (let i = 0; i < queue.length; i++) {
    const agent = queue[i];
    const next  = queue[i + 1];
    if (TOTAL_BUDGET - state.totalBurned < 500) { showBudgetExceeded(); break; }

    $btStatus.textContent = `${agent.name.toUpperCase()} SPEAKING...`;
    setSeatState(agent.id, 'active');
    showActivePanel(agent);

    const { output, inputTokens, outputTokens } = await streamAgent(agent, ctx);
    ctx += `\n\n--- ${agent.name.toUpperCase()} (${agent.role}) ---\n${output}`;
    state.results.push({ agent, output, inputTokens, outputTokens });

    $activeStatus.textContent = 'COMPLETE';
    $activeStatus.className   = 'status-badge status-complete';
    $thinkingDots.classList.add('hidden');
    $bubbleLabel.textContent = `${agent.name.toUpperCase()} — ${fmtNum(inputTokens + outputTokens)} TOKENS`;
    setSeatState(agent.id, 'complete');
    addBurnItem(agent, inputTokens + outputTokens);
    updateBurnTotal();
    updateTopbarBudget(TOTAL_BUDGET - state.totalBurned);
    logActivity(`${agent.name.toUpperCase()} → COMPLETE (${fmtNum(inputTokens + outputTokens)} tkn)`);

    if (next) { $btStatus.textContent = `HANDOFF → ${next.name.toUpperCase()}`; setSeatState(next.id, 'idle'); await sleep(800); }
  }

  $btStatus.textContent = 'MISSION COMPLETE';
  logActivity('ALL AGENTS COMPLETE');
  await sleep(1200);
  buildDeliverables();
  showPhase(3);
}

async function streamAgent(agent, context) {
  let fullText = '', inputTokens = 0, outputTokens = 0;
  const cursor = document.createElement('span');
  cursor.className = 'cursor';
  $bubbleOutput.appendChild(cursor);

  try {
    const res = await fetch('/api/run-agent', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        systemPrompt: agent.system, context, maxTokens: agent.maxOutput,
        provider: state.llmMode, apiKey: state.apiKey,
      }),
    });
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const lines = buf.split('\n'); buf = lines.pop();
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const d = JSON.parse(line.slice(6));
          if (d.type === 'text') {
            fullText += d.text;
            cursor.remove();
            $bubbleOutput.textContent = fullText;
            $bubbleOutput.appendChild(cursor);
            $bubbleOutput.scrollTop = $bubbleOutput.scrollHeight;
          } else if (d.type === 'done') {
            inputTokens = d.inputTokens; outputTokens = d.outputTokens;
            state.totalBurned += inputTokens + outputTokens;
          }
        } catch { /**/ }
      }
    }
  } catch (err) { fullText = `[Error: ${err.message}]`; }
  cursor.remove();
  $bubbleOutput.textContent = fullText;
  return { output: fullText, inputTokens, outputTokens };
}

/* ── Helpers ── */
function showBudgetExceeded() {
  $btStatus.textContent = '⚠ BUDGET EXCEEDED';
  $activePanel.hidden = true;
  const el = document.createElement('div');
  el.className = 'budget-exceeded';
  el.innerHTML = `⚠ BUDGET EXCEEDED<p>Token budget exhausted.</p>`;
  document.querySelector('.warroom-main').appendChild(el);
}

function addBurnItem(agent, tokens) {
  const el = document.createElement('div');
  el.className = 'burn-item';
  el.innerHTML = `<div class="burn-dot" style="background:${agent.color}"></div><span class="burn-name">${agent.abbr}</span><span class="burn-val">${fmtNum(tokens)}</span>`;
  $burnList.appendChild(el);
}

function updateBurnTotal() {
  $totalBurned.textContent = fmtNum(state.totalBurned);
  const pct = Math.min((state.totalBurned / TOTAL_BUDGET) * 100, 100);
  $burnFill.style.width = `${pct}%`;
  $burnPct.textContent = `${pct.toFixed(2)}% of budget`;
}

function updateTopbarBudget(rem) {
  $topbarBudget.textContent = fmtNum(Math.max(rem, 0));
  const pct = (rem / TOTAL_BUDGET) * 100;
  $topbarBudget.classList.toggle('warn', pct < 40 && pct >= 15);
  $topbarBudget.classList.toggle('danger', pct < 15);
}

function logActivity(msg) {
  const t = new Date().toTimeString().slice(0, 8);
  const el = document.createElement('div');
  el.className = 'log-entry';
  el.innerHTML = `<span class="log-time">${t}</span> ${msg}`;
  $activityLog.insertBefore(el, $activityLog.firstChild);
}
