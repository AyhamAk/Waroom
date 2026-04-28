// Decals — projected geometry (DecalGeometry from three/examples) for
// bullet holes, scorch marks, blood splats, footprints. Self-managing
// pool that disposes the oldest when it exceeds capacity.

import * as THREE from 'three';
import { DecalGeometry } from 'three/examples/jsm/geometries/DecalGeometry.js';

const _orientation = new THREE.Euler();
const _matrix = new THREE.Matrix4();

export class Decals {
  constructor(engine, { capacity = 64 } = {}) {
    this.engine = engine;
    this.scene = engine.renderer.scene;
    this.capacity = capacity;
    this.pool = [];   // ring buffer of THREE.Mesh
  }

  // Create a decal projected onto `mesh` at `position`, oriented to surface
  // normal. Material defaults give a circular soft mark; override material
  // for textured marks.
  spray(mesh, position, normal, {
    size = 0.5,
    color = 0x000000,
    opacity = 0.85,
    roughness = 1.0,
    metalness = 0,
    material = null,
  } = {}) {
    if (!mesh) return null;

    // Decal orientation: align to surface normal, random roll.
    const upDir = new THREE.Vector3(...normal).normalize();
    const helper = new THREE.Object3D();
    helper.position.copy(position);
    helper.lookAt(position.clone().add(upDir));
    helper.rotation.z = Math.random() * Math.PI * 2;

    const sz = new THREE.Vector3(size, size, size);
    const geo = new DecalGeometry(mesh, position, helper.rotation, sz);
    const mat = material ?? new THREE.MeshStandardMaterial({
      color,
      transparent: true,
      opacity,
      roughness,
      metalness,
      polygonOffset: true,
      polygonOffsetFactor: -4,
      depthWrite: false,
    });
    const decalMesh = new THREE.Mesh(geo, mat);
    decalMesh.receiveShadow = false;
    decalMesh.castShadow = false;
    this.scene.add(decalMesh);

    this.pool.push(decalMesh);
    while (this.pool.length > this.capacity) {
      const old = this.pool.shift();
      this.scene.remove(old);
      old.geometry.dispose();
      if (Array.isArray(old.material)) old.material.forEach(m => m.dispose?.());
      else old.material.dispose?.();
    }
    return decalMesh;
  }

  clear() {
    for (const m of this.pool) {
      this.scene.remove(m);
      m.geometry.dispose();
      if (Array.isArray(m.material)) m.material.forEach(mm => mm.dispose?.());
      else m.material.dispose?.();
    }
    this.pool = [];
  }
}
