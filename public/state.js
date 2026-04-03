/* ══════════════════════════════════════════════
   WAR ROOM — MUTABLE STATE
   Planning state (phases 1-3) and live state (phase 4).
   ══════════════════════════════════════════════ */

let state = {
  selectedAgents: [],
  selectedCategory: 'tech-startup',
  brief: '',
  results: [],
  totalBurned: 0,
  currentPhase: 1,
  llmMode: 'gemini',      // 'gemini' | 'anthropic'
  apiKey: '',
};

let liveState = {
  paused: false,
  speed: 1,
  tokens: 0,
  startTime: null,
  timerInterval: null,
  files: {}, // path → { content, agentId, ts, lines }
  msgCount: 0,
  sse: null,
};
