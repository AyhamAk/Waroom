/* ══════════════════════════════════════════════
   WAR ROOM — AGENT PROMPTS
   Category-aware prompt builder for Phase 4 live pipeline.
   buildPrompt(agentId, live) → string
   ══════════════════════════════════════════════ */

const fs   = require('fs');
const path = require('path');

const { getCDNHint } = require('./tools/cdnResolver');

async function buildPrompt(agentId, live, searchResults = '') {
  const brief    = live.brief.slice(0, 600);
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

  // Cross-cycle agent memory: prevents regressions and repeated decisions.
  const memoryRaw = readFile('docs/agent-memory.json');
  let memoryCtx = '';
  try {
    const mem = JSON.parse(memoryRaw);
    if (mem.lastCycle >= 1) {
      const bugs = (mem.openBugs || []).length ? `Open bugs: ${mem.openBugs.join('; ')}` : '';
      const fns  = (mem.jsFunctions || []).length ? `Functions built: ${mem.jsFunctions.slice(0, 15).join(', ')}` : '';
      memoryCtx = `\n📋 AGENT MEMORY (cross-cycle — do NOT contradict these):
Past decisions: ${(mem.decisions || []).join(' → ')}
Files: ${(mem.filesBuilt || []).join(', ')}
${fns}${bugs ? '\n' + bugs : ''}${mem.hasBackend ? '\nReal backend running at /backend — frontend uses fetch("/backend/...")' : ''}\n`;
    }
  } catch { /* no memory yet — cycle 1 */ }

  // Summarize a JS file for builder context: show full content up to maxChars,
  // then list any additional function names that were cut off.
  function summarizeJs(code, maxChars = 8000) {
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
${roadmapCtx}${memoryCtx}
UI SECTIONS BUILT: ${sectionList}
JS FUNCTIONS IMPLEMENTED: ${jsFunctions}
COMPLETED CYCLES: ${donePriorities}
Last cycle: ${lastPriority || 'nothing yet'}
QA last cycle: ${lastQA ? lastQA.slice(0, 300) : 'N/A'}
TECH SPEC SUMMARY: ${techSpec ? techSpec.slice(0, 300) : 'none yet'}
${fixLimitNote}
DECISION RULES (follow in strict order — stop at first match):
1. If VISUAL ANALYSIS says BROKEN or health score ≤ 4 → FIX: <be specific — name the broken component and what exactly is wrong>
2. NEVER repeat last cycle's decision.
3. If QA flagged broken logic AND last cycle was NOT already a FIX for the same issue → FIX: <specific>
4. If JS functions = "none yet" and cycle > 1 → FIX: implement all JS interactivity — data simulation, DOM updates, event handlers
5. If the next feature requires modifying or replacing existing logic (not just adding a new section) → FIX: <describe the restructuring needed>. Use FIX for integration work, not just bugs.
6. If VISION shows health score ≥ 8 AND all features from the brief are implemented AND QA has no BROKEN → output: DONE: <one sentence reason>. Only use DONE when genuinely complete.
7. Otherwise → pick the HIGHEST-IMPACT next item from the roadmap (or invent the best next feature if no roadmap).
   - NEW PAGE: /name.html — one sentence description
   - SECTION: one sentence description
   Pages so far: ${existingHtmlPages.length}. Prefer new pages after 4+ sections on index.html.
${cycle === 1 ? `
Also output a product roadmap (second file) — 6–8 bullet points covering the complete product vision.` : ''}
Output exactly ONE line: FIX: ... (bugs OR structural changes) | NEW PAGE: ... | SECTION: ... | DONE: ...
${cycle === 1
  ? workFmt('docs/feature-priority.md', 'Feature decision for cycle 1') + '\n\n' +
    `===FILE===\nRespond in this EXACT format, no other text:\nTYPE: work\nFILENAME: docs/product-roadmap.md\nTASK: Product roadmap\n---\n<roadmap content here>`
  : workFmt('docs/feature-priority.md', 'Feature decision for cycle ' + cycle)}`,

    'game-studio': `You are Game Director. Game: "${brief}". Cycle ${cycle}. Stack: Phaser 3 (scenes, arcade physics, programmatic textures).
Built: ${sectionList}
Done: ${donePriorities}
Last cycle: ${lastPriority || 'nothing yet'}
QA last cycle: ${lastQA ? lastQA.slice(0, 300) : 'N/A'}
JS size: ${jsLines} lines
${fixLimitNote}
DECISION RULES (follow in strict order — stop at first match):
1. Cycle 1 → always: SECTION: complete Phaser 3 game — BootScene (programmatic textures), GameScene (physics, input, collision, score, lives), GameOverScene (restart)
2. If VISUAL ANALYSIS says BROKEN or health score ≤ 4 → FIX: <be specific — Phaser config wrong, scene not starting, physics not set up, black screen because textures not generated, etc.>
3. NEVER output anything identical or nearly identical to "Last cycle" above.
4. If QA flagged game-breaking bugs AND last cycle was NOT already a FIX for the same issue → FIX: <specific Phaser fix>
5. If JS < 150 lines → FIX: implement all 3 Phaser scenes with physics, input, collision detection, HUD, and game over flow
6. If VISION shows health score ≥ 8 AND game is fully playable AND QA has no BROKEN → output: DONE: <one sentence reason>. Only use DONE when game is genuinely complete.
7. Otherwise → add ONE new mechanic (output as SECTION):
   - Power-ups (speed boost, shield, multi-shot)
   - New enemy type with different AI (homing, zigzag, splitting)
   - Level/wave progression with difficulty scaling
   - Leaderboard / high score persistence (localStorage)
   - Sound effects (Phaser sound manager + Howler.js)
   - Boss fight with health bar

Output exactly ONE line: FIX: ... OR SECTION: ... OR DONE: ...
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

  // Sanitize search results to prevent prompt injection attacks.
  // Strip any text that looks like instruction overrides embedded in SEO content.
  function sanitizeSearchResults(raw) {
    if (!raw) return '';
    return raw
      .slice(0, 2000) // hard cap
      .replace(/\b(ignore|disregard|forget|override|system\s*:|new\s+instructions?|you\s+are\s+now)\b[\s\S]{0,200}/gi, '[removed]')
      .replace(/TYPE\s*:\s*work/gi, '[removed]') // prevent fake file blocks
      .replace(/FILENAME\s*:/gi, '[removed]');
  }
  const searchNote = searchResults
    ? `\nWEB SEARCH RESULTS (use to inform your decision):\n${sanitizeSearchResults(searchResults)}\n`
    : '';

  /* ── Lead Engineer prompts per category ── */
  const LEAD_ENG_PROMPTS = {
    'tech-startup': `You are Lead Engineer. Cycle ${cycle}.
Task: ${featurePriority || 'Build the full app from scratch.'}${customerCtx}${searchNote}${memoryCtx}
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
    'game-studio': `Phaser 3 QA Engineer. Cycle ${cycle}.
Feature built: ${featurePriority || 'core game'} | JS size: ${jsLines} lines
App.js sample: ${jsSnapshot.slice(0, 500)}

Review the Phaser 3 code critically. Check:
1. Does new Phaser.Game(config) exist with parent: 'game-container' and scene array?
2. Do all scene classes extend Phaser.Scene with correct constructor super({ key: '...' })?
3. Does BootScene.preload() generate textures programmatically (generateTexture)?
4. Does GameScene.create() set up physics sprites, overlap/collider, keyboard input, and HUD text?
5. Does GameScene.update() run player movement, shooting, and win/lose checks?
6. Does GameOverScene show score and have a restart button?

If ANY of these are missing or broken, flag it with: BROKEN: <description>
Write max 6 lines. Start each issue with BROKEN: or OK:.
${workFmt('docs/qa-cycle' + cycle + '.md', 'Phaser QA cycle ' + cycle)}`,

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
    'game-studio':     { role: 'Senior Phaser 3 Game Developer',     style: 'Phaser 3 HTML5 game with scenes, physics, and input',palette: 'dark bg (#0a0a0f), neon accent, pixel/sharp aesthetic',          framework: 'vanilla' },
    'film-production': { role: 'Frontend Developer for film',       style: 'cinematic Vue 3 site',                               palette: 'dark (#0d0d0d), film-grain aesthetic, bold typography',           framework: 'vue' },
    'ad-agency':       { role: 'Frontend Developer for advertising', style: 'Vue 3 campaign page',                               palette: 'brand-focused, clean, high contrast, bold CTAs',                 framework: 'vue' },
    'newsroom':        { role: 'Frontend Developer for digital news', style: 'Vue 3 editorial site',                             palette: 'clean white/off-white, strong typography, journalistic layout',  framework: 'vue' },
    'consulting':      { role: 'Frontend Developer for consulting',  style: 'Vue 3 strategy report',                             palette: 'white/light, navy/charcoal, data-friendly charts',               framework: 'vue' },
    'tech-startup':    { role: 'Senior Full-Stack Developer',        style: 'modern dark web app',                                palette: 'dark theme #07090f, accent #00e676, cards #111827',              framework: 'vanilla' },
  };
  const ctx = BUILDER_CONTEXT[category] || BUILDER_CONTEXT['tech-startup'];
  const isVue = ctx.framework === 'vue';

  // Smart library hints — scans the brief and suggests the best CDN library to use.
  // Tells the builder to reach for Chart.js, Phaser, GSAP etc. instead of building from scratch.
  function getSmartLibraryHints() {
    if (category === 'game-studio') return ''; // games have their own Phaser guidance
    const b = (brief || '').toLowerCase();
    const hints = [];
    if (/chart|graph|dashboard|analytic|metric|stat|visuali|trading|crypto|stock|price|candlestick/.test(b))
      hints.push('📊 Chart.js (CDN ready): new Chart(canvasEl, { type: "line"|"bar"|"doughnut", data: { labels, datasets:[{data,borderColor}] }, options })');
    if (/3d|cube|sphere|rotate|model|scene|render|vr|ar|three/.test(b))
      hints.push('🧊 Three.js (CDN ready): new THREE.Scene() + Camera + WebGLRenderer + lights + meshes + animation loop');
    if (/physic|bounce|collide|gravity|rigid|simulat|pendulum|billiard/.test(b))
      hints.push('⚙️ Matter.js (CDN ready): Engine.create(), Bodies.rectangle/circle(), World.add(), Render.create()');
    if (/animat|motion|tween|smooth|transition|parallax|morph/.test(b))
      hints.push('✨ GSAP (CDN ready): gsap.to(el, { duration:1, x:100, opacity:0, ease:"power2.out" }) — far better than CSS transitions');
    if (/music|audio|sound|beat|synth|tone|instrument|piano/.test(b))
      hints.push('🔊 Tone.js (CDN ready): new Tone.Synth().toDestination(); synth.triggerAttackRelease("C4","8n") — or Howler.js for playback');
    if (/map|geo|topolog|d3|network|tree|force|hierarch/.test(b))
      hints.push('🗺️ D3.js (CDN ready): d3.select/selectAll, scales, axes, line/area/bar generators, force simulation');
    if (/confetti|celebrat|firework|particle|effect/.test(b))
      hints.push('🎉 Confetti (CDN ready): confetti({ particleCount:150, spread:90, origin:{y:0.6} })');
    if (/markdown|code|highlight|syntax|editor/.test(b))
      hints.push('📝 Marked.js (CDN ready): marked.parse(markdownString) → HTML; Highlight.js for syntax coloring');
    return hints.length
      ? `\n💡 POWER-UP HINTS — use these CDN libraries instead of building from scratch:\n${hints.join('\n')}\n`
      : '';
  }

  const builderPrompt = (() => {
    const isFirstBuild = cycle === 1;
    const featureSlug  = (featurePriority || 'hero')
      .replace(/^(add|build|create|implement)\s+/i, '')
      .split(/\s+/).slice(0, 2).join('-').replace(/[^a-z0-9\-]/gi, '-').toLowerCase();

    const consoleErrors = (live.consoleErrors || []);
    const consoleNote = consoleErrors.length
      ? `\n🚨 BROWSER CONSOLE ERRORS (${consoleErrors.length}) — FIX THESE FIRST:\n${consoleErrors.slice(0, 12).map((e, i) => {
          const type = /getElementById|querySelector|null|undefined/.test(e) ? '🔗 DOM'
            : /syntax|unexpected|token/i.test(e) ? '⚠️ SYNTAX'
            : /fetch|network|cors|404/i.test(e) ? '🌐 NETWORK'
            : /cannot read|typeerror/i.test(e) ? '💥 RUNTIME' : '❓ OTHER';
          return `  ${type} ${i + 1}. ${e}`;
        }).join('\n')}\n`
      : '';

    const visionCtx = live.lastVisionReport
      ? `\n📸 SCREENSHOT ANALYSIS (look at the attached screenshot — this is what users see RIGHT NOW):\n${live.lastVisionReport}\nIf this shows a loading screen, blank page, spinner, or broken UI — your PRIMARY job is to fix that, not add new features.\n`
      : '';

    const backendNote = live.backendPort
      ? `\n🔌 REAL BACKEND RUNNING at http://localhost:${live.backendPort} (proxied via /backend):
- Use fetch('/backend/...') for ALL data reads and writes in app.js and data.js.
- Replace ALL setInterval simulations with fetch() calls + setInterval polling.
- data.js: fetch initial data on load, then poll every 3-5s with fetch.
- app.js: handle fetch responses and update the DOM with real data.
- Example: fetch('/backend/api/prices').then(r=>r.json()).then(updatePrices);\n`
      : '';

    const planContext = `PROJECT: ${brief}
FEATURE: ${featurePriority || 'Build from scratch.'}
TECH SPEC: ${(techSpec || 'Semantic HTML5, modern CSS, vanilla JS.').slice(0, isFix ? 800 : 2000)}
DESIGN SPEC: ${(designSpec || ctx.palette).slice(0, isFix ? 600 : 800)}${visionCtx}${consoleNote}${memoryCtx}${backendNote}`;

    if (isFirstBuild) {
      const buildPhase = live._buildPhase || 1;

      /* ── PHASE 1: HTML structure + complete CSS ── */
      if (buildPhase === 1) {
        const selfPlan = isVue
          ? `PLANNING STEP (decide before writing any HTML):
1. List every reactive data property this app needs (e.g. prices: {}, portfolio: {}, selectedCoin: 'BTC')
2. List every method name (e.g. refreshPrices, buyCoins, formatCurrency)
3. List every computed property (e.g. totalValue, profitPct)
4. Pick a color accent that fits the domain (base: #07090f dark)
These become data(), methods{}, computed{} in app.js — be consistent.`.trim()
          : `PLANNING STEP (decide before writing any HTML):
1. List every UI section this app needs (e.g. header, price-ticker, chart, portfolio-table, footer)
2. Assign an element ID to each interactive/dynamic element (e.g. id="price-chart", id="btc-price")
3. Pick a color accent that fits the domain (base: #07090f dark)
These IDs will be used verbatim in the JavaScript — be consistent.`.trim();

        const htmlStructureHint = category === 'game-studio'
          ? `PHASER 3 HTML: Keep HTML minimal — Phaser creates its own canvas inside the container.
Include <div id="game-container"> — Phaser renders here. NO <canvas> tag needed.
Add <div id="ui-menu" class="game-overlay"> for start/gameover HTML screens layered over the game.
Include: <script src="https://cdnjs.cloudflare.com/ajax/libs/phaser/3.60.0/phaser.min.js"></script> BEFORE <script src="app.js"></script>.
CSS: body{margin:0;background:#0a0a0f;display:flex;align-items:center;justify-content:center;height:100vh}
     #game-container{position:relative} .game-overlay{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;z-index:10;background:rgba(0,0,0,0.85)}`
          : `⚠️ VUE 3 TEMPLATE: Use <div id="app"> as the root — Vue mounts here.
Use {{ property }} for text output. Use @click="method" for events. Use v-for="item in list" :key="item.id" for lists. Use :class/:style for dynamic binding. Use v-if/v-else for conditionals.
Do NOT use element IDs for JS targeting (CSS IDs are fine, just no getElementById in JS).
Place <!-- END APP --> just before the closing </div> of <div id="app"> — cycle 2+ injects new sections here.
Include <script src="https://cdnjs.cloudflare.com/ajax/libs/vue/3.4.21/vue.global.prod.min.js"></script> BEFORE <script src="app.js"></script>.
💅 BULMA CSS (zero layout CSS needed): Add <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/bulma/0.9.4/css/bulma.min.css"> to <head>.
Use Bulma classes: columns/column (flex grid), card/card-content, button/is-primary/is-danger, navbar, hero/hero-body, section, container, table, tag/is-success, notification, progress, modal.
Your style.css only needs: :root color variables + brand overrides + dark background + custom animations. Let Bulma handle all layout and component structure.`;

        const scriptTags = isVue
          ? `<script src="https://cdnjs.cloudflare.com/ajax/libs/vue/3.4.21/vue.global.prod.min.js"></script><script src="app.js"></script>`
          : category === 'game-studio'
            ? `<script src="https://cdnjs.cloudflare.com/ajax/libs/phaser/3.60.0/phaser.min.js"></script><script src="app.js"></script>`
            : `<script src="data.js"></script><script src="app.js"></script>`;

        // ── Vanilla (tech-startup): output plan + HTML + CSS as one coherent call ──
        // The plan is written FIRST so both the HTML (this call) and JS (Phase 2) use the same IDs.
        if (!isVue && category !== 'game-studio') {
          return `${ctx.role}. CYCLE 1 PHASE 1 — Design the architecture, then build HTML + CSS.

PROJECT: ${brief}
DESIGN: ${(designSpec || ctx.palette).slice(0, 800)}${memoryCtx}
${getSmartLibraryHints()}
QUALITY BAR — output MUST meet ALL of these:
- Every section from the brief has real content (no "Lorem ipsum", no "Coming soon")
- At least 5 distinct interactive elements (buttons, inputs, toggles, tabs, cards)
- CSS uses custom properties (--variables) with a cohesive dark color system
- Mobile responsive with at least one @media breakpoint
- The page must look like a real product, not a template

WRITE 3 FILES IN THIS EXACT ORDER:

① docs/build-plan.md — YOUR BINDING CONTRACT (write this first; Phase 2 will follow it exactly)
   Include:
   SECTIONS: every UI panel with its exact id= string (e.g. id="price-ticker", id="chart-canvas")
   STATE:    the complete \`const state = { }\` object with ALL fields and realistic seed values
   DATA.JS FUNCTIONS: name every simulation/update function (e.g. simulatePrices, updatePortfolio)
   APP.JS FUNCTIONS:  name every render/event function (e.g. renderTicker, handleBuy, initChart)
   LIBS:     CDN library choices and why

② public/index.html — Use EXACTLY the element IDs from your plan
   Vanilla HTML5 only. No frameworks. No inline JS.
   <link rel="stylesheet" href="style.css"> in <head>
   <script src="data.js"></script><script src="app.js"></script> before </body>
   Every section from the brief gets a real DOM structure with real labels and content.

③ public/style.css — Target EXACTLY the IDs and classes from your index.html
   :root with --bg, --surface, --accent, --text, --border, --success, --danger
   Dark theme #07090f. Cards with box-shadow. Typography scale. Hover transitions. @media (max-width:768px).
\x00CACHE_SPLIT\x00
${getCDNHint()}

TYPE: work
FILENAME: docs/build-plan.md
TASK: architecture plan — the contract between Phase 1 and Phase 2
---
SECTIONS:
  [list every UI panel: name — id="exact-id-here"]
STATE:
  const state = {
    [every field with type and seed value, e.g. prices: { BTC: 43250, ETH: 2280 }]
  };
DATA.JS FUNCTIONS:
  [e.g. simulatePrices() — setInterval, updates state.prices every 2s]
APP.JS FUNCTIONS:
  [e.g. renderTicker() — writes to #price-ticker, called from data.js after each update]
LIBS:
  [e.g. Chart.js — for price history line chart on #chart-canvas]

===FILE===
TYPE: work
FILENAME: public/index.html
TASK: complete HTML — every section with exact IDs from the plan
---
[COMPLETE HTML using the element IDs from docs/build-plan.md. Every section from the brief. Real content, real labels. No placeholder text.]

===FILE===
TYPE: work
FILENAME: public/style.css
TASK: complete CSS — targets every ID and class in index.html
---
[COMPLETE CSS. :root variables first. Style EVERY element ID and class from the HTML. Dark theme. Cards, shadows, colors, transitions, responsive.]

No text before first TYPE: or after last block.`;
        }

        // ── Vue / game-studio Phase 1: existing path ──
        return `${ctx.role}. PHASE 1 of 2 — Build the visual shell for: ${ctx.style}

${selfPlan}

PROJECT: ${brief}
DESIGN: ${(designSpec || ctx.palette).slice(0, 800)}${memoryCtx}

YOUR TASK THIS PHASE: Output ONLY index.html and style.css. NO JavaScript yet.
${htmlStructureHint}
\x00CACHE_SPLIT\x00
${getCDNHint()}${getSmartLibraryHints()}
⚠️ Write style.css FIRST so the page renders styled immediately.
${isVue
  ? `⚠️ Vue template syntax ONLY in HTML. No vanilla JS. The <div id="app"> is the Vue root.`
  : `⚠️ Vanilla HTML5 + CSS3 ONLY. No JavaScript in this phase.\n⚠️ Use descriptive element IDs that JavaScript can target: id="btc-price", id="portfolio-table", id="chart-canvas"`}

TYPE: work
FILENAME: public/style.css
TASK: complete stylesheet — all CSS variables, every section styled, animations, mobile responsive
---
[Write the COMPLETE CSS. :root with all --variables (--bg, --surface, --accent, --text, --border, --success, --danger). Style EVERY element ID and class. Dark theme with accent color. Cards with shadows. Typography scale. Hover/transition states. Mobile responsive @media (max-width: 768px). Polished production quality. Do NOT truncate.]

===FILE===
TYPE: work
FILENAME: public/index.html
TASK: complete HTML — semantic structure with all UI sections${isVue ? ' using Vue template syntax' : ' and their element IDs'}
---
[Write the COMPLETE HTML. Every section from the brief gets its own element. Link <link rel="stylesheet" href="style.css">. Add ${scriptTags} before </body>. No inline JS. No placeholder text — write real labels and structure.]

No text before first TYPE: or after last block.`;
      }

      /* ── PHASE 2: JS logic — Vue path (app.js only) or vanilla path (data.js + app.js) ── */

      if (isVue) {
        // Vue 3: single app.js with createApp. No data.js needed.
        // Read the actual HTML template to understand what bindings to implement.
        const actualHtml = readFile('public/index.html') || html;

        return `${ctx.role}. PHASE 2 of 2 — Build the Vue 3 JavaScript for: ${ctx.style}

PROJECT: ${brief}
The HTML template and CSS are already written. Your ONLY job: implement the Vue 3 app.js.

TEMPLATE ANALYSIS — look at index.html and implement ALL of:
- Every {{ expression }} → must be a data() property or computed{}
- Every @event="method" → must be in methods{}
- Every v-model="prop" → must be in data()
- Every v-for="item in list" → list must be in data() (initialize as array)
- Every :attr="expr" → expr must resolve on the Vue instance

ACTUAL INDEX.HTML (reference this — implement every binding you see):
${actualHtml.slice(0, 6000)}

${memoryCtx}${backendNote}${getSmartLibraryHints()}
⚠️ OUTPUT: ONE file only — public/app.js. No data.js needed (all state lives in Vue data()).
⚠️ NO getElementById, no querySelector, no document.* DOM manipulation — Vue handles all DOM reactively.
⚠️ Use this.propertyName inside methods{} and mounted() — not window globals.
⚠️ Simulations in mounted(): setInterval(() => { this.prices.BTC *= (1 + (Math.random()-0.5)*0.02); }, 2000)
⚠️ Initialize data() with realistic seed values so the app looks live immediately (not empty arrays/zeros).
SELF-CHECK: (1) Every {{ expr }} in the HTML has a matching data() key or computed. (2) Every @click="x" has method x defined. (3) mounted() starts all simulations and initial data loads. (4) No getElementById anywhere. (5) No import/export statements.

TYPE: work
FILENAME: public/app.js
TASK: complete Vue 3 app — data, computed, methods, mounted
---
[Write the COMPLETE app.js using Vue 3 Options API:
const { createApp } = Vue;
createApp({
  data() {
    return {
      // ALL reactive state with realistic seed data
    };
  },
  computed: {
    // derived values: totals, percentages, formatted strings
  },
  methods: {
    // ALL event handlers and data mutations
    // Use this.x to access/mutate data properties
  },
  mounted() {
    // Start ALL simulations: setInterval(() => { this.x = ...; }, interval)
    // Initial data loads, fetch calls
    // this.x refers to data properties
  }
}).mount('#app');
ZERO getElementById. ZERO external state globals. ZERO imports. Fully functional from first page load.]

No text before TYPE: or after last block.`;
      }

      // ── Vanilla Phase 2: read plan + HTML, write data.js + app.js ──
      if (!isVue && category !== 'game-studio') {
        const actualHtml = readFile('public/index.html') || html;
        const buildPlan  = readFile('docs/build-plan.md');

        return `${ctx.role}. CYCLE 1 PHASE 2 — Implement the JavaScript.

PROJECT: ${brief}
The HTML and CSS are already written. Write data.js and app.js that bring them to life.

BUILD PLAN — follow this EXACTLY (use these IDs, state fields, and function names):
${buildPlan
  ? buildPlan.slice(0, 3000)
  : 'No plan file found — derive state model and element IDs from the HTML below.'}

ACTUAL index.html (target ONLY the element IDs you see here):
${actualHtml.slice(0, 5000)}

${memoryCtx}${backendNote}${getSmartLibraryHints()}
RULES:
⚠️ Vanilla JS ONLY. No imports, no modules, no TypeScript, no frameworks.
⚠️ data.js loads FIRST — define \`const state = {...}\` globally and start all setIntervals here.
⚠️ app.js loads SECOND — wire all DOM events, call render functions, start on DOMContentLoaded.
⚠️ getElementById/querySelector targets must match EXACTLY the IDs in the HTML above.
⚠️ Initialize state with realistic seed data so the app looks live from first load.
⚠️ ZERO placeholder functions, ZERO stubs, ZERO TODOs — every function fully implemented.

SELF-CHECK: (1) Every element ID referenced in JS exists in the HTML. (2) DOMContentLoaded wraps all DOM code in app.js. (3) setInterval simulations start in data.js. (4) No variable declared twice across both files. (5) Removing either file would break the app — both files are needed.

TYPE: work
FILENAME: public/data.js
TASK: state object + all simulation/update functions
---
[COMPLETE data.js:
- const state = { ALL fields with realistic seed values }
- ALL simulation functions (setInterval loops that mutate state and call render functions)
- Helper functions (formatCurrency, formatPct, randomWalk, etc.)
- Call initSimulations() at the bottom to start all intervals
Every function from DATA.JS FUNCTIONS in the plan — fully implemented, no stubs.]

===FILE===
TYPE: work
FILENAME: public/app.js
TASK: DOM wiring + all render/event functions
---
[COMPLETE app.js wrapped in DOMContentLoaded:
document.addEventListener('DOMContentLoaded', () => {
  // ALL render functions — update DOM elements by their exact IDs from the HTML
  // ALL event handlers — buttons, inputs, tabs, selectors
  // Initial render calls — populate every panel on first load
  // Any Chart.js or library initialization if used
});
Every function from APP.JS FUNCTIONS in the plan — fully implemented, no stubs.]

No text before first TYPE: or after last block.`;
      }

      // Phaser 3 path (game-studio) — single app.js with scene classes
      // Working scaffold: customize this instead of starting from scratch
      const phaserScaffold = `class BootScene extends Phaser.Scene {
  constructor() { super({ key: 'Boot' }); }
  preload() {
    // Generate ALL textures here programmatically — zero external files needed
    const g = this.make.graphics({ x: 0, y: 0, add: false });
    g.fillStyle(0x00e676); g.fillRect(0, 0, 32, 32); g.generateTexture('player', 32, 32);
    g.clear(); g.fillStyle(0xff4444); g.fillTriangle(16,0, 32,32, 0,32); g.generateTexture('enemy', 32, 32);
    g.clear(); g.fillStyle(0xffff00); g.fillCircle(4, 4, 4); g.generateTexture('bullet', 8, 8);
    g.destroy();
  }
  create() { this.scene.start('Game'); }
}

class GameScene extends Phaser.Scene {
  constructor() { super({ key: 'Game' }); }
  create() {
    this.score = 0; this.lives = 3; this.wave = 1;
    this.player = this.physics.add.sprite(400, 540, 'player').setCollideWorldBounds(true);
    this.enemies = this.physics.add.group();
    this.bullets = this.physics.add.group({ runChildUpdate: true });
    this.scoreText = this.add.text(16, 16, 'Score: 0', { fontSize: '20px', color: '#0ff' }).setScrollFactor(0);
    this.livesText = this.add.text(16, 44, 'Lives: 3', { fontSize: '18px', color: '#f66' }).setScrollFactor(0);
    this.waveText  = this.add.text(16, 72, 'Wave: 1',  { fontSize: '18px', color: '#ff0' }).setScrollFactor(0);
    this.cursors = this.input.keyboard.createCursorKeys();
    this.wasd = this.input.keyboard.addKeys({ up:'W', left:'A', down:'S', right:'D' });
    this.fireKey = this.input.keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.SPACE);
    this.physics.add.overlap(this.bullets, this.enemies, this.hitEnemy, null, this);
    this.physics.add.overlap(this.player, this.enemies, this.playerHit, null, this);
    this.spawnTimer = this.time.addEvent({ delay: 1200, callback: this.spawnEnemy, callbackScope: this, loop: true });
    this.lastFired = 0;
  }
  update(time, delta) {
    this.player.setVelocity(0);
    if (this.cursors.left.isDown  || this.wasd.left.isDown)  this.player.setVelocityX(-280);
    if (this.cursors.right.isDown || this.wasd.right.isDown) this.player.setVelocityX(280);
    if (this.cursors.up.isDown    || this.wasd.up.isDown)    this.player.setVelocityY(-280);
    if (this.cursors.down.isDown  || this.wasd.down.isDown)  this.player.setVelocityY(280);
    if (Phaser.Input.Keyboard.JustDown(this.fireKey) || (time - this.lastFired > 250 && this.fireKey.isDown)) {
      this.fireBullet(); this.lastFired = time;
    }
  }
  fireBullet() {
    const b = this.bullets.create(this.player.x, this.player.y - 20, 'bullet');
    b.setVelocityY(-500); b.setActive(true); b.setVisible(true);
    b.update = () => { if (b.y < 0) b.destroy(); };
  }
  spawnEnemy() {
    const x = Phaser.Math.Between(32, 768);
    const e = this.enemies.create(x, 32, 'enemy');
    e.setVelocityY(60 + this.wave * 15);
    e.checkWorldBounds = true; e.outOfBoundsKill = true;
  }
  hitEnemy(bullet, enemy) {
    bullet.destroy(); enemy.destroy();
    this.score += 10; this.scoreText.setText('Score: ' + this.score);
    this.cameras.main.flash(80, 255, 200, 0);
    if (this.enemies.countActive() === 0) this.nextWave();
  }
  playerHit(player, enemy) {
    enemy.destroy(); this.lives--;
    this.livesText.setText('Lives: ' + this.lives);
    this.cameras.main.shake(200, 0.015);
    if (this.lives <= 0) this.scene.start('GameOver', { score: this.score });
  }
  nextWave() {
    this.wave++;
    this.waveText.setText('Wave: ' + this.wave);
    this.spawnTimer.delay = Math.max(400, 1200 - this.wave * 80);
  }
}

class GameOverScene extends Phaser.Scene {
  constructor() { super({ key: 'GameOver' }); }
  create(data) {
    this.add.text(400, 220, 'GAME OVER', { fontSize: '56px', color: '#ff4444', fontStyle: 'bold' }).setOrigin(0.5);
    this.add.text(400, 310, 'Score: ' + (data?.score || 0), { fontSize: '32px', color: '#ffffff' }).setOrigin(0.5);
    const btn = this.add.text(400, 410, '[ PLAY AGAIN ]', { fontSize: '28px', color: '#00e676', backgroundColor: '#1a1a2e', padding: { x: 24, y: 12 } })
      .setOrigin(0.5).setInteractive({ useHandCursor: true });
    btn.on('pointerover', () => btn.setColor('#ffffff'));
    btn.on('pointerout',  () => btn.setColor('#00e676'));
    btn.on('pointerdown', () => this.scene.start('Game'));
  }
}

const config = {
  type: Phaser.AUTO, width: 800, height: 600,
  parent: 'game-container', backgroundColor: '#0a0a0f',
  physics: { default: 'arcade', arcade: { gravity: { y: 0 }, debug: false } },
  scene: [BootScene, GameScene, GameOverScene]
};
new Phaser.Game(config);`.trim();

      return `${ctx.role}. PHASE 2 of 2 — Build the Phaser 3 game for: "${brief}"

The HTML shell and CSS are already written. Your ONLY job: write app.js based on the working scaffold below.

${memoryCtx}${backendNote}
WORKING SCAFFOLD — this already runs. Customize it to match "${brief}":
${phaserScaffold}

YOUR JOB — modify the scaffold above to match the brief:
1. BootScene.preload(): re-draw textures to fit the game's theme (colors, shapes, sizes)
2. GameScene: adapt player movement, shooting/attack, enemy behavior and AI per the brief
3. Tune spawn rate, speeds, and difficulty scaling to feel right for this genre
4. Add extra scenes or mechanics the brief calls for (boss, power-ups, platformer physics, etc.)
5. Keep all existing infrastructure: arcade physics, collider wiring, HUD text, GameOver flow

WHAT MAKES A GREAT GAME:
✅ All textures generated programmatically in BootScene.preload() — zero external files
✅ Player movement via keyboard arrows/WASD (or touch for mobile)
✅ Shooting / attack mechanic (space, click, or theme-appropriate input)
✅ At least 2 enemy types with distinct movement patterns
✅ Physics overlap/collider for all interactions (bullets↔enemies, player↔enemies)
✅ Score + lives/health tracked and displayed as HUD text via setScrollFactor(0)
✅ Boot → Game → GameOver scenes with restart
✅ Wave/difficulty progression
✅ FULLY PLAYABLE from first load — zero stubs, zero TODOs

${getSmartLibraryHints()}
⚠️ Output ONLY app.js. No data.js. No import/export. Phaser is global via CDN.
SELF-CHECK: (1) All 3 scene classes extend Phaser.Scene. (2) preload() generates all textures. (3) create() wires all colliders and input. (4) update() runs game logic every frame. (5) GameOver has restart button. (6) new Phaser.Game(config) at bottom.

TYPE: work
FILENAME: public/app.js
TASK: complete Phaser 3 game — BootScene + GameScene + GameOverScene
---
[Write the COMPLETE app.js — customize the scaffold above for "${brief}". Every feature above implemented. Fully playable from first load.]

No text before TYPE: or after last block.`;
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
${isVue ? `FRAMEWORK: Vue 3. Use this.propertyName inside methods/mounted. No getElementById — Vue handles all DOM reactively.\n` : ''}
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

    // Extract existing HTML element IDs so builder targets correct selectors
    const existingHtmlIds = [...html.matchAll(/\bid=["']([^"']+)["']/gi)].map(m => m[1]).slice(0, 60);
    const htmlIdsNote = existingHtmlIds.length
      ? `\nEXISTING ELEMENT IDs IN index.html: ${existingHtmlIds.join(', ')}\n⚠️ Your JS must target THESE EXACT IDs for existing elements. New feature gets NEW IDs as defined in TECH SPEC.\n`
      : '';

    const featureName = featureSlug.replace(/-/g, '');

    // ── Vue 3 cycle 2+ — full app.js rewrite (createApp cannot be appended to) ──
    if (isVue) {
      return `${ctx.role}. Add ONE new feature to existing ${ctx.style}.

${planContext}

⚠️ VUE 3 REWRITE RULE: Vue's createApp({}) is a single declaration — it CANNOT be appended to.
Always use TYPE: work for app.js. Include ALL existing data/methods/computed PLUS the new feature.

CURRENT app.js (preserve ALL existing — add "${featurePriority}" on top of this):
${appJs ? summarizeJs(appJs, 6000) : '(none yet — write the full Vue app from scratch)'}

${featuresCtx ? `FEATURES ALREADY BUILT (preserve ALL of these in your rewrite):\n${featuresCtx}\n` : ''}
For "${featurePriority}" add:
1. New data properties → add to data() return (keep ALL existing keys)
2. New methods → add to methods{} (keep ALL existing methods)
3. New computed → add to computed{} if needed
4. New mounted() init → add setInterval/fetch calls (keep existing simulations running)
5. New HTML section → output as TYPE: work for index.html (server injects before <!-- END APP --> inside #app)

⚠️ NO getElementById anywhere. Use this.x inside methods/mounted to access Vue data.
⚠️ No import/export, no TypeScript annotations.
SELF-CHECK: (1) ALL existing methods from FEATURES list are still in methods{}. (2) ALL existing data keys still in data(). (3) mounted() still starts all previous simulations. (4) Zero getElementById.

TYPE: work
FILENAME: public/style.css
TASK: ${featureSlug} styles — append new rules only
---
[New CSS rules ONLY for ${featureSlug}. Use EXISTING CSS variables (--bg, --surface, --accent, --text, --border). Do NOT redefine :root or override existing selectors.]

===FILE===
TYPE: work
FILENAME: public/app.js
TASK: complete Vue 3 app with ${featureSlug} integrated
---
[COMPLETE app.js — ALL existing data/computed/methods/mounted PLUS new ${featureName} feature added.
const { createApp } = Vue; createApp({ data(){return{...}}, computed:{...}, methods:{...}, mounted(){...} }).mount('#app');
ZERO getElementById. Every existing method preserved. Every existing simulation still running.]

===FILE===
TYPE: work
FILENAME: public/index.html
TASK: new ${featureSlug} section — server injects inside #app div
---
[New HTML section ONLY using Vue template syntax ({{ }}, @click, v-for, v-if).
Server injects this before <!-- END APP --> inside <div id="app">. Do NOT output the full page.]

No text before first TYPE: or after last block.`;
    }

    // ── Vanilla cycle 2+ (tech-startup) — full data.js + app.js rewrite with new feature ──
    if (!isVue && category !== 'game-studio') {
      const buildPlan = readFile('docs/build-plan.md');
      return `${ctx.role}. Add ONE new feature to existing ${ctx.style}.

${planContext}${htmlIdsNote}
⚠️ VANILLA REWRITE RULE: data.js and app.js share global state — always rewrite both completely.
Include ALL existing functionality PLUS the new feature.

BUILD PLAN (reference for existing state shape and IDs):
${buildPlan ? buildPlan.slice(0, 1500) : '(no plan — derive from existing HTML IDs listed above)'}

CURRENT data.js (preserve ALL existing state and simulations):
${dataJs ? summarizeJs(dataJs, 3000) : '(none yet — write from scratch)'}

CURRENT app.js (preserve ALL existing render and event logic):
${appJs ? summarizeJs(appJs, 3000) : '(none yet — write from scratch)'}

${featuresCtx ? `FEATURES ALREADY BUILT (preserve ALL of these):\n${featuresCtx}\n` : ''}
For "${featurePriority}" add:
1. New state fields in data.js const state = {} (keep ALL existing fields)
2. New simulation/update functions in data.js (keep ALL existing intervals)
3. New render functions in app.js (keep ALL existing render logic)
4. New event handlers in app.js (keep ALL existing event handlers)
5. New HTML section in index.html if needed (output as ===FILE=== block)
6. New CSS rules in style.css (new rules only — keep existing vars and selectors)

SELF-CHECK: (1) Every existing state key still in state. (2) All existing setIntervals still running. (3) DOMContentLoaded still wraps all DOM code in app.js. (4) Every getElementById target exists in current or new HTML. (5) No variable declared twice.

TYPE: work
FILENAME: public/style.css
TASK: ${featureSlug} styles — new rules only
---
[New CSS for ${featureSlug} only. Use EXISTING --variables. Do NOT redefine :root or override existing selectors.]

===FILE===
TYPE: work
FILENAME: public/data.js
TASK: complete data.js — all existing state + ${featureSlug} additions
---
[COMPLETE data.js — ALL existing state fields and simulations preserved, plus new ${featureName} state and simulation. No stubs. initSimulations() at bottom.]

===FILE===
TYPE: work
FILENAME: public/app.js
TASK: complete app.js — all existing logic + ${featureSlug} integrated
---
[COMPLETE app.js — ALL existing render functions and event handlers preserved, plus new ${featureName} render and events. DOMContentLoaded wrapper. No stubs.]

No text before first TYPE: or after last block.`;
    }

    // ── Phaser 3 cycle 2+ (game-studio) — full app.js rewrite adding the new mechanic ──
    return `${ctx.role}. Add ONE new mechanic to existing ${ctx.style}.

${planContext}

⚠️ PHASER 3 REWRITE RULE: Phaser game config and scenes are a single block — always TYPE: work for app.js.
Include ALL existing scenes + new mechanic integrated. Keep all existing gameplay working.

CURRENT app.js (preserve ALL existing scenes — add "${featurePriority}" on top):
${appJs ? summarizeJs(appJs, 6000) : '(none yet — write the complete Phaser 3 game from scratch)'}

${featuresCtx ? `FEATURES ALREADY BUILT (preserve ALL):\n${featuresCtx}\n` : ''}
For "${featurePriority}" extend the existing Phaser 3 game:
1. New data in GameScene (properties on this) — or new Scene if warranted
2. New game objects in create() — sprites, groups, timers
3. New update() logic — movement, AI, collision handlers
4. New assets in BootScene.preload() — generate textures programmatically
5. CSS/HTML changes if a new UI element is needed (HUD, panel, button)

⚠️ No import/export. No TypeScript annotations. Phaser is a global via CDN.
SELF-CHECK: (1) All existing scenes preserved. (2) BootScene generates all textures. (3) Colliders still wired. (4) new Phaser.Game(config) still at bottom.

TYPE: work
FILENAME: public/style.css
TASK: ${featureSlug} styles
---
[New CSS for any HTML elements added this cycle. Match existing dark game theme.]

===FILE===
TYPE: work
FILENAME: public/app.js
TASK: Phaser 3 game with ${featureSlug} added
---
[COMPLETE app.js — ALL existing Phaser scenes + new ${featureName} mechanic integrated. Fully playable.]

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
    'backend-eng': `You are Backend Engineer. Project: "${brief}". Cycle ${cycle}.

TECH SPEC (the frontend will call these data shapes — your API MUST match):
${techSpec ? techSpec.slice(0, 800) : featurePriority || 'Build a REST API for this app.'}

Features to expose as API: ${featuresCtx || featurePriority}

Write a complete Node.js HTTP backend using ONLY built-in modules (http, fs, path, url).
NO external dependencies — no express, no cors packages. Pure Node.js built-ins only.

Requirements:
1. CORS headers on every response: Access-Control-Allow-Origin: *
2. Content-Type: application/json on all responses
3. Handle OPTIONS preflight requests (return 204)
4. JSON file database: read/write a local db.json file for persistence
5. Include seed data so the app works immediately on first run
6. Endpoint naming: use the EXACT paths the frontend will call based on the tech spec above
   e.g. if tech spec says "fetch prices from /api/prices" → expose GET /api/prices
7. Response shape: match the data structure described in the tech spec exactly
   e.g. if state.prices = { BTC: 45000 } → GET /api/prices returns { "BTC": 45000 }
8. Comprehensive CRUD endpoints tailored to the project brief
9. Server listens on process.env.PORT || 3001

Helper pattern to use:
  const DB = path.join(__dirname, 'db.json');
  function readDB() { try { return JSON.parse(fs.readFileSync(DB,'utf8')); } catch { return {/* seed */}; } }
  function writeDB(d) { fs.writeFileSync(DB, JSON.stringify(d,null,2)); }

${workFmt('api/server.js', 'Node.js REST API backend')}`,
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
