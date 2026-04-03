/* ══════════════════════════════════════════════
   WAR ROOM — AGENT PROMPTS
   Category-aware prompt builder for Phase 4 live pipeline.
   buildPrompt(agentId, live) → string
   ══════════════════════════════════════════════ */

const fs   = require('fs');
const path = require('path');

function buildPrompt(agentId, live) {
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
  const html            = readFile('public/index.html');
  const css             = readFile('public/style.css');
  const appJs           = readFile('public/app.js');
  const lastQA          = cycle > 1 ? readFile(`docs/qa-cycle${cycle - 1}.md`) : '';
  const htmlLines = html  ? html.split('\n').length  : 0;
  const cssLines  = css   ? css.split('\n').length   : 0;
  const jsLines   = appJs ? appJs.split('\n').length : 0;

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

  // Detect fix mode: CEO ordered a FIX last cycle
  const isFix = featurePriority.trim().startsWith('FIX:');

  // JS snapshot for fix mode — give builder the real current code to work from
  const jsSnapshot = appJs ? appJs.slice(0, 3000) : '';

  /* ── CEO / Director prompts per category ── */
  const CEO_PROMPTS = {
    'tech-startup': `You are PM. Project: "${brief}". Cycle ${cycle}.
Built: ${sectionList}
Done: ${donePriorities}
QA last cycle: ${lastQA ? lastQA.slice(0, 300) : 'N/A'}
JS size: ${jsLines} lines

DECISION RULES (follow in order):
1. If QA flagged broken logic, missing functionality, or non-working features → output FIX: <specific description of what code to fix>
2. If JS is < 50 lines and cycle > 1 → output FIX: complete all interactivity and logic for existing UI
3. Otherwise → add ONE new feature:
   - NEW PAGE: /name.html — description (distinct URL destination)
   - SECTION: description (scrollable component)
   Pages so far: ${existingHtmlPages.length}. Prefer new page if index.html has 5+ sections.

Output exactly ONE line: FIX: ... OR NEW PAGE: ... OR SECTION: ...
${workFmt('docs/feature-priority.md', 'Feature decision for cycle ' + cycle)}`,

    'game-studio': `You are Game Director. Game: "${brief}". Cycle ${cycle}.
Built: ${sectionList}
Done: ${donePriorities}
QA last cycle: ${lastQA ? lastQA.slice(0, 300) : 'N/A'}
JS size: ${jsLines} lines

DECISION RULES (follow in order):
1. Cycle 1 → always: SECTION: complete game with loop, input, collision, score, start/play/gameover states
2. If QA flagged game-breaking bugs, missing collision, broken input, or game loop not running → FIX: <specific fix>
3. If JS < 100 lines → FIX: implement complete game loop with requestAnimationFrame, input handling, collision detection, and score display
4. Otherwise → add ONE mechanic:
   - NEW PAGE: /name.html — description (separate game screen)
   - SECTION: description (new mechanic added to game canvas)

Output exactly ONE line: FIX: ... OR NEW PAGE: ... OR SECTION: ...
${workFmt('docs/feature-priority.md', 'Game feature for cycle ' + cycle)}`,

    'film-production': `You are Film Director. Project: "${brief}". Cycle ${cycle}.
Built: ${sectionList}
Done: ${donePriorities}

Pick ONE page or section to add to the film website. Routing rule:
- NEW PAGE if it's a distinct section (/cast.html, /gallery.html, /screenplay.html, /awards.html)
- SECTION if it's added to the main page (trailer embed, synopsis block, review quotes, crew credits)
Output: "NEW PAGE: /name.html — description" OR "SECTION: description".
${workFmt('docs/feature-priority.md', 'Film feature for cycle ' + cycle)}`,

    'ad-agency': `You are Creative Director. Campaign: "${brief}". Cycle ${cycle}.
Built: ${sectionList}
Done: ${donePriorities}

Pick ONE campaign section or page to add. Routing rule:
- NEW PAGE if it's a distinct landing page (/case-study.html, /results.html, /contact.html)
- SECTION if it's added to the main campaign page (testimonials, stats, CTA block, social proof, video)
Output: "NEW PAGE: /name.html — description" OR "SECTION: description".
${workFmt('docs/feature-priority.md', 'Campaign feature for cycle ' + cycle)}`,

    'newsroom': `You are Editor-in-Chief. Story: "${brief}". Cycle ${cycle}.
Built: ${sectionList}
Done: ${donePriorities}

Pick ONE article section or page to build next. Routing rule:
- NEW PAGE if it's a distinct story page (/data-analysis.html, /related-stories.html, /sources.html)
- SECTION if it's added to the main article (pull quote, data visualization, photo gallery, sidebar, timeline)
Output: "NEW PAGE: /name.html — description" OR "SECTION: description".
${workFmt('docs/feature-priority.md', 'Article feature for cycle ' + cycle)}`,

    'consulting': `You are Managing Director. Engagement: "${brief}". Cycle ${cycle}.
Built: ${sectionList}
Done: ${donePriorities}

Pick ONE deliverable section or page to build next. Routing rule:
- NEW PAGE if it's a distinct report section (/analysis.html, /recommendations.html, /appendix.html)
- SECTION if it's added to the main report page (executive summary, chart, matrix, timeline, table)
Output: "NEW PAGE: /name.html — description" OR "SECTION: description".
${workFmt('docs/feature-priority.md', 'Deliverable for cycle ' + cycle)}`,
  };

  /* ── Lead Engineer prompts per category ── */
  const LEAD_ENG_PROMPTS = {
    'game-studio': `You are Game Systems Engineer. Cycle ${cycle}.
Task: ${featurePriority || 'Build the game from scratch.'}
Pages: ${existingHtmlPages.join(', ') || 'none'} | Size: ${htmlLines}L HTML, ${cssLines}L CSS, ${jsLines}L JS
${isFix ? `Current app.js (first 800 chars):\n${jsSnapshot.slice(0, 800)}` : ''}

${isFix
  ? `Write a FIX spec (≤120 words): identify the broken code, exact functions to rewrite, correct game loop structure (requestAnimationFrame, update(), draw()), input event handling, collision algorithm, state machine (START/PLAYING/GAMEOVER). Be specific about what's wrong and how to fix it.`
  : `Write game mechanics spec (≤100 words): target file, canvas element IDs, game object structures, JS functions needed, collision logic.`}
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
    'game-studio': `You are Visual Artist. Cycle ${cycle}.
Feature: ${featurePriority || 'Design the game.'}
Spec: ${techSpec ? techSpec.slice(0, 150) : ''}

Write art direction spec (≤80 words): color palette, canvas background, sprite colors, UI style, animation feel.
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

    const planContext = `PROJECT: ${brief}
FEATURE: ${featurePriority || 'Build from scratch.'}
TECH: ${(techSpec || 'Semantic HTML5, modern CSS, vanilla JS.').slice(0, isFix ? 600 : 300)}
DESIGN: ${(designSpec || ctx.palette).slice(0, isFix ? 400 : 200)}`;

    if (isFirstBuild) {
      const gameExtra = category === 'game-studio' ? `
GAME REQUIREMENTS — all must be present in cycle 1:
- requestAnimationFrame game loop with update() and draw() functions
- Input handling: keyboard (ArrowKeys/WASD/Space) AND mouse/touch click
- At least 2 entity types (player + enemy or obstacle)
- Collision detection that runs every frame
- Score counter displayed on canvas
- 3 game states: START SCREEN → PLAYING → GAME OVER (with restart)
- The game must be FULLY PLAYABLE. Do not leave stubs or TODOs.` : '';

      return `${ctx.role}. Build from scratch: ${ctx.style}.

${planContext}${gameExtra}

Write one block per file, separated by ===FILE===. Min: style.css, index.html, app.js. All HTML must have <link href="style.css"> and <script src="app.js">. Keep each file ≤250 lines.

TYPE: work
FILENAME: public/style.css
TASK: shared stylesheet
---
[CSS]

===FILE===
TYPE: work
FILENAME: public/index.html
TASK: homepage
---
[HTML]

===FILE===
TYPE: work
FILENAME: public/app.js
TASK: shared JS
---
[JS]

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

      return `${ctx.role}. FIX broken logic in existing ${ctx.style}.

${planContext}
FIX TASK: ${featurePriority}

CURRENT app.js (FULL):
${appJs || '(empty — write it from scratch)'}

${referencedHtml ? `CURRENT ${referencedPage} (FULL — this is the page to fix JS for):\n${referencedHtml.slice(0, 1500)}` : `EXISTING HTML PAGES:\n${allPagesCtx || html.slice(-600)}`}

Instructions:
- Output the COMPLETE rewritten app.js with ALL required logic implemented (no stubs, no TODOs)
- If the FIX TASK references a specific HTML page, write JS that targets that page's real element IDs and classes
- If that HTML page doesn't exist yet, create it with a ===FILE=== block first, then write app.js
- Fix every issue described in the FIX TASK
- For game-studio: ensure game loop runs, input works, collision detects, score updates, game states transition correctly
- Only include style.css block if CSS also needs fixing

Write one block per file, separated by ===FILE===:

TYPE: work
FILENAME: public/app.js
TASK: fix ${featureSlug}
---
[COMPLETE working app.js — no placeholders]

Only output files that need changing. No text before first TYPE: or after last block.`;
    }

    return `${ctx.role}. Add feature to existing ${ctx.style}.

${planContext}

Pages: ${existingPages}
HTML tail: ${html.slice(-200)}

Rules: style.css/app.js → new code only (server appends). Existing HTML → new section only (server injects before </body>). New page → full document with <link href="style.css"> + <script src="app.js">.

TYPE: work
FILENAME: public/style.css
TASK: ${featureSlug} CSS
---
[new CSS]

===FILE===
TYPE: work
FILENAME: [target file]
TASK: [description]
---
[content]

Only files that change. No text before TYPE: or after last block.`;
  })();

  const customerFeedback = live.customerFeedback ? live.customerFeedback.trim() : '';
  const customerNote = customerFeedback
    ? `🚨 CUSTOMER FEEDBACK — MANDATORY THIS CYCLE: "${customerFeedback}"\nYou MUST output a decision that directly addresses this feedback. Do not add unrelated features.\n\n`
    : '';
  const customerCtx = customerFeedback
    ? `\n🚨 CUSTOMER FEEDBACK TO ADDRESS THIS CYCLE: "${customerFeedback}"\n`
    : '';

  /* ── Assemble final map ── */
  const screenshotNote = live.previewScreenshot
    ? 'A screenshot of the current website is attached — use it to visually assess what is working or broken before making your decision.\n\n'
    : '';
  const map = {
    ceo:        screenshotNote + customerNote + (CEO_PROMPTS[category] || CEO_PROMPTS['tech-startup']),
    'lead-eng': LEAD_ENG_PROMPTS[category] || `You are Lead Engineer. Cycle ${cycle}.
Task: ${featurePriority || 'Build the full website from scratch.'}${customerCtx}
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
