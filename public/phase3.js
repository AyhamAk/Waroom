/* ══════════════════════════════════════════════
   WAR ROOM — PHASE 3: MISSION DEBRIEF
   Deliverables grid and new mission reset.
   Depends on: data.js, state.js, utils.js, app.js
   ══════════════════════════════════════════════ */

function buildDeliverables() {
  $delivGrid.innerHTML = '';
  const total = state.results.reduce((s, r) => s + r.inputTokens + r.outputTokens, 0);
  const pct = ((total / TOTAL_BUDGET) * 100).toFixed(2);
  document.getElementById('report-total').innerHTML  = `<span class="stat-label">TOTAL TOKENS</span><span class="stat-value">${fmtNum(total)}</span><span class="stat-sub">of ${fmtNum(TOTAL_BUDGET)}</span>`;
  document.getElementById('report-pct').innerHTML    = `<span class="stat-label">BUDGET USED</span><span class="stat-value">${pct}%</span><span class="stat-sub">${fmtNum(TOTAL_BUDGET - total)} remaining</span>`;
  document.getElementById('report-agents').innerHTML = `<span class="stat-label">AGENTS</span><span class="stat-value">${state.results.length}</span><span class="stat-sub">of ${state.selectedAgents.length} selected</span>`;
  state.results.forEach(({ agent, output, inputTokens, outputTokens }) => {
    const card = document.createElement('div');
    card.className = 'deliverable-card';
    card.innerHTML = `
      <div class="deliverable-header">
        <div style="width:44px;height:44px;border-radius:50%;overflow:hidden;border:2px solid ${agent.color}">${PORTRAITS[agent.id]||''}</div>
        <div class="deliverable-agent"><div class="deliverable-name" style="color:${agent.color}">${agent.name}</div><div class="deliverable-role">${agent.role}</div></div>
        <div class="deliverable-tokens"><strong>${fmtNum(inputTokens + outputTokens)}</strong> tokens</div>
      </div>
      <div class="deliverable-body">${escHtml(output)}</div>`;
    $delivGrid.appendChild(card);
  });
}

function resetToPhase1() {
  state.selectedAgents = []; state.brief = ''; state.results = []; state.totalBurned = 0;
  $brief.value = ''; $activePanel.hidden = true;
  updateAgentCards(); updateBudgetMeter(); updateDeployBtn();
  showPhase(1);
}
