// Lighting — HDRI loader, procedural sky, sun + CSM cascaded shadows,
// fog presets. Tech-Art picks the preset; the runtime wires it.

import * as THREE from 'three';
import { RGBELoader } from 'three/examples/jsm/loaders/RGBELoader.js';
import { Sky } from 'three/examples/jsm/objects/Sky.js';
import { CSM } from 'three/examples/jsm/csm/CSM.js';

// HDRI catalog — Poly Haven CC0 HDRIs, served from the polyhaven CDN. Tech-
// Art picks one of these names; the runtime loads it. They are 1k-2k EXRs
// so they are fast to fetch and PMREM filtering is cheap on a modern GPU.
export const HDRI_CATALOG = {
  studio_small_03:    'https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/1k/studio_small_03_1k.hdr',
  kloofendal_43d_clear:'https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/1k/kloofendal_43d_clear_1k.hdr',
  industrial_sunset:  'https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/1k/industrial_sunset_02_puresky_1k.hdr',
  moonless_golf:      'https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/1k/moonless_golf_1k.hdr',
  satara_night:       'https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/1k/satara_night_1k.hdr',
  blue_studio:        'https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/1k/qwantani_dusk_2_1k.hdr',
  forest_grove:       'https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/1k/forest_grove_1k.hdr',
  warehouse:          'https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/1k/empty_warehouse_01_1k.hdr',
};

// Lighting presets — exposure, sun direction, fog defaults. Tech-Art names
// one of these; the runtime resolves it to concrete numbers.
export const LIGHTING_PRESETS = {
  warm_outdoor_skybox: {
    hdri: 'kloofendal_43d_clear', use_sky: true,
    sun_direction: [0.4, 0.7, 0.3], sun_intensity: 3.5, sun_color: 0xfff1d6,
    fill_intensity: 0.25, fill_sky: 0xa0c4ff, fill_ground: 0x402218,
    exposure: 1.05, background_blur: 0.0,
    fog: { type: 'exp2', color: 0xb0c4d8, density: 0.012 },
    sky_params: { turbidity: 4, rayleigh: 1.6, mieCoefficient: 0.005, mieDirectionalG: 0.85 },
  },
  golden_hour_outdoor: {
    hdri: 'industrial_sunset', use_sky: true,
    sun_direction: [0.35, 0.18, 0.4], sun_intensity: 4.5, sun_color: 0xffb070,
    fill_intensity: 0.3, fill_sky: 0xffc090, fill_ground: 0x301810,
    exposure: 1.1, background_blur: 0.06,
    fog: { type: 'exp2', color: 0xf3a578, density: 0.008 },
    sky_params: { turbidity: 8, rayleigh: 3, mieCoefficient: 0.008, mieDirectionalG: 0.95 },
  },
  moody_industrial: {
    hdri: 'warehouse', use_sky: false,
    sun_direction: [-0.3, 0.55, -0.4], sun_intensity: 1.8, sun_color: 0xffd0a8,
    fill_intensity: 0.18, fill_sky: 0x556070, fill_ground: 0x101012,
    exposure: 0.85, background_blur: 0.4,
    fog: { type: 'exp2', color: 0x1a1d22, density: 0.045 },
  },
  stylized_topdown_punch: {
    hdri: 'studio_small_03', use_sky: false,
    sun_direction: [0.5, 1.0, 0.3], sun_intensity: 4.5, sun_color: 0xffffff,
    fill_intensity: 0.45, fill_sky: 0xffd2ff, fill_ground: 0x303060,
    exposure: 1.2, background_blur: 0.0,
    fog: { type: 'linear', color: 0x0a0a18, near: 30, far: 80 },
  },
  neon_night: {
    hdri: 'moonless_golf', use_sky: false,
    sun_direction: [0.4, 0.6, 0.3], sun_intensity: 0.6, sun_color: 0x6088ff,
    fill_intensity: 0.5, fill_sky: 0xff00aa, fill_ground: 0x0040ff,
    exposure: 1.4, background_blur: 0.5,
    fog: { type: 'exp2', color: 0x10042a, density: 0.03 },
  },
  studio_neutral: {
    hdri: 'studio_small_03', use_sky: false,
    sun_direction: [0.3, 0.7, 0.5], sun_intensity: 2.5, sun_color: 0xffffff,
    fill_intensity: 0.4, fill_sky: 0xffffff, fill_ground: 0x404040,
    exposure: 1.0, background_blur: 0.0,
    fog: { type: 'none' },
  },
};

export class Lighting {
  constructor(engine) {
    this.engine = engine;
    this.scene = engine.renderer.scene;
    this.renderer = engine.renderer.three;
    this.camera = engine.renderer.camera;
    this.sun = null;
    this.fill = null;
    this.sky = null;
    this.csm = null;
    this.envTexture = null;
    this._pmrem = new THREE.PMREMGenerator(this.renderer);
    this._rgbe = new RGBELoader();
  }

  // Apply a preset by name (or a custom config object). Async because HDRI
  // load is non-blocking — caller can await preload().
  async applyPreset(presetOrName) {
    const cfg = (typeof presetOrName === 'string')
      ? (LIGHTING_PRESETS[presetOrName] || LIGHTING_PRESETS.studio_neutral)
      : presetOrName;

    this._clear();

    // Exposure first.
    this.renderer.toneMappingExposure = cfg.exposure ?? 1.0;

    // HDRI.
    if (cfg.hdri && HDRI_CATALOG[cfg.hdri]) {
      try {
        const hdr = await this._rgbe.loadAsync(HDRI_CATALOG[cfg.hdri]);
        const env = this._pmrem.fromEquirectangular(hdr).texture;
        this.scene.environment = env;
        this.envTexture = env;
        if (cfg.use_sky) {
          // Sky shader paints the background; HDRI still drives reflections.
        } else {
          // Use a blurred HDRI as background.
          this.scene.background = (cfg.background_blur > 0)
            ? this._blurredEquirect(hdr, cfg.background_blur)
            : env;
        }
        hdr.dispose();
      } catch (e) {
        console.warn('HDRI load failed, falling back', e);
      }
    }

    // Sky shader (procedural atmosphere).
    if (cfg.use_sky) {
      this.sky = new Sky();
      this.sky.scale.setScalar(450000);
      const u = this.sky.material.uniforms;
      const sp = cfg.sky_params || {};
      u.turbidity.value = sp.turbidity ?? 6;
      u.rayleigh.value = sp.rayleigh ?? 2;
      u.mieCoefficient.value = sp.mieCoefficient ?? 0.005;
      u.mieDirectionalG.value = sp.mieDirectionalG ?? 0.9;
      const sun = new THREE.Vector3(...cfg.sun_direction).normalize();
      u.sunPosition.value.copy(sun);
      this.scene.add(this.sky);
    }

    // Sun (directional) — use CSM if cascades are enabled, else single shadow camera.
    const sunDir = new THREE.Vector3(...cfg.sun_direction).normalize();
    if (cfg.use_csm) {
      this.csm = new CSM({
        maxFar: cfg.csm_max_far ?? 100,
        cascades: cfg.csm_cascades ?? 3,
        shadowMapSize: cfg.csm_shadow_size ?? 2048,
        lightDirection: sunDir.clone().multiplyScalar(-1),
        lightIntensity: cfg.sun_intensity ?? 3,
        lightColor: new THREE.Color(cfg.sun_color ?? 0xffffff),
        camera: this.camera,
        parent: this.scene,
        mode: 'practical',
      });
      this.csm.fade = true;
    } else {
      const sun = new THREE.DirectionalLight(cfg.sun_color ?? 0xffffff, cfg.sun_intensity ?? 3);
      sun.position.copy(sunDir.clone().multiplyScalar(60));
      sun.target.position.set(0, 0, 0);
      this.scene.add(sun.target);
      sun.castShadow = true;
      const sz = 30;
      sun.shadow.camera.left = -sz; sun.shadow.camera.right = sz;
      sun.shadow.camera.top = sz; sun.shadow.camera.bottom = -sz;
      sun.shadow.camera.near = 0.5; sun.shadow.camera.far = 120;
      sun.shadow.mapSize.set(2048, 2048);
      sun.shadow.bias = -0.00015;
      sun.shadow.normalBias = 0.025;
      this.scene.add(sun);
      this.sun = sun;
    }

    // Hemisphere fill — gives ambient bounce a colour story.
    this.fill = new THREE.HemisphereLight(
      cfg.fill_sky ?? 0xa0c4ff,
      cfg.fill_ground ?? 0x101010,
      cfg.fill_intensity ?? 0.3,
    );
    this.scene.add(this.fill);

    // Fog.
    this._applyFog(cfg.fog);
  }

  _applyFog(fog) {
    if (!fog || fog.type === 'none') {
      this.scene.fog = null;
      return;
    }
    if (fog.type === 'exp2') {
      this.scene.fog = new THREE.FogExp2(fog.color ?? 0x202028, fog.density ?? 0.02);
    } else {
      this.scene.fog = new THREE.Fog(fog.color ?? 0x202028, fog.near ?? 30, fog.far ?? 90);
    }
  }

  _blurredEquirect(hdr, blur) {
    // Blur the HDRI for a soft background while keeping crisp reflections.
    const blurred = this._pmrem.fromEquirectangular(hdr, blur).texture;
    return blurred;
  }

  _clear() {
    if (this.csm) { this.csm.dispose?.(); this.csm = null; }
    if (this.sun) { this.scene.remove(this.sun); this.sun = null; }
    if (this.fill) { this.scene.remove(this.fill); this.fill = null; }
    if (this.sky) { this.scene.remove(this.sky); this.sky = null; }
    this.scene.fog = null;
    // Don't clear environment until a new one is ready (avoids a frame of black).
  }

  // Hook the engine update loop — CSM needs per-frame camera updates.
  update() {
    if (this.csm) this.csm.update();
  }

  // Make a material respect CSM cascades. Gameplay code calls this after
  // creating Standard/Physical materials at runtime if CSM is active.
  registerMaterial(material) {
    if (this.csm) this.csm.setupMaterial(material);
  }
}
