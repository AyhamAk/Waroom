/* ══════════════════════════════════════════════
   WAR ROOM — CLIENT-SIDE ROUTER
   ══════════════════════════════════════════════
   History API routing layered on top of the existing single-page UI.

   Routes:
     /                  → assemble (phase 1)
     /live              → live mission feed (phase 4)
     /results           → results screen (phase 3)
     /studio/3d-game    → 3D Game Studio
     /studio/blender    → Blender Studio

   Loaded LAST in index.html so it can wrap the existing showPhase()
   and switchStudioMode() globals with URL-sync side effects.

   Backward-compatible: every existing call site that calls
   showPhase(n) or switchStudioMode(mode) continues to work — the
   wrappers just additionally update the URL via history.pushState.
   ══════════════════════════════════════════════ */
(function () {
  'use strict';

  // ── Route table ────────────────────────────────────────────────
  const ROUTES = [
    { test: (p) => p === '/' || p === '',                     name: 'home' },
    { test: (p) => p === '/live'    || p.startsWith('/live/'), name: 'live' },
    { test: (p) => p === '/results' || p.startsWith('/results/'), name: 'results' },
    { test: (p) => p === '/studio/3d-game',                   name: 'studio-3d-game' },
    { test: (p) => p === '/studio/blender',                   name: 'studio-blender' },
  ];

  // ── Internals ──────────────────────────────────────────────────
  let _origShowPhase = null;
  let _origSwitchStudioMode = null;
  let _isResolving = false;   // re-entrancy guard so resolve→handler→sync doesn't loop

  function _phaseToPath(n) {
    if (n === 4) return '/live';
    if (n === 3) return '/results';
    return '/';
  }

  function _modeToPath(mode) {
    if (mode === 'game3d')  return '/studio/3d-game';
    if (mode === 'blender') return '/studio/blender';
    return '/';
  }

  // Resolve a URL path → invoke the matching app function
  function resolve(path) {
    _isResolving = true;
    try {
      const route = ROUTES.find(r => r.test(path));
      const name = route ? route.name : 'home';   // 404 → home

      switch (name) {
        case 'home':
          if (_origSwitchStudioMode) _origSwitchStudioMode('game'); // hide other studio sections
          if (_origShowPhase) _origShowPhase(1);
          break;
        case 'live':
          if (_origSwitchStudioMode) _origSwitchStudioMode('game'); // ensure phases are visible
          if (_origShowPhase) _origShowPhase(4);
          break;
        case 'results':
          if (_origSwitchStudioMode) _origSwitchStudioMode('game');
          if (_origShowPhase) _origShowPhase(3);
          break;
        case 'studio-3d-game':
          if (_origSwitchStudioMode) _origSwitchStudioMode('game3d');
          break;
        case 'studio-blender':
          if (_origSwitchStudioMode) _origSwitchStudioMode('blender');
          break;
      }
    } finally {
      _isResolving = false;
    }
  }

  // Programmatic navigation — pushes state and applies the route
  function navigate(path, opts) {
    opts = opts || {};
    if (!path || typeof path !== 'string') return;
    if (location.pathname === path && !opts.force) return;
    if (opts.replace) history.replaceState(null, '', path);
    else history.pushState(null, '', path);
    resolve(path);
  }

  // Wrap the existing globals so any call to showPhase / switchStudioMode
  // also updates the URL (for back-button + bookmark support).
  function _hookExisting() {
    if (typeof window.showPhase === 'function' && !window.showPhase._wrapped) {
      _origShowPhase = window.showPhase;
      const wrapped = function (n) {
        _origShowPhase(n);
        if (_isResolving) return;
        const path = _phaseToPath(n);
        if (location.pathname !== path) history.pushState(null, '', path);
      };
      wrapped._wrapped = true;
      window.showPhase = wrapped;
    }
    if (typeof window.switchStudioMode === 'function' && !window.switchStudioMode._wrapped) {
      _origSwitchStudioMode = window.switchStudioMode;
      const wrapped = function (mode) {
        _origSwitchStudioMode(mode);
        if (_isResolving) return;
        const path = _modeToPath(mode);
        if (location.pathname !== path) history.pushState(null, '', path);
      };
      wrapped._wrapped = true;
      window.switchStudioMode = wrapped;
    }
  }

  // Browser back / forward
  window.addEventListener('popstate', function () {
    resolve(location.pathname);
  });

  // Intercept clicks on elements with [data-route="/path"] — lets us add
  // declarative deep-links anywhere in the markup (e.g. nav buttons).
  document.addEventListener('click', function (e) {
    const target = e.target.closest('[data-route]');
    if (!target) return;
    const path = target.getAttribute('data-route');
    if (!path) return;
    e.preventDefault();
    navigate(path);
  });

  // Initial route resolution after the page is ready
  function init() {
    _hookExisting();
    resolve(location.pathname);
  }

  // Public API
  window.warroomRouter = {
    navigate: navigate,
    resolve:  resolve,
    routes:   ROUTES.map(r => r.name),
  };
  // Convenience global for other scripts
  window.navigate = navigate;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    // DOM already parsed — defer to next tick so other scripts at the
    // bottom of <body> finish defining their globals first.
    setTimeout(init, 0);
  }
})();
