// Placeholder game. Demonstrates the engine API end-to-end so you know
// the rendering pipeline is healthy on first boot. The Gameplay
// Programmer agent rewrites this file with real mechanics.

import * as THREE from 'three';

export class Game {
  constructor(engine) {
    this.engine = engine;
    this.scene = engine.renderer.scene;
    this.camera = engine.renderer.camera;
    this.objects = [];
    this._lastSpark = 0;
  }

  async preload() {
    // Engine Engineer + Tech-Art usually pick presets. We default to a
    // warm outdoor look so the placeholder demo is recognisable.
    await this.engine.applyLightingPreset('warm_outdoor_skybox');
    this.engine.enablePostFX('filmic_soft');
  }

  start() {
    // Ground plane — large, slightly rough so reflections aren't sharp.
    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(80, 80),
      new THREE.MeshStandardMaterial({ color: 0x222431, roughness: 0.85, metalness: 0.0 })
    );
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    this.engine.lighting?.registerMaterial?.(ground.material);
    this.scene.add(ground);

    // A cluster of metal/plastic primitives to sell PBR + IBL + SSAO.
    const layout = [
      { kind: 'sphere',   pos: [-3.5, 0.7, 0],  color: 0xff5577, m: 0.0, r: 0.25 },
      { kind: 'cube',     pos: [-1.5, 0.6, 0],  color: 0x6e8efb, m: 0.05, r: 0.45, size: 1.2 },
      { kind: 'cylinder', pos: [ 0.5, 0.7, 0],  color: 0xffd66b, m: 0.3, r: 0.35, size: 1.4 },
      { kind: 'torus',    pos: [ 2.5, 0.6, 0],  color: 0x57e2c0, m: 0.85, r: 0.18, size: 1.6 },
      { kind: 'cube',     pos: [-2.5, 0.4, 2.5], color: 0x8a3cff, m: 0.6, r: 0.25, size: 0.8 },
      { kind: 'sphere',   pos: [ 1.5, 0.5, 2.5], color: 0xffffff, m: 0.0, r: 0.05, size: 1.0 },
    ];
    for (const o of layout) {
      const mesh = this.engine.assets.primitive(o.kind, {
        size: o.size ?? 1, color: o.color, metalness: o.m, roughness: o.r,
      });
      mesh.position.set(...o.pos);
      this.engine.lighting?.registerMaterial?.(mesh.material);
      this.scene.add(mesh);
      this.objects.push({ mesh, kind: o.kind });
    }

    // A glowing pillar to show emissive + bloom.
    const pillar = this.engine.assets.primitive('cylinder', {
      size: 1, color: 0x000000, metalness: 0.0, roughness: 0.4,
      emissive: 0xff5500, emissiveIntensity: 4.0,
    });
    pillar.scale.set(0.25, 4, 0.25);
    pillar.position.set(0, 2, -3);
    this.engine.lighting?.registerMaterial?.(pillar.material);
    this.scene.add(pillar);
    this.pillar = pillar;

    // Camera — slow orbit so the lighting reads.
    this.camera.position.set(7, 4.5, 8);
    this.camera.lookAt(0, 0.7, 0);

    this.engine.ui.text('tl', 'WarRoom Engine — placeholder scene. Replace with your gameplay.');
  }

  update(dt, t) {
    // Slow camera orbit.
    const r = 9, y = 4.5;
    this.camera.position.set(Math.cos(t * 0.18) * r, y + Math.sin(t * 0.4) * 0.3, Math.sin(t * 0.18) * r);
    this.camera.lookAt(0, 0.7, 0);

    // Spin and bob.
    for (let i = 0; i < this.objects.length; i++) {
      const o = this.objects[i];
      o.mesh.rotation.y += dt * (0.4 + i * 0.05);
      o.mesh.rotation.x = Math.sin(t * (0.6 + i * 0.1)) * 0.12;
    }

    // Sparkle particles at the pillar so the bloom + grain reads.
    if (t - this._lastSpark > 0.05) {
      this._lastSpark = t;
      this.engine.particles?.sparkle(
        new THREE.Vector3(0, 3.5, -3),
        { count: 3, color: 0xffaa44 }
      );
    }
  }
}
