// Audio — Web Audio wrapper. Synthesised SFX (no asset dependency) plus
// optional sample loader. Spatial audio via PannerNode if a listener is set.

export class Audio {
  constructor() {
    this.ctx = null;
    this.master = null;
    this.musicGain = null;
    this.sfxGain = null;
    this.unlocked = false;
    this.samples = new Map();
    addEventListener('pointerdown', this._unlock, { once: true });
    addEventListener('keydown', this._unlock, { once: true });
  }

  _unlock = () => {
    if (this.unlocked) return;
    this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    this.master = this.ctx.createGain(); this.master.gain.value = 0.7;
    this.musicGain = this.ctx.createGain(); this.musicGain.gain.value = 0.5;
    this.sfxGain = this.ctx.createGain(); this.sfxGain.gain.value = 0.9;
    this.musicGain.connect(this.master);
    this.sfxGain.connect(this.master);
    this.master.connect(this.ctx.destination);
    this.unlocked = true;
  };

  setMasterVolume(v) { if (this.master) this.master.gain.value = v; }
  setMusicVolume(v) { if (this.musicGain) this.musicGain.gain.value = v; }
  setSfxVolume(v) { if (this.sfxGain) this.sfxGain.gain.value = v; }

  // Quick synthesised one-shot. type: 'click'|'hit'|'pickup'|'shoot'|'jump'|'die'|'beep'.
  blip(type = 'beep', { freq = 440, dur = 0.08, gain = 0.4, sweep = 0 } = {}) {
    if (!this.unlocked) return;
    const t0 = this.ctx.currentTime;
    const osc = this.ctx.createOscillator();
    const g = this.ctx.createGain();
    osc.connect(g);
    g.connect(this.sfxGain);
    osc.type = ({ click: 'square', hit: 'sawtooth', pickup: 'triangle', shoot: 'sawtooth', jump: 'square', die: 'sawtooth', beep: 'sine' })[type] || 'sine';
    let f = freq;
    if (type === 'shoot')  { f = 220; sweep = -180; dur = 0.06; }
    if (type === 'pickup') { f = 880; sweep = 660;  dur = 0.10; }
    if (type === 'hit')    { f = 180; sweep = -90;  dur = 0.12; }
    if (type === 'jump')   { f = 320; sweep = 180;  dur = 0.10; }
    if (type === 'die')    { f = 220; sweep = -200; dur = 0.45; }
    if (type === 'click')  { f = 600; sweep = -50;  dur = 0.04; }
    osc.frequency.setValueAtTime(f, t0);
    if (sweep) osc.frequency.linearRampToValueAtTime(f + sweep, t0 + dur);
    g.gain.setValueAtTime(0.0, t0);
    g.gain.linearRampToValueAtTime(gain, t0 + 0.005);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    osc.start(t0);
    osc.stop(t0 + dur + 0.02);
  }

  // Light hum/loop synthesiser for ambient music (no external assets).
  hum({ root = 110, dur = 8, gain = 0.06 } = {}) {
    if (!this.unlocked) return null;
    const t0 = this.ctx.currentTime;
    const osc1 = this.ctx.createOscillator(); osc1.type = 'sine'; osc1.frequency.value = root;
    const osc2 = this.ctx.createOscillator(); osc2.type = 'sine'; osc2.frequency.value = root * 1.5;
    const lfo  = this.ctx.createOscillator(); lfo.type = 'sine';  lfo.frequency.value = 0.18;
    const lfoG = this.ctx.createGain(); lfoG.gain.value = 0.4;
    const g = this.ctx.createGain(); g.gain.value = gain;
    lfo.connect(lfoG); lfoG.connect(g.gain);
    osc1.connect(g); osc2.connect(g);
    g.connect(this.musicGain);
    osc1.start(t0); osc2.start(t0); lfo.start(t0);
    osc1.stop(t0 + dur); osc2.stop(t0 + dur); lfo.stop(t0 + dur);
    return { osc1, osc2, g };
  }

  async loadSample(id, url) {
    if (!this.unlocked) await new Promise(r => addEventListener('pointerdown', r, { once: true }));
    const buf = await fetch(url).then(r => r.arrayBuffer()).then(b => this.ctx.decodeAudioData(b));
    this.samples.set(id, buf);
    return buf;
  }

  play(id, { gain = 1, rate = 1, loop = false } = {}) {
    if (!this.unlocked) return null;
    const buf = this.samples.get(id);
    if (!buf) return null;
    const src = this.ctx.createBufferSource();
    src.buffer = buf;
    src.playbackRate.value = rate;
    src.loop = loop;
    const g = this.ctx.createGain();
    g.gain.value = gain;
    src.connect(g);
    g.connect(this.sfxGain);
    src.start();
    return src;
  }
}
