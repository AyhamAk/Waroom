// Engine — orchestrates renderer, lighting, input, audio, asset registry,
// UI, particles, decals, post-FX, perf. Game classes plug in via
// engine.game = new Game(engine); engine.start(game).

import { Renderer } from './renderer.js';
import { Lighting } from './lighting.js';
import { Input } from './input.js';
import { Audio } from './audio.js';
import { Assets } from './assets.js';
import { UI } from './ui.js';
import { PostFX } from './postfx.js';
import { Particles } from './particles.js';
import { Decals } from './decals.js';

export class Engine {
  constructor(canvas) {
    this.canvas = canvas;
    this.renderer = new Renderer(canvas);
    this.input = new Input(canvas);
    this.audio = new Audio();
    this.assets = new Assets();
    this.ui = new UI();
    // Set lazily after renderer.init():
    this.lighting = null;
    this.particles = null;
    this.decals = null;
    this.postfx = null;

    this.clock = { last: 0, dt: 0, t: 0, frame: 0, fps: 0, _acc: 0, _frames: 0 };
    this.running = false;
    this.game = null;
    this._perfEl = null;
    this._fixedStep = 1 / 60;
    this._accumulator = 0;
  }

  async init() {
    await this.renderer.init();
    this.assets.attachKtx2(this.renderer.three);
    this.lighting = new Lighting(this);
    this.particles = new Particles(this);
    this.decals = new Decals(this);
    this.input.attach();
    this.ui.mount();
  }

  // Tech-Art's preset lands here. Optional — Game can call it later.
  async applyLightingPreset(presetOrCfg) {
    if (!this.lighting) return;
    await this.lighting.applyPreset(presetOrCfg);
  }

  // Tech-Art's post-FX preset.
  enablePostFX(preset = 'standard') {
    if (this.postfx) return;
    this.postfx = new PostFX(this, preset);
  }

  start(game) {
    this.game = game;
    this.running = true;
    this.clock.last = performance.now();
    requestAnimationFrame(this._tick);
  }

  stop() {
    this.running = false;
  }

  _tick = (t) => {
    if (!this.running) return;
    const dt = Math.min(0.1, (t - this.clock.last) / 1000);
    this.clock.last = t;
    this.clock.dt = dt;
    this.clock.t += dt;
    this.clock.frame++;
    this.clock._acc += dt;
    this.clock._frames++;
    if (this.clock._acc >= 0.5) {
      this.clock.fps = this.clock._frames / this.clock._acc;
      this.clock._acc = 0;
      this.clock._frames = 0;
    }
    if (this.game?.update) this.game.update(dt, this.clock.t);
    if (this.lighting) this.lighting.update();
    if (this.particles) this.particles.update(dt, this.clock.t);
    this.input.tick();
    if (this.postfx?.render) this.postfx.render();
    else this.renderer.render();
    if (this._perfEl) this._updatePerf();
    requestAnimationFrame(this._tick);
  };

  enablePerfOverlay() {
    if (this._perfEl) return;
    const el = document.createElement('div');
    el.id = 'perf';
    document.body.appendChild(el);
    this._perfEl = el;
  }

  _updatePerf() {
    const r = this.renderer.three.info;
    this._perfEl.textContent =
      `fps   ${this.clock.fps.toFixed(1)}\n` +
      `dt    ${(this.clock.dt * 1000).toFixed(2)}ms\n` +
      `tris  ${r.render.triangles}\n` +
      `calls ${r.render.calls}\n` +
      `geo   ${r.memory.geometries}\n` +
      `tex   ${r.memory.textures}`;
  }
}
