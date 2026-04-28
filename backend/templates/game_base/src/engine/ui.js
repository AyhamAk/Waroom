// UI — thin helpers for HUD cards, bars, overlays. Game classes drive it.
export class UI {
  mount() {
    this.tl = document.getElementById('hud-top-left');
    this.tr = document.getElementById('hud-top-right');
    this.bottom = document.getElementById('hud-bottom');
    this.overlay = document.getElementById('overlay');
  }

  setHUD(slot, html) {
    const el = ({ tl: this.tl, tr: this.tr, bottom: this.bottom })[slot];
    if (el) el.innerHTML = html;
  }

  bar(label, value, max, slot = 'tl') {
    const pct = Math.max(0, Math.min(1, value / max)) * 100;
    this.setHUD(slot, `<div class="hud-card">${label} <strong>${Math.round(value)}</strong>/${max}</div><div class="hud-bar"><i style="width:${pct}%"></i></div>`);
  }

  text(slot, text) {
    this.setHUD(slot, `<div class="hud-card">${text}</div>`);
  }

  showOverlay(title, body, buttonLabel = 'Restart', onClick = null) {
    this.overlay.innerHTML = `<h1>${title}</h1><p>${body}</p>${buttonLabel ? `<button id="overlay-btn">${buttonLabel}</button>` : ''}`;
    this.overlay.hidden = false;
    if (buttonLabel && onClick) {
      document.getElementById('overlay-btn').addEventListener('click', () => {
        this.hideOverlay();
        onClick();
      });
    }
  }

  hideOverlay() {
    this.overlay.hidden = true;
    this.overlay.innerHTML = '';
  }
}
