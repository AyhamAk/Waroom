// Trails — ribbon trails behind fast-moving objects.
// Usage:
//   const trail = engine.trails.create(mesh, { color: 0xff2244, length: 20, width: 0.25 });
//   // each frame, trail updates automatically via engine update loop.
//   trail.destroy(); // when entity dies

import * as THREE from 'three';

class Trail {
  constructor(scene, target, { color = 0xffffff, length = 24, width = 0.2, opacity = 0.7 } = {}) {
    this.target = target;
    this.length = length;
    this.points = [];
    this._dead = false;

    const positions = new Float32Array(length * 6);  // 2 verts per segment × 3 floats
    const alphas    = new Float32Array(length * 2);

    this.geo = new THREE.BufferGeometry();
    this.geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    this.geo.setAttribute('alpha',    new THREE.BufferAttribute(alphas, 1));
    this.geo.setDrawRange(0, 0);

    this.mat = new THREE.ShaderMaterial({
      uniforms: { uColor: { value: new THREE.Color(color) }, uOpacity: { value: opacity } },
      vertexShader: `
        attribute float alpha;
        varying float vAlpha;
        void main() { vAlpha = alpha; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }
      `,
      fragmentShader: `
        uniform vec3 uColor; uniform float uOpacity;
        varying float vAlpha;
        void main() { gl_FragColor = vec4(uColor, vAlpha * uOpacity); }
      `,
      transparent: true, depthWrite: false,
      blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
    });

    this.mesh = new THREE.Mesh(this.geo, this.mat);
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = 998;
    this._width = width;
    this._scene = scene;
    scene.add(this.mesh);
  }

  update(camera) {
    if (this._dead) return;
    const pos = this.target.getWorldPosition(new THREE.Vector3());
    this.points.unshift(pos.clone());
    if (this.points.length > this.length) this.points.pop();

    const n = this.points.length;
    if (n < 2) return;

    const right = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0);
    const posArr = this.geo.attributes.position.array;
    const alpArr = this.geo.attributes.alpha.array;

    for (let i = 0; i < n; i++) {
      const t = 1 - i / (n - 1);
      const w = this._width * t;
      const p = this.points[i];
      const r = right.clone().multiplyScalar(w * 0.5);
      const idx = i * 6;
      posArr[idx+0] = p.x - r.x; posArr[idx+1] = p.y - r.y; posArr[idx+2] = p.z - r.z;
      posArr[idx+3] = p.x + r.x; posArr[idx+4] = p.y + r.y; posArr[idx+5] = p.z + r.z;
      alpArr[i*2+0] = alpArr[i*2+1] = t;
    }

    const indices = [];
    for (let i = 0; i < n - 1; i++) {
      const a = i*2, b = i*2+1, c = i*2+2, d = i*2+3;
      indices.push(a,b,c, b,d,c);
    }
    this.geo.setIndex(indices);
    this.geo.attributes.position.needsUpdate = true;
    this.geo.attributes.alpha.needsUpdate = true;
    this.geo.setDrawRange(0, indices.length);
  }

  destroy() {
    this._dead = true;
    this._scene.remove(this.mesh);
    this.geo.dispose();
    this.mat.dispose();
  }
}

export class Trails {
  constructor(engine) {
    this.engine = engine;
    this._trails = new Set();
  }

  create(mesh, opts = {}) {
    const t = new Trail(this.engine.renderer.scene, mesh, opts);
    this._trails.add(t);
    return t;
  }

  update() {
    const cam = this.engine.renderer.camera;
    for (const t of this._trails) {
      if (t._dead) { this._trails.delete(t); continue; }
      t.update(cam);
    }
  }
}
