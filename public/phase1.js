/* ══════════════════════════════════════════════
   WAR ROOM — PHASE 1: ASSEMBLE
   Agent grid, category selector, budget meter.
   Depends on: data.js, state.js, utils.js, app.js
   ══════════════════════════════════════════════ */

function buildAgentGrid() {
  $agentGrid.innerHTML = '';
  getAgents().forEach(a => {
    const card = document.createElement('div');
    card.className = 'agent-card';
    card.dataset.id = a.id;
    card.style.setProperty('--agent-color', a.color);
    const tags = AGENT_TAGS[a.id] || [];
    card.innerHTML = `
      <div class="card-corner tl"></div><div class="card-corner tr"></div>
      <div class="card-corner bl"></div><div class="card-corner br"></div>
      <div class="agent-card-header">
        <div class="agent-avatar-wrap" style="border-color:${a.color};box-shadow:0 0 14px ${a.color}33">
          <div style="width:44px;height:44px;border-radius:50%;overflow:hidden">${getPortrait(a)}</div>
        </div>
        <div>
          <div class="agent-name" style="color:${a.color}">${a.name}</div>
          <div class="agent-role">${a.role}</div>
        </div>
        <div class="agent-select-indicator">✓</div>
      </div>
      <div class="agent-desc">${a.desc}</div>
      <div class="agent-tags">${tags.map(t=>`<span class="agent-tag">${t}</span>`).join('')}</div>
      <div class="agent-card-footer">
        <div class="agent-token-cost">EST. COST &nbsp;<span>${fmtNum(a.tokens)}</span> TKN</div>
        <div class="agent-status-dot" style="background:${a.color}"></div>
      </div>`;
    card.addEventListener('click', () => toggleAgent(a.id));
    $agentGrid.appendChild(card);
  });
}

function buildCategoryRow() {
  const row = document.getElementById('category-row');
  if (!row) return;
  row.innerHTML = '';
  CATEGORIES.forEach(cat => {
    const card = document.createElement('div');
    card.className = 'category-card' + (cat.locked ? ' locked' : '');
    card.dataset.id = cat.id;
    card.style.setProperty('--cat-color', cat.color);
    const agentCount = (CATEGORY_AGENTS[cat.id] || []).length;
    card.innerHTML = `
      <div class="cat-corner tl"></div><div class="cat-corner tr"></div>
      <div class="cat-corner bl"></div><div class="cat-corner br"></div>
      <div class="cat-icon">${cat.icon}</div>
      <div class="cat-name">${cat.name}</div>
      <div class="cat-tagline">${cat.tagline}</div>
      <div class="cat-footer">
        <span class="cat-agent-count">${agentCount > 0 ? agentCount + ' AGENTS' : '—'}</span>
        ${cat.locked ? '<span class="cat-lock-badge">SOON</span>' : '<span class="cat-active-badge">ACTIVE</span>'}
      </div>`;
    if (!cat.locked) {
      card.addEventListener('click', () => selectCategory(cat.id));
    }
    row.appendChild(card);
  });
}

function selectCategory(id) {
  const cat = CATEGORIES.find(c => c.id === id);
  if (!cat || cat.locked) return;
  state.selectedCategory = id;
  state.selectedAgents = (CATEGORY_AGENTS[id] || []).map(a => a.id);
  document.querySelectorAll('.category-card').forEach(c =>
    c.classList.toggle('selected', c.dataset.id === id));
  buildAgentGrid();
  updateAgentCards();
  updateBudgetMeter();
  updateDeployBtn();
}

function toggleAgent(id) {
  const i = state.selectedAgents.indexOf(id);
  if (i === -1) state.selectedAgents.push(id);
  else state.selectedAgents.splice(i, 1);
  updateAgentCards(); updateBudgetMeter(); updateDeployBtn();
}

function updateAgentCards() {
  document.querySelectorAll('.agent-card').forEach(c =>
    c.classList.toggle('selected', state.selectedAgents.includes(c.dataset.id)));
  $countBadge.textContent = `${state.selectedAgents.length} SELECTED`;
}

function updateBudgetMeter() {
  const allAgents = Object.values(CATEGORY_AGENTS).flat();
  const cost = state.selectedAgents.reduce((s, id) => s + (allAgents.find(x => x.id === id)?.tokens || 0), 0);
  const pct = Math.min((cost / TOTAL_BUDGET) * 100, 100);
  $budgetDisp.textContent = `${fmtNum(cost)} / ${fmtNum(TOTAL_BUDGET)}`;
  $budgetFill.style.width = `${pct}%`;
  $budgetPct.textContent = `${pct.toFixed(1)}% of budget committed`;
  $budgetFill.classList.toggle('warn',   pct >= 60 && pct < 85);
  $budgetFill.classList.toggle('danger', pct >= 85);
  if (state.currentPhase === 1) updateTopbarBudget(TOTAL_BUDGET - cost);
}

function updateDeployBtn() {
  const hasKey    = state.apiKey.trim().length > 10;
  const hasAgents = state.selectedAgents.length > 0;
  const hasBrief  = $brief.value.trim().length > 10;
  $deployBtn.disabled = !(hasKey && hasAgents && hasBrief);
}

/* ── Mode selector ── */
function buildModeSelector() {
  const wrap = document.getElementById('mode-selector');
  if (!wrap) return;
  wrap.innerHTML = `
    <label class="field-label">// COMMAND SOURCE</label>
    <div class="mode-row">
      <div class="mode-card selected" data-mode="gemini">
        <div class="cat-corner tl"></div><div class="cat-corner tr"></div>
        <div class="cat-corner bl"></div><div class="cat-corner br"></div>
        <div class="mode-icon">⚡</div>
        <div class="mode-name">FREE MODE</div>
        <div class="mode-sub">Google Gemini Flash</div>
        <div class="mode-badge mode-badge--free">NO COST</div>
        <input class="mode-key-input" id="key-gemini" type="password"
          placeholder="Paste Gemini API key..."
          autocomplete="off" spellcheck="false" />
        <div class="mode-hint">Free key → <span class="mode-link" onclick="window.open('https://aistudio.google.com/app/apikey')">aistudio.google.com</span></div>
      </div>
      <div class="mode-card" data-mode="anthropic">
        <div class="cat-corner tl"></div><div class="cat-corner tr"></div>
        <div class="cat-corner bl"></div><div class="cat-corner br"></div>
        <div class="mode-icon">🔑</div>
        <div class="mode-name">MY API KEY</div>
        <div class="mode-sub">Claude (Anthropic)</div>
        <div class="mode-badge mode-badge--pro">FULL POWER</div>
        <input class="mode-key-input" id="key-anthropic" type="password"
          placeholder="Paste Anthropic API key..."
          autocomplete="off" spellcheck="false" />
        <div class="mode-hint">Get key → <span class="mode-link" onclick="window.open('https://console.anthropic.com/')">console.anthropic.com</span></div>
      </div>
    </div>`;

  wrap.querySelectorAll('.mode-card').forEach(card => {
    card.addEventListener('click', e => {
      if (e.target.classList.contains('mode-key-input') || e.target.classList.contains('mode-link')) return;
      selectMode(card.dataset.mode);
    });
  });

  wrap.querySelectorAll('.mode-key-input').forEach(input => {
    input.addEventListener('input', () => {
      if (input.id === `key-${state.llmMode}`) {
        state.apiKey = input.value;
        updateDeployBtn();
      }
    });
  });
}

function selectMode(mode) {
  state.llmMode = mode;
  // Sync apiKey from the active input
  const input = document.getElementById(`key-${mode}`);
  state.apiKey = input ? input.value : '';
  document.querySelectorAll('.mode-card').forEach(c =>
    c.classList.toggle('selected', c.dataset.mode === mode));
  // Re-attach input listener to new active field
  if (input) {
    input.addEventListener('input', () => {
      state.apiKey = input.value;
      updateDeployBtn();
    });
  }
  updateDeployBtn();
}

/* ── Event listeners ── */
$brief.addEventListener('input', updateDeployBtn);
$deployBtn.addEventListener('click', () => {
  state.brief = $brief.value.trim();
  if (!state.brief || !state.selectedAgents.length) return;
  startMission();
});
$newMissionBtn.addEventListener('click', () => resetToPhase1());
$goLiveBtn.addEventListener('click', () => startLiveMode());
