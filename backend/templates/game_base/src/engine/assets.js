// Assets — registry + loaders for glTF, KTX2 textures, PBR texture sets,
// and helpers for InstancedMesh / LOD groups. The Asset Lead's manifest
// drives everything; the gameplay programmer only ever asks for ids.

import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader.js';
import { KTX2Loader } from 'three/examples/jsm/loaders/KTX2Loader.js';
import { MeshoptDecoder } from 'three/examples/jsm/libs/meshopt_decoder.module.js';
import { SkeletonUtils } from 'three/examples/jsm/utils/SkeletonUtils.js';
import { Anim } from './animation.js';

export class Assets {
  constructor() {
    this.cache = new Map();          // gltf assets
    this.textures = new Map();       // texture sets
    this._tex = new THREE.TextureLoader();

    this.gltf = new GLTFLoader();
    const draco = new DRACOLoader();
    draco.setDecoderPath('https://www.gstatic.com/draco/versioned/decoders/1.5.7/');
    this.gltf.setDRACOLoader(draco);
    this.gltf.setMeshoptDecoder(MeshoptDecoder);
  }

  attachKtx2(renderer) {
    const ktx2 = new KTX2Loader()
      .setTranscoderPath('https://unpkg.com/three@0.169.0/examples/jsm/libs/basis/')
      .detectSupport(renderer);
    this.gltf.setKTX2Loader(ktx2);
  }

  // ─── glTF ───────────────────────────────────────────────────────────────

  async loadGltf(id, url) {
    const gltf = await this.gltf.loadAsync(url);
    gltf.scene.traverse((o) => {
      if (o.isMesh) {
        o.castShadow = true;
        o.receiveShadow = true;
        if (o.material) {
          // Sharper textures.
          if (o.material.map) o.material.map.anisotropy = 8;
        }
      }
    });
    this.cache.set(id, gltf);
    return gltf;
  }

  // Spawn a clone of a loaded glTF — supports skinned animation. Returns
  // {scene, anim} where anim is an Anim wrapper if the glTF has clips.
  spawn(id) {
    const gltf = this.cache.get(id);
    if (!gltf) throw new Error(`Asset not loaded: ${id}`);
    const clone = SkeletonUtils.clone(gltf.scene);
    let anim = null;
    if (gltf.animations && gltf.animations.length) {
      anim = new Anim(clone, gltf.animations);
    }
    return { scene: clone, anim, source: gltf };
  }

  get(id) { return this.cache.get(id); }
  has(id) { return this.cache.has(id); }

  // ─── Procedural primitives ──────────────────────────────────────────────

  primitive(kind = 'cube', {
    size = 1,
    color = 0x6e8efb,
    metalness = 0,
    roughness = 0.6,
    emissive = 0x000000,
    emissiveIntensity = 0,
  } = {}) {
    let geo;
    if (kind === 'cube')      geo = new THREE.BoxGeometry(size, size, size);
    else if (kind === 'sphere')   geo = new THREE.SphereGeometry(size * 0.5, 32, 24);
    else if (kind === 'cylinder') geo = new THREE.CylinderGeometry(size * 0.5, size * 0.5, size, 32);
    else if (kind === 'capsule')  geo = new THREE.CapsuleGeometry(size * 0.4, size * 0.6, 8, 16);
    else if (kind === 'cone')     geo = new THREE.ConeGeometry(size * 0.5, size, 32);
    else if (kind === 'torus')    geo = new THREE.TorusGeometry(size * 0.5, size * 0.15, 16, 48);
    else if (kind === 'plane')    geo = new THREE.PlaneGeometry(size, size);
    else                          geo = new THREE.BoxGeometry(size, size, size);

    const mat = new THREE.MeshStandardMaterial({
      color, metalness, roughness, emissive, emissiveIntensity,
    });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    return mesh;
  }

  // ─── PBR texture sets ───────────────────────────────────────────────────

  // Load a coordinated PBR texture set. URLs default to the common Poly
  // Haven 1k naming; callers can override any slot.
  async loadTextureSet(id, urls = {}) {
    const out = {};
    const slots = ['map', 'normalMap', 'roughnessMap', 'metalnessMap', 'aoMap', 'displacementMap', 'emissiveMap'];
    await Promise.all(slots.map(async (slot) => {
      const url = urls[slot];
      if (!url) return;
      const tex = await this._tex.loadAsync(url);
      tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
      tex.anisotropy = 8;
      if (slot === 'map' || slot === 'emissiveMap') tex.colorSpace = THREE.SRGBColorSpace;
      out[slot] = tex;
    }));
    this.textures.set(id, out);
    return out;
  }

  makePBRMaterial(id, opts = {}) {
    const set = this.textures.get(id) || {};
    return new THREE.MeshStandardMaterial({
      color: opts.color ?? 0xffffff,
      metalness: opts.metalness ?? 0.0,
      roughness: opts.roughness ?? 0.85,
      ...set,
      normalScale: set.normalMap ? new THREE.Vector2(opts.normalScale ?? 1, opts.normalScale ?? 1) : undefined,
    });
  }

  // ─── InstancedMesh for swarms / props (huge perf win) ───────────────────

  instanced(geometry, material, count) {
    const mesh = new THREE.InstancedMesh(geometry, material, count);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    return mesh;
  }

  // ─── LOD helper ─────────────────────────────────────────────────────────

  lod(levels = []) {
    // levels: [{ object, distance }, ...] ordered nearest → farthest.
    const lod = new THREE.LOD();
    for (const lv of levels) {
      lod.addLevel(lv.object, lv.distance);
    }
    return lod;
  }
}
