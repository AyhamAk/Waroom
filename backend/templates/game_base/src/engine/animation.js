// Animation — AnimationMixer wrapper with named clips + crossfade. Handles
// the common "set state and forget" loop you want for character anim
// (idle/walk/run/jump/fall/land/attack/hit/die).

import * as THREE from 'three';

export class Anim {
  constructor(rootObject, animations = []) {
    this.mixer = new THREE.AnimationMixer(rootObject);
    this.actions = new Map();
    this.current = null;
    for (const clip of animations) {
      const a = this.mixer.clipAction(clip);
      a.enabled = false;
      this.actions.set(clip.name, a);
    }
  }

  // Add or replace an action by name.
  add(name, clip) {
    const a = this.mixer.clipAction(clip);
    a.enabled = false;
    this.actions.set(name, a);
    return a;
  }

  // Play a named clip with a smooth crossfade from the current one.
  play(name, { fade = 0.25, loop = true, timeScale = 1.0, weight = 1.0 } = {}) {
    const next = this.actions.get(name);
    if (!next) return null;
    if (this.current === next && next.isRunning()) return next;

    next.reset();
    next.setLoop(loop ? THREE.LoopRepeat : THREE.LoopOnce, Infinity);
    next.clampWhenFinished = !loop;
    next.timeScale = timeScale;
    next.setEffectiveWeight(weight);
    next.enabled = true;
    next.play();

    if (this.current && this.current !== next) {
      this.current.crossFadeTo(next, fade, true);
    }
    this.current = next;
    return next;
  }

  // Trigger a one-shot animation, return to whatever was playing before.
  triggerOnce(name, { fade = 0.1, timeScale = 1.0 } = {}) {
    const a = this.actions.get(name);
    if (!a) return null;
    const previous = this.current;
    a.reset();
    a.setLoop(THREE.LoopOnce, 0);
    a.clampWhenFinished = true;
    a.timeScale = timeScale;
    a.fadeIn(fade);
    a.play();
    a.getMixer().addEventListener('finished', function onDone(e) {
      if (e.action === a) {
        a.getMixer().removeEventListener('finished', onDone);
        if (previous) previous.fadeIn(fade).play();
      }
    });
    return a;
  }

  setSpeed(s) {
    if (this.current) this.current.timeScale = s;
  }

  update(dt) {
    this.mixer.update(dt);
  }
}
