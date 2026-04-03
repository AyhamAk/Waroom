/* ══════════════════════════════════════════════
   WAR ROOM — CORE
   Shared DOM refs and phase navigation.
   Depends on: data.js, state.js, utils.js
   ══════════════════════════════════════════════ */

/* ── Shared DOM refs ── */
const $brief        = document.getElementById('brief-input');
const $agentGrid    = document.getElementById('agent-grid');
const $deployBtn    = document.getElementById('deploy-btn');
const $countBadge   = document.getElementById('agent-count-badge');
const $budgetDisp   = document.getElementById('budget-display');
const $budgetFill   = document.getElementById('budget-bar-fill');
const $budgetPct    = document.getElementById('budget-pct');
const $topbarBudget = document.getElementById('topbar-budget');
const $missionText  = document.getElementById('mission-text');
const $agentsRow    = document.getElementById('agents-row');
const $btStatus     = document.getElementById('bt-status');
const $activePanel  = document.getElementById('active-panel');
const $portraitWrap = document.getElementById('portrait-svg-wrap');
const $portraitRing = document.getElementById('portrait-ring');
const $activeName   = document.getElementById('active-agent-name');
const $activeRole   = document.getElementById('active-agent-role');
const $activeStatus = document.getElementById('active-status-badge');
const $thinkingDots = document.getElementById('thinking-dots');
const $bubbleLabel  = document.getElementById('bubble-label');
const $bubbleOutput = document.getElementById('bubble-output');
const $burnList     = document.getElementById('token-burn-list');
const $totalBurned  = document.getElementById('total-burned');
const $burnFill     = document.getElementById('burn-bar-fill');
const $burnPct      = document.getElementById('burn-pct');
const $activityLog  = document.getElementById('activity-log');
const $delivGrid    = document.getElementById('deliverables-grid');
const $newMissionBtn= document.getElementById('new-mission-btn');
const $goLiveBtn    = document.getElementById('go-live-btn');

/* ── Phase navigation ── */
function showPhase(n) {
  state.currentPhase = n;
  document.querySelectorAll('.phase').forEach((el, i) => el.classList.toggle('active', i + 1 === n));
  document.querySelectorAll('.phase-indicator').forEach((el, i) => {
    el.classList.remove('active', 'done');
    if (i + 1 === n) el.classList.add('active');
    if (i + 1 < n)  el.classList.add('done');
  });
}
