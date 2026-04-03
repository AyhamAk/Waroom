/* ══════════════════════════════════════════════
   WAR ROOM — UTILITIES
   Pure helpers. Depends on: data.js, state.js
   ══════════════════════════════════════════════ */

const fmtNum  = n  => Number(n).toLocaleString('en-US');
const sleep   = ms => new Promise(r => setTimeout(r, ms));
const escHtml = s  => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

function timeAgo(ts) {
  const s = Math.floor((Date.now() - ts) / 1000);
  if (s < 5)    return 'just now';
  if (s < 60)   return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
}

function getAgents() {
  return CATEGORY_AGENTS[state.selectedCategory] || CATEGORY_AGENTS['tech-startup'];
}

function getPortrait(agent) {
  const key = PORTRAIT_FALLBACK[agent.id] || agent.id;
  return PORTRAITS[key] || PORTRAITS['pm'] || '';
}
