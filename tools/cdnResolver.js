/* ══════════════════════════════════════════════
   WAR ROOM — CDN RESOLVER
   Scans HTML for common library script/link tags
   and replaces guessed URLs with real cdnjs URLs.
   ══════════════════════════════════════════════ */

const CDN_MAP = {
  'chart.js':          'https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js',
  'chartjs':           'https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js',
  'three.js':          'https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js',
  'three.min.js':      'https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js',
  'matter.js':         'https://cdnjs.cloudflare.com/ajax/libs/matter-js/0.19.0/matter.min.js',
  'matter.min.js':     'https://cdnjs.cloudflare.com/ajax/libs/matter-js/0.19.0/matter.min.js',
  'd3.js':             'https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js',
  'd3.min.js':         'https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js',
  'gsap.min.js':       'https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.2/gsap.min.js',
  'gsap.js':           'https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.2/gsap.min.js',
  'p5.min.js':         'https://cdnjs.cloudflare.com/ajax/libs/p5.js/1.9.0/p5.min.js',
  'p5.js':             'https://cdnjs.cloudflare.com/ajax/libs/p5.js/1.9.0/p5.min.js',
  'tone.js':           'https://cdnjs.cloudflare.com/ajax/libs/tone/14.8.49/Tone.js',
  'tone.min.js':       'https://cdnjs.cloudflare.com/ajax/libs/tone/14.8.49/Tone.js',
  'socket.io.js':      'https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js',
  'anime.min.js':      'https://cdnjs.cloudflare.com/ajax/libs/animejs/3.2.1/anime.min.js',
  'anime.js':          'https://cdnjs.cloudflare.com/ajax/libs/animejs/3.2.1/anime.min.js',
  'howler.min.js':     'https://cdnjs.cloudflare.com/ajax/libs/howler/2.2.4/howler.min.js',
  'howler.js':         'https://cdnjs.cloudflare.com/ajax/libs/howler/2.2.4/howler.min.js',
  'lodash.min.js':     'https://cdnjs.cloudflare.com/ajax/libs/lodash.js/4.17.21/lodash.min.js',
  'lodash.js':         'https://cdnjs.cloudflare.com/ajax/libs/lodash.js/4.17.21/lodash.min.js',
  'moment.min.js':     'https://cdnjs.cloudflare.com/ajax/libs/moment.js/2.29.4/moment.min.js',
  'moment.js':         'https://cdnjs.cloudflare.com/ajax/libs/moment.js/2.29.4/moment.min.js',
  'pixi.min.js':       'https://cdnjs.cloudflare.com/ajax/libs/pixi.js/7.3.2/pixi.min.js',
  'pixi.js':           'https://cdnjs.cloudflare.com/ajax/libs/pixi.js/7.3.2/pixi.min.js',
  'phaser.min.js':     'https://cdnjs.cloudflare.com/ajax/libs/phaser/3.60.0/phaser.min.js',
  'phaser.js':         'https://cdnjs.cloudflare.com/ajax/libs/phaser/3.60.0/phaser.min.js',
  'cannon.min.js':     'https://cdnjs.cloudflare.com/ajax/libs/cannon.js/0.6.2/cannon.min.js',
  'planck.min.js':     'https://cdn.jsdelivr.net/npm/planck@1.0.0/dist/planck.min.js',
  'box2d.min.js':      'https://cdnjs.cloudflare.com/ajax/libs/box2dweb/2.1a/Box2d.min.js',
  'highlight.min.js':  'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js',
  'marked.min.js':     'https://cdnjs.cloudflare.com/ajax/libs/marked/9.1.6/marked.min.js',
  'marked.js':         'https://cdnjs.cloudflare.com/ajax/libs/marked/9.1.6/marked.min.js',
  'confetti.min.js':   'https://cdn.jsdelivr.net/npm/canvas-confetti@1.9.2/dist/confetti.browser.min.js',
  'html2canvas.min.js':'https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js',
  'jszip.min.js':      'https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js',
  'vue.global.prod.min.js': 'https://cdnjs.cloudflare.com/ajax/libs/vue/3.4.21/vue.global.prod.min.js',
  'vue.min.js':             'https://cdnjs.cloudflare.com/ajax/libs/vue/3.4.21/vue.global.prod.min.js',
  'vue.js':                 'https://cdnjs.cloudflare.com/ajax/libs/vue/3.4.21/vue.global.prod.min.js',
  'faker.min.js':           'https://cdnjs.cloudflare.com/ajax/libs/Faker/5.5.3/faker.min.js',
  'faker.js':               'https://cdnjs.cloudflare.com/ajax/libs/Faker/5.5.3/faker.min.js',
  'dayjs.min.js':           'https://cdnjs.cloudflare.com/ajax/libs/dayjs/1.11.10/dayjs.min.js',
  'dayjs.js':               'https://cdnjs.cloudflare.com/ajax/libs/dayjs/1.11.10/dayjs.min.js',
  'kaboom.js':              'https://unpkg.com/kaboom@3000.1.17/dist/kaboom.js',
  'babylon.js':             'https://cdn.babylonjs.com/babylon.js',
  'numeral.min.js':         'https://cdnjs.cloudflare.com/ajax/libs/numeral.js/2.0.6/numeral.min.js',
  'numeral.js':             'https://cdnjs.cloudflare.com/ajax/libs/numeral.js/2.0.6/numeral.min.js',
};

// CSS CDN map
const CSS_CDN_MAP = {
  'font-awesome':      'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css',
  'bootstrap.min.css': 'https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.3.2/css/bootstrap.min.css',
  'normalize.css':     'https://cdnjs.cloudflare.com/ajax/libs/normalize/8.0.1/normalize.min.css',
  'bulma.min.css':     'https://cdnjs.cloudflare.com/ajax/libs/bulma/0.9.4/css/bulma.min.css',
  'animate.min.css':   'https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.min.css',
};

function resolveCDNs(html) {
  // Replace <script src="..."> tags that reference known libraries
  html = html.replace(/<script\b([^>]*?)src=["']([^"']+)["']([^>]*?)>/gi, (match, pre, src, post) => {
    const filename = src.split('/').pop().toLowerCase().split('?')[0];
    const resolved = CDN_MAP[filename];
    if (resolved && src !== resolved) {
      console.log(`[cdn] resolved ${filename} → ${resolved}`);
      return `<script${pre}src="${resolved}"${post}>`;
    }
    // Also check if the src contains a known library name but wrong version/path
    for (const [key, url] of Object.entries(CDN_MAP)) {
      if (src.toLowerCase().includes(key.replace('.min.js', '').replace('.js', '')) &&
          !src.startsWith('http') && src.endsWith('.js')) {
        console.log(`[cdn] resolved ${src} → ${url}`);
        return `<script${pre}src="${url}"${post}>`;
      }
    }
    return match;
  });

  // Replace <link href="..."> tags that reference known CSS libraries
  html = html.replace(/<link\b([^>]*?)href=["']([^"']+)["']([^>]*?)>/gi, (match, pre, href, post) => {
    const filename = href.split('/').pop().toLowerCase().split('?')[0];
    const resolved = CSS_CDN_MAP[filename];
    if (resolved && href !== resolved) {
      console.log(`[cdn] resolved CSS ${filename} → ${resolved}`);
      return `<link${pre}href="${resolved}"${post}>`;
    }
    return match;
  });

  return html;
}

// Returns a string listing available CDN libraries for injection into prompts
function getCDNHint() {
  return `Available CDN libraries (use these exact URLs in <script src> or <link href>):
JS Libraries:
- Chart.js: https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js
- Three.js: https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js
- Matter.js (physics): https://cdnjs.cloudflare.com/ajax/libs/matter-js/0.19.0/matter.min.js
- D3.js: https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js
- GSAP (animation): https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.2/gsap.min.js
- P5.js: https://cdnjs.cloudflare.com/ajax/libs/p5.js/1.9.0/p5.min.js
- Phaser (game engine): https://cdnjs.cloudflare.com/ajax/libs/phaser/3.60.0/phaser.min.js
- Pixi.js (2D renderer): https://cdnjs.cloudflare.com/ajax/libs/pixi.js/7.3.2/pixi.min.js
- Howler.js (audio): https://cdnjs.cloudflare.com/ajax/libs/howler/2.2.4/howler.min.js
- Anime.js (animation): https://cdnjs.cloudflare.com/ajax/libs/animejs/3.2.1/anime.min.js
- Confetti: https://cdn.jsdelivr.net/npm/canvas-confetti@1.9.2/dist/confetti.browser.min.js
- Vue 3 (reactive UI): https://cdnjs.cloudflare.com/ajax/libs/vue/3.4.21/vue.global.prod.min.js
- Faker.js (mock data): https://cdnjs.cloudflare.com/ajax/libs/Faker/5.5.3/faker.min.js  → faker.name.findName(), faker.commerce.price()
- Day.js (date formatting): https://cdnjs.cloudflare.com/ajax/libs/dayjs/1.11.10/dayjs.min.js  → dayjs().format('MMM D, YYYY')
- Kaboom.js (simple 2D games): https://unpkg.com/kaboom@3000.1.17/dist/kaboom.js
- Babylon.js (3D scenes): https://cdn.babylonjs.com/babylon.js
- Numeral.js (number formatting): https://cdnjs.cloudflare.com/ajax/libs/numeral.js/2.0.6/numeral.min.js  → numeral(1234567).format('$0,0')
CSS Frameworks:
- Bulma CSS (UI framework, zero layout CSS needed): https://cdnjs.cloudflare.com/ajax/libs/bulma/0.9.4/css/bulma.min.css
  → <link rel="stylesheet" href="..."> in <head>. Classes: button, card, columns, column, navbar, hero, section, table, tag, notification, progress
- Animate.css (CSS animations): https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.min.css  → class="animate__animated animate__fadeIn"`;
}

module.exports = { resolveCDNs, getCDNHint };
