/* ══════════════════════════════════════════════
   WAR ROOM — AGENT PROMPTS
   Category-aware prompt builder for Phase 4 live pipeline.
   buildPrompt(agentId, live) → string
   ══════════════════════════════════════════════ */

const fs   = require('fs');
const path = require('path');

const { getCDNHint } = require('./tools/cdnResolver');

async function buildPrompt(agentId, live, searchResults = '') {
  const brief    = live.brief.slice(0, 200);
  const cycle    = live.cycle || 1;
  const category = live.category || 'tech-startup';

  function readFile(p) {
    if (!live.workspaceDir) return '';
    try { return fs.readFileSync(path.join(live.workspaceDir, p), 'utf8'); } catch { return ''; }
  }

  function workFmt(filename, taskHint) {
    return `Respond in this EXACT format, no other text:
TYPE: work
FILENAME: ${filename}
TASK: ${taskHint}
---
<content here>`;
  }

  const featurePriority = readFile('docs/feature-priority.md');
  const techSpec        = readFile('docs/technical-spec.md');
  const designSpec      = readFile('docs/design-spec.md');
  const roadmap         = readFile('docs/product-roadmap.md');
  const html            = readFile('public/index.html');
  const css             = readFile('public/style.css');
  const appJs           = readFile('public/app.js');
  const dataJs          = readFile('public/data.js');
  const lastQA          = cycle > 1 ? readFile(`docs/qa-cycle${cycle - 1}.md`) : '';

  // Feature inventory written by pipeline after each builder run.
  // Tells the builder which functions/state keys exist and must be preserved.
  const featuresRaw = readFile('docs/features.json');
  let featuresCtx = '';
  try {
    const feat = JSON.parse(featuresRaw);
    if (feat.functions?.length) featuresCtx += `Functions: ${feat.functions.join(', ')}`;
    if (feat.stateKeys?.length) featuresCtx += `\nState keys: ${feat.stateKeys.join(', ')}`;
  } catch { /* no inventory yet — cycle 1 */ }

  // Summarize a JS file for builder context: show full content up to maxChars,
  // then list any additional function names that were cut off.
  function summarizeJs(code, maxChars = 3000) {
    if (!code) return '(empty)';
    if (code.length <= maxChars) return code;
    const head = code.slice(0, maxChars);
    const moreFns = [...code.slice(maxChars).matchAll(/^(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:function|\())/gm)]
      .map(m => m[1] || m[2]).filter(Boolean);
    return head + (moreFns.length
      ? `\n// ... [${moreFns.length} more: ${moreFns.join(', ')}]`
      : '\n// ... [truncated]');
  }
  const htmlLines = html  ? html.split('\n').length  : 0;
  const cssLines  = css   ? css.split('\n').length   : 0;
  const jsLines   = (appJs ? appJs.split('\n').length : 0) + (dataJs ? dataJs.split('\n').length : 0);

  // Extract function names from JS to give CEO/LE a real inventory of what's built
  const jsFunctions = (() => {
    const allJs = (dataJs || '') + '\n' + (appJs || '');
    const fns = [...allJs.matchAll(/^(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:function|\([^)]*\)\s*=>))/gm)]
      .map(m => m[1] || m[2]).filter(Boolean);
    return fns.length ? fns.slice(0, 20).join(', ') : 'none yet';
  })();

  const existingHtmlPages = (() => {
    try {
      const pub = path.join(live.workspaceDir, 'public');
      return fs.readdirSync(pub).filter(f => f.endsWith('.html'));
    } catch { return []; }
  })();

  const headings = [...html.matchAll(/<(h[1-3]|section)[^>]*id=["']([^"']+)["'][^>]*>([^<]*)/gi)]
                     .map(m => `${m[2]}: ${m[3].trim()}`).filter(s => s.length > 2);
  const sectionList = [
    existingHtmlPages.length > 1 ? `Pages: ${existingHtmlPages.join(', ')}` : '',
    headings.length ? headings.slice(0, 10).join(' | ') : (html ? `${htmlLines} lines built` : 'nothing yet'),
  ].filter(Boolean).join('\n');

  const existingPages  = existingHtmlPages.map(f => 'public/' + f).join(', ') || 'none yet';
  const donePriorities = live.pastPriorities.length
    ? live.pastPriorities.map((p, i) => `[${i + 1}] ${p}`).join(' | ') : 'nothing';
  const lastPriority   = live.pastPriorities.length ? live.pastPriorities[live.pastPriorities.length - 1] : '';
  const consecutiveFixes = (() => {
    let n = 0;
    for (let i = live.pastPriorities.length - 1; i >= 0; i--) {
      if (live.pastPriorities[i].trim().toUpperCase().startsWith('FIX:')) n++; else break;
    }
    return n;
  })();

  // Detect fix mode: CEO ordered a FIX last cycle
  // (declared early so fixLimitNote can reference isSiteBroken)
  const visionReportEarly = live.lastVisionReport || '';
  const isSiteBrokenEarly = visionReportEarly.includes('BROKEN')
    || /health score.*[1-4]/i.test(visionReportEarly)
    || /score.*[1-4].*\/.*10/i.test(visionReportEarly);

  // After 1 consecutive FIX, push CEO to move on — BUT only if the site is actually healthy.
  // If the site is still broken (health ≤ 4), never block FIX regardless of how many cycles.
  const fixLimitNote = (consecutiveFixes >= 1 && !isSiteBrokenEarly)
    ? `🚫 MANDATORY OVERRIDE: You already issued a FIX last cycle AND the site is now healthy. You MUST output a NEW PAGE or SECTION this cycle — NOT FIX. Outputting FIX again is NOT allowed.\n`
    : '';

  // Detect fix mode: CEO ordered a FIX last cycle
  const isFix = featurePriority.trim().startsWith('FIX:');

  // JS snapshot for fix mode — give builder the real current code to work from
  const jsSnapshot = [
    dataJs ? `// data.js\n${dataJs.slice(0, 1500)}` : '',
    appJs  ? `// app.js\n${appJs.slice(0, 1500)}`   : '',
  ].filter(Boolean).join('\n\n') || '';

  /* ── CEO / Director prompts per category ── */
  const visionReport  = visionReportEarly;
  const isSiteBroken  = isSiteBrokenEarly;

  const roadmapCtx = roadmap
    ? `PRODUCT ROADMAP (your plan — tick off items as they're done):\n${roadmap}\n`
    : cycle === 1
      ? `PRODUCT ROADMAP: None yet — you will create it this cycle as the second output file.\n`
      : '';

  const CEO_PROMPTS = {
    'tech-startup': `You are an elite Product Manager. Project: "${brief}". Cycle ${cycle}.
${roadmapCtx}
UI SECTIONS BUILT: ${sectionList}
JS FUNCTIONS IMPLEMENTED: ${jsFunctions}
COMPLETED CYCLES: ${donePriorities}
Last cycle: ${lastPriority || 'nothing yet'}
QA last cycle: ${lastQA ? lastQA.slice(0, 300) : 'N/A'}
${fixLimitNote}
DECISION RULES (follow in strict order — stop at first match):
1. If VISUAL ANALYSIS says BROKEN or health score ≤ 4 → FIX: <be specific — name the broken component and what exactly is wrong>
2. NEVER repeat last cycle's decision.
3. If QA flagged broken logic AND last cycle was NOT already a FIX for the same issue → FIX: <specific>
4. If JS functions = "none yet" and cycle > 1 → FIX: implement all JS interactivity — data simulation, DOM updates, event handlers
5. Otherwise → pick the HIGHEST-IMPACT next item from the roadmap (or invent the best next feature if no roadmap).
   - NEW PAGE: /name.html — one sentence description
   - SECTION: one sentence description
   Pages so far: ${existingHtmlPages.length}. Prefer new pages after 4+ sections on index.html.
${cycle === 1 ? `
Also output a product roadmap (second file) — 6–8 bullet points covering the complete product vision.` : ''}
Output exactly ONE line for the feature decision: FIX: ... OR NEW PAGE: ... OR SECTION: ...
${cycle === 1
  ? workFmt('docs/feature-priority.md', 'Feature decision for cycle 1') + '\n\n' +
    `===FILE===\nRespond in this EXACT format, no other text:\nTYPE: work\nFILENAME: docs/product-roadmap.md\nTASK: Product roadmap\n---\n<roadmap content here>`
  : workFmt('docs/feature-priority.md', 'Feature decision for cycle ' + cycle)}`,

    'game-studio': `You are Game Director. Game: "${brief}". Cycle ${cycle}.
Built: ${sectionList}
Done: ${donePriorities}
Last cycle: ${lastPriority || 'nothing yet'}
QA last cycle: ${lastQA ? lastQA.slice(0, 300) : 'N/A'}
JS size: ${jsLines} lines
${fixLimitNote}
DECISION RULES (follow in strict order — stop at first match):
1. Cycle 1 → always: SECTION: complete game with loop, input, collision, score, start/play/gameover states
2. If VISUAL ANALYSIS above says BROKEN or health score ≤ 4 → FIX: <describe exactly what's broken — black screen, canvas empty, game stuck, etc.>
3. NEVER output anything identical or nearly identical to "Last cycle" above.
4. If QA flagged game-breaking bugs AND last cycle was NOT already a FIX for the same issue → FIX: <specific fix>
5. If JS < 100 lines → FIX: implement complete game loop with requestAnimationFrame, input handling, collision detection, and score display
5. Otherwise → add ONE new mechanic:
   - NEW PAGE: /name.html — description (separate game screen like leaderboard, settings)
   - SECTION: description (new mechanic, power-up, enemy type, level progression)

Output exactly ONE line: FIX: ... OR NEW PAGE: ... OR SECTION: ...
${workFmt('docs/feature-priority.md', 'Game feature for cycle ' + cycle)}`,

    'film-production': `You are Film Director. Project: "${brief}". Cycle ${cycle}.
Built: ${sectionList}
Done: ${donePriorities}
Last cycle: ${lastPriority || 'nothing yet'}

RULE: NEVER pick anything identical or nearly identical to "Last cycle". Always advance to something new.
Pick ONE page or section to add to the film website. Routing rule:
- NEW PAGE if it's a distinct section (/cast.html, /gallery.html, /screenplay.html, /awards.html)
- SECTION if it's added to the main page (trailer embed, synopsis block, review quotes, crew credits)
Output: "NEW PAGE: /name.html — description" OR "SECTION: description".
${workFmt('docs/feature-priority.md', 'Film feature for cycle ' + cycle)}`,

    'ad-agency': `You are Creative Director. Campaign: "${brief}". Cycle ${cycle}.
Built: ${sectionList}
Done: ${donePriorities}
Last cycle: ${lastPriority || 'nothing yet'}

RULE: NEVER pick anything identical or nearly identical to "Last cycle". Always advance to something new.
Pick ONE campaign section or page to add. Routing rule:
- NEW PAGE if it's a distinct landing page (/case-study.html, /results.html, /contact.html)
- SECTION if it's added to the main campaign page (testimonials, stats, CTA block, social proof, video)
Output: "NEW PAGE: /name.html — description" OR "SECTION: description".
${workFmt('docs/feature-priority.md', 'Campaign feature for cycle ' + cycle)}`,

    'newsroom': `You are Editor-in-Chief. Story: "${brief}". Cycle ${cycle}.
Built: ${sectionList}
Done: ${donePriorities}
Last cycle: ${lastPriority || 'nothing yet'}

RULE: NEVER pick anything identical or nearly identical to "Last cycle". Always advance to something new.
Pick ONE article section or page to build next. Routing rule:
- NEW PAGE if it's a distinct story page (/data-analysis.html, /related-stories.html, /sources.html)
- SECTION if it's added to the main article (pull quote, data visualization, photo gallery, sidebar, timeline)
Output: "NEW PAGE: /name.html — description" OR "SECTION: description".
${workFmt('docs/feature-priority.md', 'Article feature for cycle ' + cycle)}`,

    'consulting': `You are Managing Director. Engagement: "${brief}". Cycle ${cycle}.
Built: ${sectionList}
Done: ${donePriorities}
Last cycle: ${lastPriority || 'nothing yet'}

RULE: NEVER pick anything identical or nearly identical to "Last cycle". Always advance to something new.
Pick ONE deliverable section or page to build next. Routing rule:
- NEW PAGE if it's a distinct report section (/analysis.html, /recommendations.html, /appendix.html)
- SECTION if it's added to the main report page (executive summary, chart, matrix, timeline, table)
Output: "NEW PAGE: /name.html — description" OR "SECTION: description".
${workFmt('docs/feature-priority.md', 'Deliverable for cycle ' + cycle)}`,
  };

  /* ── Customer feedback + search context (needed by all agent prompts) ── */
  const customerFeedback = live.customerFeedback ? live.customerFeedback.trim() : '';
  const customerNote = customerFeedback
    ? `🚨 CUSTOMER FEEDBACK — MANDATORY THIS CYCLE: "${customerFeedback}"\nYou MUST output a decision that directly addresses this feedback. Do not add unrelated features.\n\n`
    : '';
  const customerCtx = customerFeedback
    ? `\n🚨 CUSTOMER FEEDBACK TO ADDRESS THIS CYCLE: "${customerFeedback}"\n`
    : '';
  const searchNote = searchResults
    ? `\nWEB SEARCH RESULTS (use to inform your decision):\n${searchResults}\n`
    : '';

  /* ── Lead Engineer prompts per category ── */
  const LEAD_ENG_PROMPTS = {
    'tech-startup': `You are Lead Engineer. Cycle ${cycle}.
Task: ${featurePriority || 'Build the full app from scratch.'}${customerCtx}${searchNote}
Pages: ${existingHtmlPages.join(', ') || 'none'} | Size: ${htmlLines}L HTML, ${cssLines}L CSS, ${jsLines}L JS
${isFix ? `Current JS:\n${jsSnapshot}` : ''}
⚠️ STACK CONSTRAINT: Vanilla HTML5 + CSS3 + JavaScript ONLY. No React, no TypeScript, no npm, no build tools, no import/export. Files must run directly in the browser with <script src="...">.

${isFix
  ? `Write a FIX spec (200+ words): identify the broken functions by name, show the incorrect logic, write the correct implementation approach, list every DOM element ID involved, and describe the exact data flow fix. Note whether data.js or app.js needs the fix.`
  : `Write a DETAILED technical spec (300+ words). Cover ALL of:
1. TARGET FILES: index.html, data.js (state+simulation), app.js (DOM+events), style.css
2. HTML STRUCTURE: every section, element ID, class name, and data attribute the JS needs (e.g. <div id="chart-canvas">, <span class="price-value" data-coin="BTC">)
3. JAVASCRIPT STATE (goes in data.js): exact global const state = {...} object shape with field names and types (NO modules, NO imports)
   e.g. const state = { prices: { BTC: 45000 }, history: { BTC: [] }, portfolio: { BTC: { qty: 0, avgCost: 0 } } }
4. SIMULATION FUNCTIONS (go in data.js): setInterval calls, random walk formulas, data generation
   e.g. simulatePrices() — updates state.prices every 2s using setInterval
5. RENDER FUNCTIONS (go in app.js): DOM updates, chart drawing, event wiring
   e.g. renderChart(coin) — draws SVG polyline using state.history[coin]
6. EVENT FLOW: which user actions trigger which state changes and DOM updates
7. DATA APPROACH: exact algorithm for simulating realistic data (random walk formula, ranges)
Be precise. Builder implements exactly this spec.`}
${workFmt('docs/technical-spec.md', (isFix ? 'Fix spec' : 'Tech spec') + ' cycle ' + cycle)}`,

    'game-studio': `You are Game Systems Engineer. Cycle ${cycle}.
Task: ${featurePriority || 'Build the game from scratch.'}
Pages: ${existingHtmlPages.join(', ') || 'none'} | Size: ${htmlLines}L HTML, ${cssLines}L CSS, ${jsLines}L JS
${isFix ? `Current app.js (first 1200 chars):\n${jsSnapshot.slice(0, 1200)}` : ''}

${isFix
  ? `Write a FIX spec (200+ words): name the broken functions, show incorrect logic, write correct game loop structure (requestAnimationFrame → update() → draw()), correct input handling (keydown/keyup state map), correct collision algorithm, correct state machine transitions (START/PLAYING/GAMEOVER). Be specific.`
  : `Write a DETAILED game architecture spec (300+ words). Cover ALL of:
1. STATE OBJECT: exact shape — { player: {x,y,vx,vy,health,lives}, enemies: [], bullets: [], score, wave, gameState, keys: {} }
2. ALL FUNCTIONS with signatures: update(dt), draw(ctx), spawnEnemy(wave), checkCollision(a,b), handleInput()
3. GAME LOOP: requestAnimationFrame pattern, delta time calculation
4. INPUT: keydown/keyup event map (ArrowLeft/Right/Up/Down/Space/W/A/S/D)
5. COLLISION: algorithm type (AABB rect vs rect, or circle), which objects check against which
6. SPAWNING: enemy spawn rate formula per wave, enemy types and their behavior
7. CANVAS IDs and dimensions`}
${workFmt('docs/technical-spec.md', (isFix ? 'Fix spec' : 'Game spec') + ' cycle ' + cycle)}`,

    'film-production': `You are Screenwriter. Cycle ${cycle}.
Feature: ${featurePriority || 'Build the film website from scratch.'}
Pages: ${existingHtmlPages.join(', ') || 'none'} | Size: ${htmlLines}L HTML, ${cssLines}L CSS

Write content spec (≤100 words): target file, HTML sections needed, content structure, text elements, media placeholders.
${workFmt('docs/technical-spec.md', 'Content spec cycle ' + cycle)}`,

    'ad-agency': `You are Brand Strategist. Cycle ${cycle}.
Feature: ${featurePriority || 'Build the campaign landing page from scratch.'}
Pages: ${existingHtmlPages.join(', ') || 'none'} | Size: ${htmlLines}L HTML, ${cssLines}L CSS

Write messaging spec (≤100 words): target file, HTML sections, copy blocks, conversion elements, CTA placements.
${workFmt('docs/technical-spec.md', 'Messaging spec cycle ' + cycle)}`,

    'newsroom': `You are Reporter. Cycle ${cycle}.
Feature: ${featurePriority || 'Build the article page from scratch.'}
Pages: ${existingHtmlPages.join(', ') || 'none'} | Size: ${htmlLines}L HTML, ${cssLines}L CSS

Write editorial spec (≤100 words): target file, article structure, section IDs, content blocks, data visualizations needed.
${workFmt('docs/technical-spec.md', 'Editorial spec cycle ' + cycle)}`,

    'consulting': `You are Data Analyst. Cycle ${cycle}.
Feature: ${featurePriority || 'Build the strategy report from scratch.'}
Pages: ${existingHtmlPages.join(', ') || 'none'} | Size: ${htmlLines}L HTML, ${cssLines}L CSS

Write deliverable spec (≤100 words): target file, report sections, data tables needed, chart types, key metrics to display.
${workFmt('docs/technical-spec.md', 'Report spec cycle ' + cycle)}`,
  };

  /* ── Designer prompts per category ── */
  const DESIGNER_PROMPTS = {
    'tech-startup': `You are UI Designer. Cycle ${cycle}.
Feature: ${featurePriority || 'Design the full app.'}${customerCtx}
Tech spec: ${techSpec ? techSpec.slice(0, 400) : 'See feature above.'}

Write a DETAILED design spec with EXACT values (200+ words). Cover ALL of:
1. CSS CUSTOM PROPERTIES (all with hex values):
   --bg, --surface, --surface2, --border, --accent, --danger, --success, --text, --text-muted, --font-mono
2. TYPOGRAPHY: font-family stack, font-size per element (px), font-weight, letter-spacing for numbers
3. LAYOUT: grid/flex structure for each major section, column widths, gap, padding (px values)
4. COMPONENTS — exact styles for each:
   - Cards: background, border, border-radius, padding, box-shadow
   - Buttons: background, color, padding, hover state
   - Inputs: background, border, focus style
   - Price values: color (green for positive, red for negative), font-size, font-weight
   - Charts: line color, glow effect, grid line color, axis label style
5. ANIMATIONS: transition for price updates (flash green/red), chart line drawing, hover effects
Builder copies these exact values into CSS — no guessing, no approximations.
${workFmt('docs/design-spec.md', 'Design spec cycle ' + cycle)}`,

    'game-studio': `You are Visual Artist. Cycle ${cycle}.
Feature: ${featurePriority || 'Design the game.'}
Spec: ${techSpec ? techSpec.slice(0, 300) : ''}

Write a DETAILED art direction spec with EXACT values (150+ words). Cover ALL of:
1. CSS CUSTOM PROPERTIES: --bg (canvas background hex), --player-color, --enemy-color, --bullet-color, --hud-bg, --hud-text
2. Canvas background: exact hex color or gradient definition
3. Player entity: shape (rect/circle), exact fill color, glow effect (box-shadow or ctx.shadowBlur)
4. Enemy entities: shape, fill color, stroke
5. Bullets/projectiles: size (px), color, glow
6. Particle effects: explosion color, size range, fade behavior
7. HUD: font-family (monospace recommended), font-size, color, position (top-left, top-right)
8. Animations: canvas glow intensity (ctx.shadowBlur value), screen flash color on damage
${workFmt('docs/design-spec.md', 'Art spec cycle ' + cycle)}`,

    'film-production': `You are Director of Photography. Cycle ${cycle}.
Feature: ${featurePriority || 'Design the film website.'}
Spec: ${techSpec ? techSpec.slice(0, 150) : ''}

Write visual spec (≤80 words): color palette (cinematic), typography, image treatment, layout mood, dark/light tone.
${workFmt('docs/design-spec.md', 'Visual spec cycle ' + cycle)}`,

    'ad-agency': `You are Art Director. Cycle ${cycle}.
Feature: ${featurePriority || 'Design the campaign page.'}
Spec: ${techSpec ? techSpec.slice(0, 150) : ''}

Write visual direction spec (≤80 words): brand colors, typography, imagery style, layout grid, component aesthetics.
${workFmt('docs/design-spec.md', 'Design spec cycle ' + cycle)}`,

    'newsroom': `You are Photo Editor. Cycle ${cycle}.
Feature: ${featurePriority || 'Design the news article.'}
Spec: ${techSpec ? techSpec.slice(0, 150) : ''}

Write visual spec (≤80 words): editorial color palette, typography (serif/sans), image treatment, layout density, section styling.
${workFmt('docs/design-spec.md', 'Visual spec cycle ' + cycle)}`,

    'consulting': `You are Presentation Designer. Cycle ${cycle}.
Feature: ${featurePriority || 'Design the strategy report.'}
Spec: ${techSpec ? techSpec.slice(0, 150) : ''}

Write visual spec (≤80 words): professional color palette, chart styles, table design, typography, white space, data hierarchy.
${workFmt('docs/design-spec.md', 'Design spec cycle ' + cycle)}`,
  };

  /* ── QA prompts per category ── */
  const QA_PROMPTS = {
    'game-studio': `Playtester. Cycle ${cycle}.
Feature built: ${featurePriority || 'core game'} | JS size: ${jsLines} lines
App.js sample: ${jsSnapshot.slice(0, 400)}

Review the code critically. Check:
1. Does a game loop exist (requestAnimationFrame or setInterval)?
2. Is input handling wired up (keydown/keyup/click/touch)?
3. Does collision detection exist and run each frame?
4. Are game states handled (start, playing, game over)?
5. Is score tracked and displayed?

If ANY of these are missing or broken, flag it with: BROKEN: <description>
Write max 5 lines. Start each issue with BROKEN: or OK:.
${workFmt('docs/qa-cycle' + cycle + '.md', 'Playtest cycle ' + cycle)}`,

    'film-production': `Film Editor review. Cycle ${cycle}.
Feature: ${featurePriority || 'film page'} | Spec: ${techSpec ? techSpec.slice(0, 150) : ''}
Check: Are navigation links working? Does content load? Any broken interactive elements?
Write 3 notes — flag broken items with BROKEN:, working items with OK:.
${workFmt('docs/qa-cycle' + cycle + '.md', 'Editorial review cycle ' + cycle)}`,

    'ad-agency': `Brand Reviewer. Cycle ${cycle}.
Feature: ${featurePriority || 'campaign page'} | Spec: ${techSpec ? techSpec.slice(0, 150) : ''}
Check: Do CTA buttons work? Are forms functional? Any broken interactive elements?
Write 3 checks — flag broken items with BROKEN:, working items with OK:.
${workFmt('docs/qa-cycle' + cycle + '.md', 'Brand review cycle ' + cycle)}`,

    'newsroom': `Fact Checker. Cycle ${cycle}.
Feature: ${featurePriority || 'article'} | Spec: ${techSpec ? techSpec.slice(0, 150) : ''}
Check: Do nav links work? Are interactive elements functional? Any JS errors likely?
Write 3 checks — flag broken items with BROKEN:, working items with OK:.
${workFmt('docs/qa-cycle' + cycle + '.md', 'Fact check cycle ' + cycle)}`,

    'consulting': `Delivery Manager review. Cycle ${cycle}.
Feature: ${featurePriority || 'report section'} | Spec: ${techSpec ? techSpec.slice(0, 150) : ''}
Check: Do charts render? Are tables complete? Any broken interactive elements?
Write 3 checks — flag broken items with BROKEN:, working items with OK:.
${workFmt('docs/qa-cycle' + cycle + '.md', 'QA cycle ' + cycle)}`,
  };

  /* ── Builder context per category ── */
  const BUILDER_CONTEXT = {
    'game-studio':     { role: 'Senior Game Developer',            style: 'HTML5 canvas game with real physics and game loop',         palette: 'dark bg (#0a0a0f), neon accent, pixel/sharp aesthetic' },
    'film-production': { role: 'Frontend Developer for film',      style: 'cinematic, editorial HTML/CSS site',                       palette: 'dark (#0d0d0d), film-grain aesthetic, bold typography' },
    'ad-agency':       { role: 'Frontend Developer for advertising',style: 'high-converting campaign landing page',                   palette: 'brand-focused, clean, high contrast, bold CTAs' },
    'newsroom':        { role: 'Frontend Developer for digital news',style: 'editorial news/magazine site',                           palette: 'clean white/off-white, strong typography, journalistic layout' },
    'consulting':      { role: 'Frontend Developer for consulting', style: 'professional strategy report / presentation',             palette: 'white/light, navy/charcoal, data-friendly charts' },
    'tech-startup':    { role: 'Senior Full-Stack Developer',       style: 'modern web app',                                          palette: 'dark theme #07090f, accent #00e676, cards #111827' },
  };
  const ctx = BUILDER_CONTEXT[category] || BUILDER_CONTEXT['tech-startup'];

  const builderPrompt = (() => {
    const isFirstBuild = cycle === 1;
    const featureSlug  = (featurePriority || 'hero')
      .replace(/^(add|build|create|implement)\s+/i, '')
      .split(/\s+/).slice(0, 2).join('-').replace(/[^a-z0-9\-]/gi, '-').toLowerCase();

    const consoleErrors = (live.consoleErrors || []);
    const consoleNote = consoleErrors.length
      ? `\n🚨 BROWSER CONSOLE ERRORS (fix these first before adding anything new):\n${consoleErrors.slice(0, 8).map((e, i) => `${i + 1}. ${e}`).join('\n')}\n`
      : '';

    const visionCtx = live.lastVisionReport
      ? `\n📸 SCREENSHOT ANALYSIS (look at the attached screenshot — this is what users see RIGHT NOW):\n${live.lastVisionReport}\nIf this shows a loading screen, blank page, spinner, or broken UI — your PRIMARY job is to fix that, not add new features.\n`
      : '';

    const planContext = `PROJECT: ${brief}
FEATURE: ${featurePriority || 'Build from scratch.'}
TECH SPEC: ${(techSpec || 'Semantic HTML5, modern CSS, vanilla JS.').slice(0, isFix ? 800 : 600)}
DESIGN SPEC: ${(designSpec || ctx.palette).slice(0, isFix ? 600 : 400)}${visionCtx}${consoleNote}`;

    if (isFirstBuild) {
      const gameExtra = category === 'game-studio' ? `
GAME REQUIREMENTS — ALL must be present and working in cycle 1:
FILE SPLIT: data.js = state object + entity classes/constructors + spawn logic. app.js = requestAnimationFrame loop, draw(), update(), input handling.
- requestAnimationFrame game loop with update(dt) and draw(ctx) functions (in app.js)
- Input: keyboard (ArrowKeys/WASD/Space) AND mouse/touch click — use a keys:{} state map (in data.js or app.js)
- At least 2 entity types (player + enemy/obstacle) with distinct behavior
- AABB or circle collision detection running every frame
- Score counter and lives displayed on canvas as HUD
- 3 game states: START SCREEN → PLAYING → GAME OVER (with restart button/key)
- Particle explosion effect on enemy death
- The game must be FULLY PLAYABLE end-to-end. Zero stubs, zero TODOs.` : `
APP REQUIREMENTS — ALL must be present and working in cycle 1:
FILE SPLIT: data.js = state object + all setInterval simulation loops. app.js = all DOM updates, rendering, event listeners.
- Every feature mentioned in FEATURE must be implemented and functional
- All data simulation/generation must be running in data.js (setInterval, random walk)
- All UI sections rendered with real dynamic data — no hardcoded placeholder text
- All event listeners wired up (clicks, inputs, form submissions) in app.js
- Zero stubs, zero TODOs, zero placeholder comments`;

      return `${ctx.role}. Build from scratch: ${ctx.style}.

${planContext}${gameExtra}

${getCDNHint()}

⚠️ CRITICAL STACK RULE: Write ONLY vanilla HTML5 + CSS3 + plain JavaScript. NO React, NO TypeScript, NO npm, NO import/export, NO JSX, NO build tools. All files load directly in the browser via <script src="...">.
⚠️ NO TYPE ANNOTATIONS: Never write x: string, x: number, x: MyType, interface Foo {}, type Foo = ..., <T>, or 'as Type'. These are TypeScript and will crash the browser. Write plain JS: function foo(x, y) { not function foo(x: string, y: number): void {

Write one block per file, separated by ===FILE===. Required files in THIS EXACT ORDER: index.html → style.css → data.js → app.js.
⚠️ CSS MUST come second — it is written before JavaScript so the app is never unstyled even if JS is long.
SPLIT THE JAVASCRIPT INTO TWO FILES to keep each file manageable:
- data.js: ALL state objects, data simulation, setInterval loops, data generation algorithms — no DOM code, no imports
- app.js: ALL DOM updates, chart rendering, event listeners, initialization — reads globals from data.js

index.html must have: <link href="style.css"> and TWO script tags: <script src="data.js"></script> then <script src="app.js"></script>
IMPORTANT: Write COMPLETE, production-quality code. No truncation. No stubs. index.html and data.js are output first so they are never cut off.
SELF-CHECK before writing each JS file: (1) Every { has a matching }. (2) Every function called is defined somewhere. (3) DOMContentLoaded listener wraps all DOM code in app.js. (4) All setInterval/requestAnimationFrame calls are actually started. (5) No variable is declared twice.

TYPE: work
FILENAME: public/index.html
TASK: complete HTML — all sections with correct IDs and classes matching the tech spec
---
[Write the complete HTML file. Include every section. Use exact element IDs specified in tech spec. Semantic structure. Include <script src="data.js"></script><script src="app.js"></script> before </body>.]

===FILE===
TYPE: work
FILENAME: public/style.css
TASK: complete stylesheet — all CSS variables from design spec, every component fully styled, all animations
---
[Write the COMPLETE CSS file NOW — before any JavaScript. This is the highest priority visual file. Declare all :root --variables. Style every element ID and class from index.html. Dark theme, polished UI. Include all animations and transitions. Do NOT truncate.]

===FILE===
TYPE: work
FILENAME: public/data.js
TASK: all state objects, data simulation, setInterval loops, data generation — no DOM code
---
[Write ALL state: const state = {...}. Write ALL simulation: setInterval(simulatePrices, 2000). Write helper data functions. Zero DOM manipulation here — only pure data logic.]

===FILE===
TYPE: work
FILENAME: public/app.js
TASK: all DOM updates, chart rendering, event listeners, initialization — reads state from data.js
---
[Write ALL DOM code: renderChart(), updatePrices(), bindEvents(). Initialize on DOMContentLoaded. References state defined in data.js. No stubs.]

No text before first TYPE: or after last block.`;
    }

    // FIX MODE — rewrite the broken file completely
    if (isFix) {
      // Find which HTML page is referenced in the FIX task (e.g. "/dashboard.html")
      const referencedPage = (featurePriority.match(/\/([a-z0-9\-_]+\.html)/i) || [])[1] || '';
      const referencedHtml = referencedPage ? readFile(`public/${referencedPage}`) : '';

      // Build context for all existing HTML pages (capped to avoid token overload)
      const allPagesCtx = existingHtmlPages
        .map(f => {
          const content = readFile(`public/${f}`);
          return content ? `=== public/${f} (${content.split('\n').length} lines) ===\n${content.slice(0, 600)}` : '';
        })
        .filter(Boolean)
        .join('\n\n')
        .slice(0, 2000);

      const dataJsCtx = dataJs ? `\nCURRENT data.js (FULL):\n${dataJs}\n` : '';
      // Extract element IDs from current index.html so builder can match them
      const htmlIds = [...html.matchAll(/\bid=["']([^"']+)["']/gi)].map(m => m[1]);
      const htmlIdsNote = htmlIds.length
        ? `\nELEMENT IDs IN CURRENT index.html: ${htmlIds.slice(0, 40).join(', ')}\n⚠️ YOUR JS MUST USE THESE EXACT IDs — do NOT invent new ones unless you also rewrite index.html.\n`
        : '';
      return `${ctx.role}. FIX broken logic in existing ${ctx.style}.

${planContext}
FIX TASK: ${featurePriority}

CURRENT app.js (FULL):
${appJs || '(empty — write it from scratch)'}
${dataJsCtx}${htmlIdsNote}
${referencedHtml ? `CURRENT ${referencedPage} (FULL — this is the page to fix JS for):\n${referencedHtml.slice(0, 1500)}` : `EXISTING HTML PAGES:\n${allPagesCtx || html.slice(-600)}`}

Instructions:
- Output the COMPLETE rewritten file(s) with ALL required logic implemented (no stubs, no TODOs)
- If data.js exists, keep state/simulation there; put DOM/rendering code in app.js
- ⚠️ CRITICAL: Your JS must use the EXACT element IDs listed in "ELEMENT IDs IN CURRENT index.html" above
- If the JS needs different IDs than what index.html has, rewrite index.html FIRST as a ===FILE=== block
- Fix every issue described in the FIX TASK
- For game-studio: ensure game loop runs, input works, collision detects, score updates, game states transition correctly
- Only include style.css block if CSS also needs fixing

SELF-CHECK before writing each JS file: (1) Every { has a matching }. (2) Every getElementById/querySelector target exists in the HTML. (3) DOMContentLoaded wraps all DOM code. (4) All setInterval/RAF calls are started. (5) No variable declared twice.

Write one block per file, separated by ===FILE===:

TYPE: work
FILENAME: public/app.js
TASK: fix ${featureSlug}
---
[COMPLETE working app.js — targeting the EXACT element IDs from current index.html]

Only output files that need changing. No text before first TYPE: or after last block.`;
    }

    return `${ctx.role}. Add feature to existing ${ctx.style}.

${planContext}

Pages: ${existingPages}
${featuresCtx ? `FEATURES BUILT SO FAR:\n${featuresCtx}\n` : ''}
CURRENT data.js (you MUST preserve all of this plus add the new feature):
${summarizeJs(dataJs)}

CURRENT app.js (you MUST preserve all of this plus add the new feature):
${summarizeJs(appJs)}

⚠️ STACK RULE: Vanilla HTML/CSS/JavaScript ONLY. No React, no TypeScript, no import/export.
⚠️ FULL REWRITE RULE: Output COMPLETE replacement files for data.js and app.js — the server replaces the entire file each cycle. You MUST include ALL existing code from the "CURRENT" sections above plus your new additions. Do NOT omit any existing function or state.
⚠️ NO STRICT MODE: Do NOT write 'use strict'. No TypeScript type annotations.
SELF-CHECK before writing each JS file: (1) Every { has a matching }. (2) All functions listed in FEATURES BUILT are present. (3) DOMContentLoaded wraps all DOM code in app.js. (4) No variable declared twice. (5) All setInterval/RAF calls are started.

TYPE: work
FILENAME: public/style.css
TASK: ${featureSlug} styles — new CSS rules for this feature only
---
[new CSS for this feature only — complete styles, no placeholders]

===FILE===
TYPE: work
FILENAME: public/data.js
TASK: complete data.js — all existing state/simulation plus new feature
---
[COMPLETE data.js — ALL existing state objects and simulation loops from CURRENT data.js above, PLUS new feature data and logic. No omissions.]

===FILE===
TYPE: work
FILENAME: public/app.js
TASK: complete app.js — all existing DOM code plus new feature
---
[COMPLETE app.js — ALL existing render/event/init functions from CURRENT app.js above, PLUS new feature implementation. No omissions.]

New page → full document with <link href="style.css"> + <script src="data.js"></script><script src="app.js"></script>. Existing HTML → new section only (server injects before </body>).
No text before first TYPE: or after last block.`;
  })();

  /* ── Assemble final map ── */
  const screenshotNote = live.previewScreenshot
    ? 'A screenshot of the current website is attached — use it to visually assess what is working or broken before making your decision.\n\n'
    : '';
  const map = {
    ceo:        screenshotNote + customerNote + searchNote + (CEO_PROMPTS[category] || CEO_PROMPTS['tech-startup']),
    'lead-eng': LEAD_ENG_PROMPTS[category] || `You are Lead Engineer. Cycle ${cycle}.
Task: ${featurePriority || 'Build the full website from scratch.'}${customerCtx}${searchNote}
Pages: ${existingHtmlPages.join(', ') || 'none'} | Size: ${htmlLines}L HTML, ${cssLines}L CSS, ${jsLines}L JS
${isFix ? `Current app.js:\n${jsSnapshot.slice(0, 600)}` : ''}
${isFix
  ? `Write a FIX spec (≤120 words): identify broken functions, exact code to rewrite, correct event handlers, data flow, and DOM interactions.`
  : `Write tech spec (≤100 words): target file, HTML element IDs, CSS classes, JS functions needed.`}
${workFmt('docs/technical-spec.md', (isFix ? 'Fix spec' : 'Tech spec') + ' cycle ' + cycle)}`,
    designer:   DESIGNER_PROMPTS[category] || `You are UI Designer. Cycle ${cycle}.
Feature: ${featurePriority || 'Design the page.'}${customerCtx}
Spec: ${techSpec ? techSpec.slice(0, 150) : ''}
Write design spec (≤80 words): colors, layout, component appearance.
${workFmt('docs/design-spec.md', 'Design spec cycle ' + cycle)}`,
    builder:    builderPrompt,
    qa:         QA_PROMPTS[category]       || `QA Engineer. Cycle ${cycle}.
Feature: ${featurePriority || 'landing page'} | Spec: ${techSpec ? techSpec.slice(0, 150) : ''}
Write 3 Given/When/Then test cases.
${workFmt('docs/qa-cycle' + cycle + '.md', 'QA cycle ' + cycle)}`,
    sales: `You are Sales Lead. Project: "${brief}". Cycle ${cycle}.
Write a targeted cold outreach email to a potential customer or partner.
${workFmt('sales/outreach-v' + live.salesV + '.md', 'Outreach email v' + live.salesV)}`,
  };

  return map[agentId] || map.ceo;
}

module.exports = { buildPrompt };
