// Input — keyboard + mouse + touch + gamepad. Polled state per frame.
// Game classes read engine.input.down.has('w'), engine.input.mouse.dx, etc.

const KEY_MAP = {
  arrowup: 'w', arrowdown: 's', arrowleft: 'a', arrowright: 'd',
};

export class Input {
  constructor(canvas) {
    this.canvas = canvas;
    this.down = new Set();
    this.pressed = new Set();   // edge: this frame only
    this.released = new Set();
    this._buffered = { pressed: new Set(), released: new Set() };

    this.mouse = {
      x: 0, y: 0,
      dx: 0, dy: 0,
      _dxAcc: 0, _dyAcc: 0,
      buttons: new Set(),
      pressed: new Set(),
      released: new Set(),
      _bufP: new Set(), _bufR: new Set(),
      pointerLocked: false,
      wheel: 0, _wheelAcc: 0,
    };

    this.touches = new Map();
    this.gamepad = null;
  }

  attach() {
    addEventListener('keydown', this._onKeyDown, { passive: false });
    addEventListener('keyup', this._onKeyUp, { passive: false });
    this.canvas.addEventListener('mousedown', this._onMouseDown);
    addEventListener('mouseup', this._onMouseUp);
    this.canvas.addEventListener('mousemove', this._onMouseMove, { passive: true });
    this.canvas.addEventListener('wheel', this._onWheel, { passive: false });
    document.addEventListener('pointerlockchange', this._onPointerLockChange);
    this.canvas.addEventListener('touchstart', this._onTouchStart, { passive: false });
    this.canvas.addEventListener('touchmove', this._onTouchMove, { passive: false });
    addEventListener('touchend', this._onTouchEnd, { passive: false });
    addEventListener('contextmenu', (e) => e.preventDefault());
  }

  requestPointerLock() {
    this.canvas.requestPointerLock?.();
  }

  tick() {
    this.pressed = this._buffered.pressed;
    this.released = this._buffered.released;
    this._buffered.pressed = new Set();
    this._buffered.released = new Set();

    this.mouse.dx = this.mouse._dxAcc;
    this.mouse.dy = this.mouse._dyAcc;
    this.mouse._dxAcc = 0;
    this.mouse._dyAcc = 0;
    this.mouse.wheel = this.mouse._wheelAcc;
    this.mouse._wheelAcc = 0;
    this.mouse.pressed = this.mouse._bufP;
    this.mouse.released = this.mouse._bufR;
    this.mouse._bufP = new Set();
    this.mouse._bufR = new Set();

    // Gamepad poll
    const pads = navigator.getGamepads?.() || [];
    this.gamepad = pads.find(p => p && p.connected) || null;
  }

  // Axis helper: returns -1..1 for keyboard pairs and gamepad stick.
  axis(neg, pos, padAxis = -1) {
    let v = 0;
    if (this.down.has(neg)) v -= 1;
    if (this.down.has(pos)) v += 1;
    if (padAxis >= 0 && this.gamepad) {
      const a = this.gamepad.axes[padAxis] || 0;
      if (Math.abs(a) > 0.15) v += a;
    }
    return Math.max(-1, Math.min(1, v));
  }

  _onKeyDown = (e) => {
    const key = (KEY_MAP[e.key.toLowerCase()] || e.key.toLowerCase());
    if (!this.down.has(key)) this._buffered.pressed.add(key);
    this.down.add(key);
    if (['w','a','s','d',' ','tab','/'].includes(key)) e.preventDefault();
  };

  _onKeyUp = (e) => {
    const key = (KEY_MAP[e.key.toLowerCase()] || e.key.toLowerCase());
    this.down.delete(key);
    this._buffered.released.add(key);
  };

  _onMouseDown = (e) => {
    this.mouse.buttons.add(e.button);
    this.mouse._bufP.add(e.button);
  };
  _onMouseUp = (e) => {
    this.mouse.buttons.delete(e.button);
    this.mouse._bufR.add(e.button);
  };
  _onMouseMove = (e) => {
    if (this.mouse.pointerLocked) {
      this.mouse._dxAcc += e.movementX || 0;
      this.mouse._dyAcc += e.movementY || 0;
    } else {
      const r = this.canvas.getBoundingClientRect();
      const nx = (e.clientX - r.left);
      const ny = (e.clientY - r.top);
      this.mouse._dxAcc += nx - this.mouse.x;
      this.mouse._dyAcc += ny - this.mouse.y;
      this.mouse.x = nx;
      this.mouse.y = ny;
    }
  };
  _onWheel = (e) => {
    this.mouse._wheelAcc += Math.sign(e.deltaY);
    e.preventDefault();
  };
  _onPointerLockChange = () => {
    this.mouse.pointerLocked = document.pointerLockElement === this.canvas;
  };

  _onTouchStart = (e) => {
    for (const t of e.changedTouches) this.touches.set(t.identifier, { x: t.clientX, y: t.clientY, sx: t.clientX, sy: t.clientY });
    e.preventDefault();
  };
  _onTouchMove = (e) => {
    for (const t of e.changedTouches) {
      const cur = this.touches.get(t.identifier);
      if (cur) { cur.x = t.clientX; cur.y = t.clientY; }
    }
    e.preventDefault();
  };
  _onTouchEnd = (e) => {
    for (const t of e.changedTouches) this.touches.delete(t.identifier);
  };
}
