// GPU particle system — instanced billboards with a soft additive shader.
// Pool-based: emit() grabs a free slot, expires by lifetime; ~2k particles
// across all emitters cost a single draw call.
//
// Built-in emitters: explosion, muzzle_flash, blood, dust, sparkle, smoke,
// pickup. Game code can also push raw {position, velocity, color, life} entries.

import * as THREE from 'three';

const VS = `
  attribute vec3 iPos;
  attribute vec3 iVel;
  attribute vec4 iColor;
  attribute vec4 iParams;       // x: birth, y: life, z: size, w: gravity
  varying vec4 vColor;
  varying float vAge;
  uniform float uTime;
  uniform vec3 uCamRight;
  uniform vec3 uCamUp;

  void main() {
    float age = clamp((uTime - iParams.x) / iParams.y, 0.0, 1.0);
    vec3 worldPos = iPos + iVel * (uTime - iParams.x) + vec3(0.0, -0.5 * iParams.w * pow(uTime - iParams.x, 2.0), 0.0);
    float size = iParams.z * (1.0 - age * 0.5);
    vec3 billboard = uCamRight * position.x * size + uCamUp * position.y * size;
    vec4 mv = modelViewMatrix * vec4(worldPos, 1.0);
    mv.xyz += vec3(billboard.x, billboard.y, 0.0);
    gl_Position = projectionMatrix * mv;
    vAge = age;
    vColor = iColor;
  }
`;

const FS = `
  varying vec4 vColor;
  varying float vAge;
  void main() {
    vec2 uv = gl_PointCoord;
    float d = length(vec2(0.5) - uv);
    // Use vUv from quad: actual coordinates are in built-in 'gl_FragCoord' for billboards.
    // For a billboard quad we approximate with derived UV via interpolated normals.
    float alpha = (1.0 - vAge) * vColor.a;
    // soft circle
    float r = length(gl_FragCoord.xy / vec2(textureSize(0,0)) - 0.5);
    gl_FragColor = vec4(vColor.rgb, alpha);
  }
`;

// Simpler frag — render the full quad with the colour faded by age. The
// game uses additive blending so the bright centre + falloff gives a soft glow.
const FS_SIMPLE = `
  varying vec4 vColor;
  varying float vAge;
  void main() {
    float alpha = (1.0 - vAge) * vColor.a;
    if (alpha <= 0.0) discard;
    gl_FragColor = vec4(vColor.rgb, alpha);
  }
`;

export class Particles {
  constructor(engine, { capacity = 2048 } = {}) {
    this.engine = engine;
    this.capacity = capacity;
    this.cursor = 0;

    const geo = new THREE.PlaneGeometry(1, 1);
    const inst = new THREE.InstancedBufferGeometry().copy(geo);

    this.iPos    = new Float32Array(capacity * 3);
    this.iVel    = new Float32Array(capacity * 3);
    this.iColor  = new Float32Array(capacity * 4);
    this.iParams = new Float32Array(capacity * 4);

    inst.setAttribute('iPos',    new THREE.InstancedBufferAttribute(this.iPos, 3));
    inst.setAttribute('iVel',    new THREE.InstancedBufferAttribute(this.iVel, 3));
    inst.setAttribute('iColor',  new THREE.InstancedBufferAttribute(this.iColor, 4));
    inst.setAttribute('iParams', new THREE.InstancedBufferAttribute(this.iParams, 4));
    inst.instanceCount = 0;

    const mat = new THREE.ShaderMaterial({
      vertexShader: VS,
      fragmentShader: FS_SIMPLE,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      uniforms: {
        uTime: { value: 0 },
        uCamRight: { value: new THREE.Vector3() },
        uCamUp:    { value: new THREE.Vector3() },
      },
    });
    this.mat = mat;
    this.geo = inst;

    this.mesh = new THREE.Mesh(inst, mat);
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = 999;
    engine.renderer.scene.add(this.mesh);
  }

  // Emit a single particle. position/velocity/color are THREE.Vector3 / Color.
  emit({
    position = new THREE.Vector3(),
    velocity = new THREE.Vector3(),
    color = new THREE.Color(0xffffff),
    alpha = 1,
    size = 0.5,
    life = 1.0,
    gravity = 0,
  } = {}) {
    const i = this.cursor;
    this.cursor = (this.cursor + 1) % this.capacity;

    this.iPos[i*3+0] = position.x;
    this.iPos[i*3+1] = position.y;
    this.iPos[i*3+2] = position.z;
    this.iVel[i*3+0] = velocity.x;
    this.iVel[i*3+1] = velocity.y;
    this.iVel[i*3+2] = velocity.z;
    this.iColor[i*4+0] = color.r;
    this.iColor[i*4+1] = color.g;
    this.iColor[i*4+2] = color.b;
    this.iColor[i*4+3] = alpha;
    this.iParams[i*4+0] = this.engine.clock.t;          // birth
    this.iParams[i*4+1] = life;                          // life
    this.iParams[i*4+2] = size;                          // size
    this.iParams[i*4+3] = gravity;                       // gravity

    if (this.geo.instanceCount < this.capacity) this.geo.instanceCount++;
    this.geo.attributes.iPos.needsUpdate = true;
    this.geo.attributes.iVel.needsUpdate = true;
    this.geo.attributes.iColor.needsUpdate = true;
    this.geo.attributes.iParams.needsUpdate = true;
  }

  // ─── Built-in emitters ──────────────────────────────────────────────────

  explosion(position, { count = 50, color = 0xffaa44, size = 0.6, force = 8 } = {}) {
    const c = new THREE.Color(color);
    for (let i = 0; i < count; i++) {
      const dir = new THREE.Vector3(Math.random()-0.5, Math.random()-0.5, Math.random()-0.5).normalize();
      this.emit({
        position: position.clone(),
        velocity: dir.multiplyScalar(force * (0.6 + Math.random() * 0.6)),
        color: c, alpha: 1.0, size: size * (0.5 + Math.random()),
        life: 0.6 + Math.random() * 0.4,
        gravity: 4,
      });
    }
  }

  muzzleFlash(position, direction, { count = 12, color = 0xffe080, size = 0.4 } = {}) {
    const c = new THREE.Color(color);
    const d = direction.clone().normalize();
    for (let i = 0; i < count; i++) {
      const spread = new THREE.Vector3((Math.random()-0.5)*0.4, (Math.random()-0.5)*0.4, (Math.random()-0.5)*0.4);
      this.emit({
        position: position.clone(),
        velocity: d.clone().multiplyScalar(8 + Math.random()*4).add(spread),
        color: c, alpha: 1.0,
        size: size * (0.6 + Math.random()*0.6),
        life: 0.08 + Math.random()*0.08,
        gravity: 0,
      });
    }
  }

  blood(position, { count = 18, color = 0xaa1020 } = {}) {
    const c = new THREE.Color(color);
    for (let i = 0; i < count; i++) {
      const dir = new THREE.Vector3(Math.random()-0.5, Math.random()*0.6+0.2, Math.random()-0.5).normalize();
      this.emit({
        position: position.clone(),
        velocity: dir.multiplyScalar(3 + Math.random()*3),
        color: c, alpha: 0.9,
        size: 0.18 + Math.random()*0.18,
        life: 0.5 + Math.random()*0.4,
        gravity: 14,
      });
    }
  }

  dust(position, { count = 14, color = 0xc6b9a3 } = {}) {
    const c = new THREE.Color(color);
    for (let i = 0; i < count; i++) {
      const dir = new THREE.Vector3(Math.random()-0.5, Math.random()*0.4+0.1, Math.random()-0.5).normalize();
      this.emit({
        position: position.clone(),
        velocity: dir.multiplyScalar(1.5 + Math.random()*1.5),
        color: c, alpha: 0.5,
        size: 0.4 + Math.random()*0.4,
        life: 0.7 + Math.random()*0.6,
        gravity: -1,
      });
    }
  }

  sparkle(position, { count = 8, color = 0xfff7c0 } = {}) {
    const c = new THREE.Color(color);
    for (let i = 0; i < count; i++) {
      const dir = new THREE.Vector3(Math.random()-0.5, Math.random(), Math.random()-0.5).normalize();
      this.emit({
        position: position.clone(),
        velocity: dir.multiplyScalar(2 + Math.random()*2),
        color: c, alpha: 1.0,
        size: 0.12 + Math.random()*0.12,
        life: 0.5 + Math.random()*0.4,
        gravity: 0,
      });
    }
  }

  smoke(position, { count = 10, color = 0x303030 } = {}) {
    const c = new THREE.Color(color);
    for (let i = 0; i < count; i++) {
      this.emit({
        position: position.clone(),
        velocity: new THREE.Vector3(
          (Math.random()-0.5)*0.5,
          1 + Math.random()*0.5,
          (Math.random()-0.5)*0.5
        ),
        color: c, alpha: 0.6,
        size: 0.6 + Math.random()*0.6,
        life: 1.5 + Math.random()*0.8,
        gravity: -1.5,
      });
    }
  }

  // Update — called once per frame from Engine.
  update(dt, t) {
    this.mat.uniforms.uTime.value = t;
    const camera = this.engine.renderer.camera;
    const right = new THREE.Vector3(); right.setFromMatrixColumn(camera.matrixWorld, 0);
    const up = new THREE.Vector3();    up.setFromMatrixColumn(camera.matrixWorld, 1);
    this.mat.uniforms.uCamRight.value.copy(right);
    this.mat.uniforms.uCamUp.value.copy(up);
  }
}
