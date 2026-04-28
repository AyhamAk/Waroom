// Physics — light kinematic helpers. Real rigid-body physics (Rapier or
// cannon-es) can be plugged in by the gameplay programmer when needed.
// For most arcade games this is all you need: AABB sweep + ground check.

import * as THREE from 'three';

export class Physics {
  constructor({ gravity = [0, -25, 0] } = {}) {
    this.gravity = new THREE.Vector3(...gravity);
    this.bodies = [];
    this.colliders = [];
  }

  addBody(body) {
    // body: { position: Vector3, velocity: Vector3, radius:number, height:number, onGround:bool }
    this.bodies.push(body);
    return body;
  }

  addStatic(box) {
    // box: { min: Vector3, max: Vector3 }
    this.colliders.push(box);
    return box;
  }

  // Apply gravity + sweep against statics. Use simple capsule-vs-AABB.
  step(dt) {
    for (const b of this.bodies) {
      if (!b.kinematic) {
        b.velocity.addScaledVector(this.gravity, dt);
      }
      b.onGround = false;
      const next = b.position.clone().addScaledVector(b.velocity, dt);

      // Ground plane fallback at y=0 if no static collider beneath.
      if (next.y - (b.height || 1) * 0.5 < 0) {
        next.y = (b.height || 1) * 0.5;
        if (b.velocity.y < 0) b.velocity.y = 0;
        b.onGround = true;
      }

      // AABB collision response (axis-by-axis).
      for (const c of this.colliders) {
        const minX = c.min.x - (b.radius || 0.5);
        const maxX = c.max.x + (b.radius || 0.5);
        const minZ = c.min.z - (b.radius || 0.5);
        const maxZ = c.max.z + (b.radius || 0.5);
        const minY = c.min.y - (b.height || 1) * 0.5;
        const maxY = c.max.y + (b.height || 1) * 0.5;
        if (next.x > minX && next.x < maxX && next.z > minZ && next.z < maxZ && next.y > minY && next.y < maxY) {
          const overlap = {
            x: Math.min(next.x - minX, maxX - next.x),
            y: Math.min(next.y - minY, maxY - next.y),
            z: Math.min(next.z - minZ, maxZ - next.z),
          };
          const m = Math.min(overlap.x, overlap.y, overlap.z);
          if (m === overlap.y) {
            if (b.velocity.y < 0) {
              next.y = maxY;
              b.onGround = true;
            } else if (b.velocity.y > 0) {
              next.y = minY;
            }
            b.velocity.y = 0;
          } else if (m === overlap.x) {
            next.x = (next.x - minX < maxX - next.x) ? minX : maxX;
            b.velocity.x = 0;
          } else {
            next.z = (next.z - minZ < maxZ - next.z) ? minZ : maxZ;
            b.velocity.z = 0;
          }
        }
      }

      b.position.copy(next);
    }
  }

  // Useful for AI line-of-sight, projectile aim, etc.
  raycast(origin, direction, maxDist = 50) {
    const ray = new THREE.Ray(origin, direction.clone().normalize());
    let hit = null;
    let bestT = maxDist;
    const tmp = new THREE.Vector3();
    for (const c of this.colliders) {
      const box = new THREE.Box3(c.min, c.max);
      if (ray.intersectBox(box, tmp)) {
        const d = tmp.distanceTo(origin);
        if (d < bestT) { bestT = d; hit = { point: tmp.clone(), distance: d, collider: c }; }
      }
    }
    return hit;
  }
}
