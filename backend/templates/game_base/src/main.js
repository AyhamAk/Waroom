// Entry point. Boot the engine, hand off to the game.
import { Engine } from './engine/index.js';
import { Game } from './game/game.js';

const canvas = document.getElementById('stage');
const loading = document.getElementById('loading');

async function boot() {
  const engine = new Engine(canvas);
  await engine.init();

  const game = new Game(engine);
  await game.preload();

  loading.hidden = true;
  document.getElementById('hud').hidden = false;

  game.start();
  engine.start(game);

  // Optional perf overlay: append ?perf=1 to URL.
  if (new URLSearchParams(location.search).has('perf')) {
    engine.enablePerfOverlay();
  }

  // Expose for console debugging.
  window.__engine = engine;
  window.__game = game;
}

boot().catch((err) => {
  console.error('Boot failure', err);
  loading.innerHTML = `<div style="color:#ff5555">Boot error<br><pre style="font-size:11px">${(err && err.stack) || err}</pre></div>`;
});
