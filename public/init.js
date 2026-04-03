/* ══════════════════════════════════════════════
   WAR ROOM — INIT
   Boot sequence: runs after all scripts are loaded.
   ══════════════════════════════════════════════ */

buildModeSelector();
buildCategoryRow();
buildAgentGrid();
selectCategory('tech-startup');
showPhase(1);

// Auto-reconnect if a session is already running on the server
fetch('/api/status').then(r => r.json()).then(s => {
  if (s.running) reconnectLiveMode(s);
}).catch(() => {});
