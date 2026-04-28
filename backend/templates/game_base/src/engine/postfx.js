// PostFX — full cinematic stack:
//   render → SSAO → bloom → bokeh DOF → FXAA → chromatic aberration →
//   film grain → vignette → output (sRGB).
//
// Tech-Art picks one preset by name; per-effect strengths can also be
// overridden at runtime via setUniforms().
//
// Effects are toggleable so we can disable expensive passes (SSAO, DOF,
// TAA) on lower-end devices via engine.postfx.setQuality('low').

import * as THREE from 'three';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
import { SSAOPass } from 'three/examples/jsm/postprocessing/SSAOPass.js';
import { BokehPass } from 'three/examples/jsm/postprocessing/BokehPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';
import { ShaderPass } from 'three/examples/jsm/postprocessing/ShaderPass.js';
import { FXAAShader } from 'three/examples/jsm/shaders/FXAAShader.js';

// ─── Custom shaders ──────────────────────────────────────────────────────────

const VIGNETTE_SHADER = {
  uniforms: {
    tDiffuse: { value: null },
    amount:   { value: 0.45 },
    softness: { value: 0.45 },
  },
  vertexShader: `
    varying vec2 vUv;
    void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }
  `,
  fragmentShader: `
    uniform sampler2D tDiffuse; uniform float amount; uniform float softness;
    varying vec2 vUv;
    void main() {
      vec4 c = texture2D(tDiffuse, vUv);
      vec2 uv = vUv - 0.5;
      float v = smoothstep(0.85, softness, length(uv));
      c.rgb *= mix(1.0, v, amount);
      gl_FragColor = c;
    }
  `,
};

const CHROMATIC_ABERRATION_SHADER = {
  uniforms: {
    tDiffuse: { value: null },
    amount:   { value: 0.0025 },
  },
  vertexShader: `
    varying vec2 vUv;
    void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }
  `,
  fragmentShader: `
    uniform sampler2D tDiffuse; uniform float amount;
    varying vec2 vUv;
    void main() {
      vec2 dir = vUv - 0.5;
      float dist = length(dir);
      vec2 dn = dir / max(dist, 0.0001);
      float strength = amount * dist * 2.0;
      vec3 col;
      col.r = texture2D(tDiffuse, vUv - dn * strength * 1.0).r;
      col.g = texture2D(tDiffuse, vUv).g;
      col.b = texture2D(tDiffuse, vUv + dn * strength * 1.0).b;
      gl_FragColor = vec4(col, texture2D(tDiffuse, vUv).a);
    }
  `,
};

// FilmPass replacement — works post-OutputPass without colour drift.
const FILM_GRAIN_SHADER = {
  uniforms: {
    tDiffuse:    { value: null },
    time:        { value: 0 },
    nIntensity:  { value: 0.18 },   // grain
    sIntensity:  { value: 0.06 },   // scanline
    sCount:      { value: 4096 },
    grayscale:   { value: 0 },
  },
  vertexShader: `
    varying vec2 vUv;
    void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }
  `,
  fragmentShader: `
    uniform sampler2D tDiffuse;
    uniform float time, nIntensity, sIntensity, sCount, grayscale;
    varying vec2 vUv;
    float rand(vec2 co) { return fract(sin(dot(co.xy, vec2(12.9898,78.233))) * 43758.5453); }
    void main() {
      vec4 c = texture2D(tDiffuse, vUv);
      float grain = (rand(vUv + time * 0.001) - 0.5) * nIntensity;
      c.rgb += grain;
      float s = sin(vUv.y * sCount) * sIntensity;
      c.rgb -= s;
      if (grayscale > 0.5) {
        float g = dot(c.rgb, vec3(0.299, 0.587, 0.114));
        c.rgb = vec3(g);
      }
      gl_FragColor = c;
    }
  `,
};

// ─── Presets ─────────────────────────────────────────────────────────────────

const PRESETS = {
  standard: {
    bloom: 0.6, threshold: 0.85, bloom_radius: 0.4,
    vignette: 0.4, softness: 0.45,
    ca: 0.0015, grain: 0.10, scanline: 0.0,
    ssao: { enabled: true, kernel: 16, radius: 0.6, minDist: 0.005, maxDist: 0.06 },
    dof:  { enabled: false, focus: 8, aperture: 0.0002, maxblur: 0.005 },
    fxaa: true,
  },
  vibrant_action: {
    bloom: 1.0, threshold: 0.65, bloom_radius: 0.6,
    vignette: 0.30, softness: 0.5,
    ca: 0.003, grain: 0.06, scanline: 0.0,
    ssao: { enabled: true, kernel: 16, radius: 0.5, minDist: 0.005, maxDist: 0.05 },
    dof:  { enabled: false },
    fxaa: true,
  },
  cinematic_grit: {
    bloom: 0.5, threshold: 0.9, bloom_radius: 0.5,
    vignette: 0.65, softness: 0.4,
    ca: 0.004, grain: 0.25, scanline: 0.04,
    ssao: { enabled: true, kernel: 24, radius: 0.7, minDist: 0.01, maxDist: 0.08 },
    dof:  { enabled: true, focus: 10, aperture: 0.0003, maxblur: 0.008 },
    fxaa: true,
  },
  filmic_soft: {
    bloom: 0.75, threshold: 0.8, bloom_radius: 0.5,
    vignette: 0.40, softness: 0.45,
    ca: 0.002, grain: 0.10, scanline: 0.0,
    ssao: { enabled: true, kernel: 16, radius: 0.6, minDist: 0.005, maxDist: 0.06 },
    dof:  { enabled: true, focus: 12, aperture: 0.00025, maxblur: 0.006 },
    fxaa: true,
  },
  filmic_dreamy: {
    bloom: 1.4, threshold: 0.55, bloom_radius: 0.85,
    vignette: 0.50, softness: 0.5,
    ca: 0.0035, grain: 0.14, scanline: 0.0,
    ssao: { enabled: true, kernel: 12, radius: 0.7, minDist: 0.005, maxDist: 0.08 },
    dof:  { enabled: true, focus: 8, aperture: 0.00045, maxblur: 0.012 },
    fxaa: true,
  },
  warm_outdoor_skybox: {
    bloom: 0.55, threshold: 0.85, bloom_radius: 0.5,
    vignette: 0.30, softness: 0.5,
    ca: 0.0015, grain: 0.06, scanline: 0.0,
    ssao: { enabled: true, kernel: 16, radius: 0.5, minDist: 0.005, maxDist: 0.05 },
    dof:  { enabled: false },
    fxaa: true,
  },
  moody_industrial: {
    bloom: 0.5, threshold: 0.8, bloom_radius: 0.55,
    vignette: 0.7, softness: 0.4,
    ca: 0.003, grain: 0.18, scanline: 0.02,
    ssao: { enabled: true, kernel: 24, radius: 0.7, minDist: 0.01, maxDist: 0.08 },
    dof:  { enabled: true, focus: 8, aperture: 0.0004, maxblur: 0.01 },
    fxaa: true,
  },
  stylized_topdown_punch: {
    bloom: 1.1, threshold: 0.7, bloom_radius: 0.6,
    vignette: 0.25, softness: 0.55,
    ca: 0.001, grain: 0.04, scanline: 0.0,
    ssao: { enabled: true, kernel: 12, radius: 0.4, minDist: 0.005, maxDist: 0.04 },
    dof:  { enabled: false },
    fxaa: true,
  },
  neon_night: {
    bloom: 1.6, threshold: 0.45, bloom_radius: 0.9,
    vignette: 0.45, softness: 0.5,
    ca: 0.005, grain: 0.10, scanline: 0.0,
    ssao: { enabled: false },
    dof:  { enabled: true, focus: 10, aperture: 0.0004, maxblur: 0.012 },
    fxaa: true,
  },
  retro_film: {
    bloom: 0.4, threshold: 0.9, bloom_radius: 0.4,
    vignette: 0.55, softness: 0.4,
    ca: 0.005, grain: 0.35, scanline: 0.08,
    ssao: { enabled: true, kernel: 12, radius: 0.5, minDist: 0.005, maxDist: 0.06 },
    dof:  { enabled: false },
    fxaa: true,
  },
  minimal: {
    bloom: 0.0, threshold: 1.0, bloom_radius: 0.4,
    vignette: 0.0, softness: 0.5,
    ca: 0.0, grain: 0.0, scanline: 0.0,
    ssao: { enabled: false },
    dof:  { enabled: false },
    fxaa: true,
  },
};

// ─── PostFX class ────────────────────────────────────────────────────────────

export class PostFX {
  constructor(engine, preset = 'standard') {
    this.engine = engine;
    const r = engine.renderer.three;
    const scene = engine.renderer.scene;
    const camera = engine.renderer.camera;
    const w = r.domElement.width, h = r.domElement.height;

    this.composer = new EffectComposer(r);
    this.composer.setSize(w, h);

    this.renderPass = new RenderPass(scene, camera);
    this.composer.addPass(this.renderPass);

    // SSAO — depth-aware, gives objects ground contact + interior shading.
    this.ssao = new SSAOPass(scene, camera, w, h);
    this.ssao.kernelRadius = 0.6;
    this.ssao.minDistance = 0.005;
    this.ssao.maxDistance = 0.06;
    this.composer.addPass(this.ssao);

    // Bloom.
    this.bloom = new UnrealBloomPass(new THREE.Vector2(w, h), 0.6, 0.4, 0.85);
    this.composer.addPass(this.bloom);

    // Bokeh DOF — disabled by default; presets enable it where it matters.
    this.bokeh = new BokehPass(scene, camera, {
      focus: 10, aperture: 0.0002, maxblur: 0.005, width: w, height: h,
    });
    this.bokeh.enabled = false;
    this.composer.addPass(this.bokeh);

    // FXAA — cheap edge cleanup. Runs before output to keep colours linear.
    this.fxaa = new ShaderPass(FXAAShader);
    this.fxaa.material.uniforms.resolution.value.set(1 / w, 1 / h);
    this.composer.addPass(this.fxaa);

    // Output (sRGB + tone-map). Everything below it is in sRGB display space.
    this.composer.addPass(new OutputPass());

    // Display-space passes (operate after tone-mapping for correct colour).
    this.chromaticAberration = new ShaderPass(CHROMATIC_ABERRATION_SHADER);
    this.composer.addPass(this.chromaticAberration);

    this.filmGrain = new ShaderPass(FILM_GRAIN_SHADER);
    this.composer.addPass(this.filmGrain);

    this.vignette = new ShaderPass(VIGNETTE_SHADER);
    this.composer.addPass(this.vignette);

    this.applyPreset(preset);

    addEventListener('resize', this._onResize, { passive: true });
  }

  _onResize = () => {
    const w = window.innerWidth, h = window.innerHeight;
    this.composer.setSize(w, h);
    this.ssao.setSize(w, h);
    this.bokeh.uniforms.aspect.value = w / h;
    this.fxaa.material.uniforms.resolution.value.set(1 / w, 1 / h);
  };

  applyPreset(name) {
    const p = PRESETS[name] || PRESETS.standard;

    this.bloom.strength = p.bloom;
    this.bloom.threshold = p.threshold;
    this.bloom.radius = p.bloom_radius ?? 0.4;

    this.vignette.uniforms.amount.value = p.vignette;
    this.vignette.uniforms.softness.value = p.softness ?? 0.45;

    this.chromaticAberration.uniforms.amount.value = p.ca ?? 0.002;

    this.filmGrain.uniforms.nIntensity.value = p.grain ?? 0.10;
    this.filmGrain.uniforms.sIntensity.value = p.scanline ?? 0.0;

    if (p.ssao && p.ssao.enabled) {
      this.ssao.enabled = true;
      this.ssao.kernelRadius = p.ssao.radius ?? 0.6;
      this.ssao.minDistance = p.ssao.minDist ?? 0.005;
      this.ssao.maxDistance = p.ssao.maxDist ?? 0.06;
    } else {
      this.ssao.enabled = false;
    }

    if (p.dof && p.dof.enabled) {
      this.bokeh.enabled = true;
      this.bokeh.uniforms.focus.value = p.dof.focus ?? 10;
      this.bokeh.uniforms.aperture.value = p.dof.aperture ?? 0.0002;
      this.bokeh.uniforms.maxblur.value = p.dof.maxblur ?? 0.005;
    } else {
      this.bokeh.enabled = false;
    }

    this.fxaa.enabled = p.fxaa !== false;
  }

  // Coarse quality knob — turn off the expensive screen-space passes.
  setQuality(level) {
    if (level === 'low') {
      this.ssao.enabled = false;
      this.bokeh.enabled = false;
      this.bloom.strength *= 0.4;
    } else if (level === 'medium') {
      this.bokeh.enabled = false;
    }
  }

  setFocus(distance) {
    if (this.bokeh) this.bokeh.uniforms.focus.value = distance;
  }

  // Game code calls this for explicit per-frame uniform updates (e.g. focus
  // tracks the player target dynamically).
  setUniforms(patch = {}) {
    if (patch.bloom != null) this.bloom.strength = patch.bloom;
    if (patch.ca != null) this.chromaticAberration.uniforms.amount.value = patch.ca;
    if (patch.vignette != null) this.vignette.uniforms.amount.value = patch.vignette;
    if (patch.grain != null) this.filmGrain.uniforms.nIntensity.value = patch.grain;
    if (patch.dof_focus != null) this.bokeh.uniforms.focus.value = patch.dof_focus;
    if (patch.dof_aperture != null) this.bokeh.uniforms.aperture.value = patch.dof_aperture;
  }

  render() {
    this.filmGrain.uniforms.time.value = performance.now();
    this.composer.render();
  }
}
