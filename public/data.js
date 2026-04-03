/* ══════════════════════════════════════════════
   WAR ROOM — STATIC DATA
   Constants: portraits, categories, agent rosters, meta.
   ══════════════════════════════════════════════ */

const TOTAL_BUDGET = 1_000_000;

/* ─── SVG PORTRAITS ─── */
const PORTRAITS = {
  pm:`<svg viewBox="0 0 80 96" xmlns="http://www.w3.org/2000/svg"><path d="M5,96 L5,72 Q18,62 28,60 L35,76 h10 l7,-16 Q52,62 75,72 L75,96Z" fill="#1e3a5f"/><rect x="33" y="60" width="14" height="36" fill="#e8ecf4"/><polygon points="40,63 37,72 40,96 43,72" fill="#00e676"/><path d="M28,60 L35,76 L33,60Z" fill="#162d4a"/><path d="M52,60 L45,76 L47,60Z" fill="#162d4a"/><rect x="34" y="55" width="12" height="9" fill="#f5c18a"/><ellipse cx="40" cy="38" rx="25" ry="27" fill="#f5c18a"/><path d="M15,34 Q16,10 40,9 Q64,10 65,34 Q59,19 40,20 Q21,20 15,34Z" fill="#1e0e08"/><ellipse cx="14" cy="40" rx="4" ry="6" fill="#e0a870"/><ellipse cx="66" cy="40" rx="4" ry="6" fill="#e0a870"/><ellipse cx="30" cy="37" rx="5.5" ry="5.5" fill="white"/><circle cx="31" cy="38" r="3.5" fill="#1a2040"/><circle cx="32" cy="37" r="1.2" fill="white"/><ellipse cx="50" cy="37" rx="5.5" ry="5.5" fill="white"/><circle cx="51" cy="38" r="3.5" fill="#1a2040"/><circle cx="52" cy="37" r="1.2" fill="white"/><path d="M24,29 Q30,26 36,29" stroke="#1e0e08" stroke-width="2.5" fill="none" stroke-linecap="round"/><path d="M44,29 Q50,26 56,29" stroke="#1e0e08" stroke-width="2.5" fill="none" stroke-linecap="round"/><path d="M38,44 Q40,47 42,44" stroke="#c07850" stroke-width="1.5" fill="none" stroke-linecap="round"/><path d="M29,51 Q40,61 51,51" stroke="#b06840" stroke-width="2" fill="none" stroke-linecap="round"/></svg>`,

  cto:`<svg viewBox="0 0 80 96" xmlns="http://www.w3.org/2000/svg"><path d="M5,96 L5,72 Q14,60 28,58 L33,68 Q40,74 47,68 L52,58 Q66,60 75,72 L75,96Z" fill="#2d333f"/><rect x="28" y="76" width="24" height="20" rx="3" fill="#232830"/><rect x="34" y="55" width="12" height="8" fill="#f0bb84"/><ellipse cx="40" cy="37" rx="25" ry="27" fill="#f0bb84"/><path d="M15,33 Q14,8 40,7 Q66,8 65,33 Q62,17 55,14 Q48,8 40,9 Q32,8 25,14 Q18,17 15,33Z" fill="#18182e"/><path d="M24,10 Q19,4 15,11" stroke="#18182e" stroke-width="3.5" fill="none" stroke-linecap="round"/><path d="M56,10 Q61,4 65,11" stroke="#18182e" stroke-width="3.5" fill="none" stroke-linecap="round"/><ellipse cx="14" cy="40" rx="4" ry="6" fill="#e0a870"/><ellipse cx="66" cy="40" rx="4" ry="6" fill="#e0a870"/><rect x="21" y="31" width="16" height="12" rx="3" fill="none" stroke="#3a3a5a" stroke-width="2.5"/><rect x="43" y="31" width="16" height="12" rx="3" fill="none" stroke="#3a3a5a" stroke-width="2.5"/><line x1="37" y1="37" x2="43" y2="37" stroke="#3a3a5a" stroke-width="2.5"/><ellipse cx="29" cy="37" rx="4" ry="4" fill="white"/><circle cx="30" cy="38" r="2.5" fill="#1a1a30"/><circle cx="31" cy="37" r="0.9" fill="white"/><ellipse cx="51" cy="37" rx="4" ry="4" fill="white"/><circle cx="52" cy="38" r="2.5" fill="#1a1a30"/><circle cx="53" cy="37" r="0.9" fill="white"/><path d="M22,27 Q28,24 35,27" stroke="#18182e" stroke-width="2" fill="none" stroke-linecap="round"/><path d="M45,27 Q52,24 58,27" stroke="#18182e" stroke-width="2" fill="none" stroke-linecap="round"/><path d="M29,52 Q37,57 51,50" stroke="#b06840" stroke-width="2" fill="none" stroke-linecap="round"/></svg>`,

  'lead-eng':`<svg viewBox="0 0 80 96" xmlns="http://www.w3.org/2000/svg"><path d="M5,96 L5,72 Q16,62 28,60 L35,76 h10 l7,-16 Q64,62 75,72 L75,96Z" fill="#2d4a6a"/><path d="M5,80 L75,80" stroke="#3a6080" stroke-width="2" opacity="0.4"/><rect x="56" y="72" width="16" height="18" rx="2" fill="#5c2a1a"/><rect x="56" y="72" width="16" height="6" rx="1" fill="#7a4a2a"/><path d="M72,79 Q78,79 78,85 Q78,90 72,90" stroke="#5c2a1a" stroke-width="2.5" fill="none"/><rect x="34" y="55" width="12" height="9" fill="#f0bb84"/><ellipse cx="40" cy="38" rx="25" ry="27" fill="#f0bb84"/><path d="M15,34 Q16,10 40,9 Q64,10 65,34 Q59,19 40,20 Q21,20 15,34Z" fill="#5c3010"/><ellipse cx="14" cy="40" rx="4" ry="6" fill="#e0a870"/><ellipse cx="66" cy="40" rx="4" ry="6" fill="#e0a870"/><path d="M15,50 Q15,64 20,66 Q30,72 40,72 Q50,72 60,66 Q65,64 65,50 Q55,60 40,60 Q25,60 15,50Z" fill="#7a4020"/><path d="M26,50 Q32,47 40,50 Q48,47 54,50 Q50,55 40,54 Q30,55 26,50Z" fill="#7a4020"/><ellipse cx="30" cy="36" rx="5.5" ry="5" fill="white"/><circle cx="31" cy="37" r="3.2" fill="#1a2a1a"/><circle cx="32" cy="36" r="1.1" fill="white"/><ellipse cx="50" cy="36" rx="5.5" ry="5" fill="white"/><circle cx="51" cy="37" r="3.2" fill="#1a2a1a"/><circle cx="52" cy="36" r="1.1" fill="white"/><path d="M23,27 Q30,25 36,28" stroke="#5c3010" stroke-width="2.5" fill="none" stroke-linecap="round"/><path d="M44,28 Q50,25 57,27" stroke="#5c3010" stroke-width="2.5" fill="none" stroke-linecap="round"/></svg>`,

  designer:`<svg viewBox="0 0 80 96" xmlns="http://www.w3.org/2000/svg"><path d="M5,96 L5,72 Q14,62 28,60 L32,70 Q36,78 40,78 Q44,78 48,70 L52,60 Q66,62 75,72 L75,96Z" fill="#6d28d9"/><rect x="34" y="55" width="12" height="9" fill="#f5c18a"/><ellipse cx="40" cy="37" rx="25" ry="27" fill="#f5c18a"/><path d="M15,34 Q14,8 40,7 Q66,8 65,34 Q60,17 52,14 Q46,9 40,9 Q34,9 28,14 Q20,17 15,34Z" fill="#7c3aed"/><path d="M15,34 Q10,46 12,60 Q16,52 18,44 Z" fill="#7c3aed"/><path d="M65,34 Q70,46 68,60 Q64,52 62,44 Z" fill="#7c3aed"/><ellipse cx="13" cy="40" rx="4" ry="6" fill="#e0a870"/><ellipse cx="67" cy="40" rx="4" ry="6" fill="#e0a870"/><circle cx="13" cy="46" r="3.5" fill="#e879f9"/><ellipse cx="29" cy="37" rx="7" ry="7" fill="white"/><circle cx="30" cy="38" r="4.5" fill="#6d28d9"/><circle cx="29" cy="35" r="2" fill="#1a0040"/><circle cx="31" cy="36" r="1.1" fill="white"/><ellipse cx="51" cy="37" rx="7" ry="7" fill="white"/><circle cx="52" cy="38" r="4.5" fill="#6d28d9"/><circle cx="51" cy="35" r="2" fill="#1a0040"/><circle cx="53" cy="36" r="1.1" fill="white"/><path d="M22,27 Q29,23 36,26" stroke="#4c1d95" stroke-width="2" fill="none" stroke-linecap="round"/><path d="M44,26 Q51,23 58,27" stroke="#4c1d95" stroke-width="2" fill="none" stroke-linecap="round"/><path d="M27,51 Q40,63 53,51" stroke="#b06840" stroke-width="2.2" fill="none" stroke-linecap="round"/></svg>`,

  'junior-dev':`<svg viewBox="0 0 80 96" xmlns="http://www.w3.org/2000/svg"><path d="M5,96 L5,72 Q14,60 28,58 L33,68 Q40,74 47,68 L52,58 Q66,60 75,72 L75,96Z" fill="#b45309"/><rect x="34" y="54" width="12" height="9" fill="#f5c18a"/><ellipse cx="40" cy="37" rx="25" ry="27" fill="#f5c18a"/><path d="M15,33 Q15,8 40,7 Q65,8 65,33 Q62,17 55,14 Q48,8 40,9 Q32,8 25,14 Q18,17 15,33Z" fill="#c47a10"/><path d="M24,10 Q20,4 16,9" stroke="#c47a10" stroke-width="3" fill="none" stroke-linecap="round"/><path d="M56,10 Q60,4 64,9" stroke="#c47a10" stroke-width="3" fill="none" stroke-linecap="round"/><ellipse cx="14" cy="40" rx="4" ry="6" fill="#e0a870"/><ellipse cx="66" cy="40" rx="4" ry="6" fill="#e0a870"/><ellipse cx="29" cy="37" rx="7.5" ry="8" fill="white"/><circle cx="30" cy="38" r="5.2" fill="#3b5998"/><circle cx="28" cy="35" r="2.3" fill="#1a2040"/><circle cx="30" cy="36" r="1.2" fill="white"/><ellipse cx="51" cy="37" rx="7.5" ry="8" fill="white"/><circle cx="52" cy="38" r="5.2" fill="#3b5998"/><circle cx="50" cy="35" r="2.3" fill="#1a2040"/><circle cx="52" cy="36" r="1.2" fill="white"/><path d="M21,27 Q28,22 35,26" stroke="#a06010" stroke-width="2" fill="none" stroke-linecap="round"/><path d="M45,26 Q52,22 59,27" stroke="#a06010" stroke-width="2" fill="none" stroke-linecap="round"/><path d="M31,52 Q40,59 49,52" stroke="#b06840" stroke-width="2" fill="none" stroke-linecap="round"/><ellipse cx="63" cy="27" rx="3.5" ry="4.5" fill="#93d4f5" opacity="0.85"/></svg>`,

  sales:`<svg viewBox="0 0 80 96" xmlns="http://www.w3.org/2000/svg"><path d="M5,96 L5,72 Q16,62 28,60 L35,76 h10 l7,-16 Q64,62 75,72 L75,96Z" fill="#831843"/><rect x="33" y="60" width="14" height="36" fill="#fdf2f8"/><polygon points="40,63 37,72 40,96 43,72" fill="#1e1b4b"/><path d="M22,66 L30,62 L28,71Z" fill="#f9a8d4"/><rect x="34" y="55" width="12" height="9" fill="#c88050"/><ellipse cx="40" cy="38" rx="25" ry="27" fill="#c88050"/><path d="M15,34 Q16,9 40,8 Q64,9 65,34 Q60,17 40,18 Q20,17 15,34Z" fill="#0c0a05"/><ellipse cx="14" cy="40" rx="4" ry="6" fill="#b07040"/><ellipse cx="66" cy="40" rx="4" ry="6" fill="#b07040"/><ellipse cx="30" cy="37" rx="5.5" ry="5" fill="white"/><circle cx="31" cy="38" r="3.2" fill="#1a0808"/><circle cx="32" cy="37" r="1.2" fill="white"/><ellipse cx="50" cy="37" rx="5.5" ry="5" fill="white"/><circle cx="51" cy="38" r="3.2" fill="#1a0808"/><circle cx="52" cy="37" r="1.2" fill="white"/><path d="M26,50 Q40,64 54,50" fill="#1a0808"/><path d="M27,51 Q40,59 53,51" fill="white"/><path d="M26,50 Q40,64 54,50" stroke="#1a0808" stroke-width="1.5" fill="none"/></svg>`,

  qa:`<svg viewBox="0 0 80 96" xmlns="http://www.w3.org/2000/svg"><path d="M5,96 L5,72 Q16,62 28,60 L35,76 h10 l7,-16 Q64,62 75,72 L75,96Z" fill="#0f6b63"/><rect x="33" y="60" width="14" height="36" fill="#e0f4f2"/><rect x="34" y="55" width="12" height="9" fill="#f5c18a"/><ellipse cx="40" cy="38" rx="25" ry="27" fill="#f5c18a"/><path d="M15,34 Q16,10 40,9 Q64,10 65,34 Q59,19 40,20 Q21,20 15,34Z" fill="#4a2c10"/><ellipse cx="14" cy="40" rx="4" ry="6" fill="#e0a870"/><ellipse cx="66" cy="40" rx="4" ry="6" fill="#e0a870"/><circle cx="30" cy="37" r="8.5" fill="none" stroke="#2a2a3a" stroke-width="2.5"/><circle cx="50" cy="37" r="8.5" fill="none" stroke="#2a2a3a" stroke-width="2.5"/><line x1="38.5" y1="37" x2="41.5" y2="37" stroke="#2a2a3a" stroke-width="2.5"/><ellipse cx="30" cy="37" rx="5" ry="5" fill="white"/><circle cx="31" cy="38" r="3" fill="#1a2a1a"/><circle cx="32" cy="37" r="1.1" fill="white"/><ellipse cx="50" cy="37" rx="5" ry="5" fill="white"/><circle cx="51" cy="38" r="3" fill="#1a2a1a"/><circle cx="52" cy="37" r="1.1" fill="white"/><path d="M22,28 Q29,26 36,29" stroke="#4a2c10" stroke-width="2.5" fill="none" stroke-linecap="round"/><path d="M44,25 Q51,22 58,26" stroke="#4a2c10" stroke-width="2.5" fill="none" stroke-linecap="round"/><path d="M30,52 Q37,56 50,50" stroke="#a06040" stroke-width="2" fill="none" stroke-linecap="round"/></svg>`,

  legal:`<svg viewBox="0 0 80 96" xmlns="http://www.w3.org/2000/svg"><path d="M5,96 L5,72 Q16,62 28,60 L35,76 h10 l7,-16 Q64,62 75,72 L75,96Z" fill="#18182e"/><rect x="33" y="60" width="14" height="36" fill="#e8ecf4"/><polygon points="40,63 37,72 40,96 43,72" fill="#2d2d4e"/><rect x="34" y="55" width="12" height="9" fill="#e8c090"/><ellipse cx="40" cy="38" rx="25" ry="27" fill="#e8c090"/><path d="M15,34 Q16,9 40,8 Q64,9 65,34 Q59,18 52,16 Q46,11 40,11 Q34,11 28,16 Q21,18 15,34Z" fill="#7a7a90"/><ellipse cx="14" cy="41" rx="4" ry="6" fill="#d0a070"/><ellipse cx="66" cy="41" rx="4" ry="6" fill="#d0a070"/><path d="M24,43 Q30,39 36,43" fill="none" stroke="#2a2a4a" stroke-width="2.5"/><path d="M44,43 Q50,39 56,43" fill="none" stroke="#2a2a4a" stroke-width="2.5"/><line x1="36" y1="43" x2="44" y2="43" stroke="#2a2a4a" stroke-width="2.2"/><ellipse cx="30" cy="36" rx="5.5" ry="4.5" fill="white"/><circle cx="31" cy="37" r="3" fill="#1a1a2e"/><circle cx="32" cy="36" r="1" fill="white"/><ellipse cx="50" cy="36" rx="5.5" ry="4.5" fill="white"/><circle cx="51" cy="37" r="3" fill="#1a1a2e"/><circle cx="52" cy="36" r="1" fill="white"/><line x1="31" y1="52" x2="49" y2="52" stroke="#906040" stroke-width="2" stroke-linecap="round"/></svg>`,
};

/* ══════════════════════════════════════════════
   TEAM CATEGORIES
   ══════════════════════════════════════════════ */
const CATEGORIES = [
  { id:'tech-startup',    name:'TECH STARTUP',    icon:'⚡', tagline:'Ship a product end-to-end',      color:'#00e676', locked:false },
  { id:'game-studio',     name:'GAME STUDIO',     icon:'🎮', tagline:'Design & build a game',           color:'#c084fc', locked:false },
  { id:'film-production', name:'FILM PRODUCTION', icon:'🎬', tagline:'From script to screen',           color:'#fb923c', locked:false },
  { id:'ad-agency',       name:'AD AGENCY',       icon:'📣', tagline:'Campaign strategy & creative',   color:'#38bdf8', locked:false },
  { id:'newsroom',        name:'NEWSROOM',        icon:'📰', tagline:'Investigate, write, publish',    color:'#f87171', locked:false },
  { id:'consulting',      name:'CONSULTING',      icon:'📊', tagline:'Strategy, data & delivery',      color:'#fde047', locked:false },
];

/* ══════════════════════════════════════════════
   PLANNING AGENTS — per category (phases 1-3)
   ══════════════════════════════════════════════ */
const CATEGORY_AGENTS = {
  'tech-startup': [
    { id:'pm',         name:'Product Manager',  abbr:'PM',  role:'Vision & Requirements',  desc:'Transforms the brief into a structured PRD.',        tokens:80_000,  maxOutput:2048, color:'#00e676', bg:'rgba(0,230,118,0.12)',    system:`You are a seasoned Product Manager. Write a concise PRD. Include: Executive Summary, Problem Statement, Target Users, Core Features (MoSCoW), Success Metrics, Timeline.` },
    { id:'cto',        name:'CTO',              abbr:'CTO', role:'Technical Architecture', desc:'Designs system architecture, tech stack, and APIs.', tokens:200_000, maxOutput:8192, color:'#ff6b6b', bg:'rgba(255,107,107,0.12)', system:`You are a visionary CTO. Design the complete technical architecture. Include: tech stack (with rationale), system architecture, data models, API endpoints, infrastructure, security.` },
    { id:'lead-eng',   name:'Lead Engineer',    abbr:'LE',  role:'Implementation Roadmap', desc:'Breaks architecture into sprints and tasks.',         tokens:120_000, maxOutput:4096, color:'#4fc3f7', bg:'rgba(79,195,247,0.12)',  system:`You are a Lead Engineer. Create a detailed implementation plan: sprint breakdown, tasks, risks, Definition of Done, CI/CD workflow.` },
    { id:'designer',   name:'UI Designer',      abbr:'UID', role:'Design System',          desc:'Defines visual language, components, and flows.',    tokens:90_000,  maxOutput:3072, color:'#ce93d8', bg:'rgba(206,147,216,0.12)', system:`You are a senior UI/UX Designer. Write a design spec: philosophy, color palette, typography, component library, user flows, accessibility.` },
    { id:'junior-dev', name:'Junior Developer', abbr:'JD',  role:'Core Feature Code',      desc:'Writes actual code for the most critical feature.',  tokens:40_000,  maxOutput:2048, color:'#ffb74d', bg:'rgba(255,183,77,0.12)',  system:`You are a Junior Developer. Write complete, working code for the core feature using the CTO's recommended stack. Include inline comments.` },
    { id:'sales',      name:'Sales Lead',       abbr:'SL',  role:'Go-To-Market Strategy',  desc:'Builds GTM plan, pricing, and growth tactics.',      tokens:100_000, maxOutput:3072, color:'#f06292', bg:'rgba(240,98,146,0.12)',  system:`You are a Sales Lead. Create a complete GTM strategy: target segments, pricing, channels, marketing plan, launch sequence, 90-day targets.` },
    { id:'qa',         name:'QA Engineer',      abbr:'QA',  role:'Quality Assurance',      desc:'Test plan covering unit, E2E, and performance.',     tokens:35_000,  maxOutput:2048, color:'#80cbc4', bg:'rgba(128,203,196,0.12)', system:`You are a QA Engineer. Write a comprehensive test plan: test strategy, unit tests, integration tests, E2E journeys, edge cases, performance plan.` },
    { id:'legal',      name:'Legal Advisor',    abbr:'LEG', role:'Legal & Compliance',     desc:'Reviews risks, compliance, and IP considerations.',  tokens:180_000, maxOutput:6144, color:'#fff176', bg:'rgba(255,241,118,0.12)', system:`You are a Legal Advisor for tech startups. Provide a legal review: ToS requirements, privacy policy, GDPR/CCPA, IP considerations, compliance, risks.` },
  ],
  'game-studio': [
    { id:'gs-director',  name:'Game Director',    abbr:'GD',  role:'Creative Vision',     desc:'Sets the game concept, core loop, and progression.',  tokens:80_000,  maxOutput:2048, color:'#c084fc', bg:'rgba(192,132,252,0.12)', system:`You are a Game Director at an indie studio. Write a game design document. Include: core loop, mechanics, progression system, win/lose conditions, player experience goals, and inspiration references.` },
    { id:'gs-engineer',  name:'Systems Engineer', abbr:'SE',  role:'Game Mechanics',      desc:'Architects game physics, collisions, and systems.',   tokens:200_000, maxOutput:8192, color:'#a78bfa', bg:'rgba(167,139,250,0.12)', system:`You are a Game Systems Engineer. Design the technical game architecture: game loop structure, entity/component system, physics, collision detection, state machine, score/level data structures.` },
    { id:'gs-artist',    name:'Visual Artist',    abbr:'VA',  role:'Art & Aesthetic',     desc:'Defines art direction, palette, and visual language.', tokens:90_000,  maxOutput:3072, color:'#f0abfc', bg:'rgba(240,171,252,0.12)', system:`You are a Game Visual Artist. Write an art direction document: art style (pixel/vector/flat), color palette, sprite design principles, UI aesthetic, particle effects style, animation guidelines.` },
    { id:'gs-developer', name:'Game Developer',   abbr:'DEV', role:'Game Code',           desc:'Builds the game with HTML5 canvas and vanilla JS.',   tokens:40_000,  maxOutput:2048, color:'#fbbf24', bg:'rgba(251,191,36,0.12)',  system:`You are a Game Developer. Write complete, working HTML5 canvas game code in vanilla JavaScript. Implement real physics, input handling (keyboard/mouse/touch), score tracking, and game states (start/play/gameover).` },
    { id:'gs-qa',        name:'Playtester',       abbr:'PT',  role:'Balance & Bugs',      desc:'Tests game balance, difficulty, and reports bugs.',   tokens:35_000,  maxOutput:2048, color:'#34d399', bg:'rgba(52,211,153,0.12)',  system:`You are a Game Playtester. Write a playtesting report covering: difficulty curve assessment, fun factor rating, bugs and edge cases found, balance issues, and specific tuning recommendations.` },
  ],
  'film-production': [
    { id:'fp-director',  name:'Director',            abbr:'DIR', role:'Creative Vision',    desc:"Sets the film's tone, story, and creative direction.", tokens:80_000,  maxOutput:2048, color:'#fbbf24', bg:'rgba(251,191,36,0.12)',  system:`You are a Film Director. Write a director's vision document: creative concept, tone and mood, target audience, visual style references, emotional arc, and the central theme of the film.` },
    { id:'fp-writer',    name:'Screenwriter',         abbr:'SCR', role:'Script & Narrative', desc:'Writes the screenplay, structure, and dialogue.',     tokens:200_000, maxOutput:8192, color:'#f97316', bg:'rgba(249,115,22,0.12)',  system:`You are a Screenwriter. Write a detailed screenplay treatment: three-act structure, key scenes with descriptions, character arcs, notable dialogue excerpts, and key plot beats.` },
    { id:'fp-dop',       name:'Cinematographer',      abbr:'DOP', role:'Visual Language',    desc:'Designs shot language, lighting, and camera style.',  tokens:90_000,  maxOutput:3072, color:'#fb923c', bg:'rgba(251,146,60,0.12)',  system:`You are a Director of Photography. Write a visual language document: shot types, camera movement vocabulary, lighting design approach, color palette and grading intent, and mood references.` },
    { id:'fp-designer',  name:'Production Designer',  abbr:'PD',  role:'Sets & Aesthetics',  desc:'Designs the visual world — sets, costumes, props.',  tokens:90_000,  maxOutput:3072, color:'#e879f9', bg:'rgba(232,121,249,0.12)', system:`You are a Production Designer. Write a production design document: set design concepts, color and texture palette, costume direction, key props, and period/world aesthetic rules.` },
    { id:'fp-editor',    name:'Film Editor',          abbr:'ED',  role:'Pacing & Structure', desc:'Reviews structure, pacing, and narrative rhythm.',   tokens:35_000,  maxOutput:2048, color:'#a3e635', bg:'rgba(163,230,53,0.12)',  system:`You are a Film Editor. Write an editing plan: scene order rationale, pacing notes, cut timing, music cue placements, transition styles, and narrative rhythm observations.` },
  ],
  'ad-agency': [
    { id:'ag-creative',  name:'Creative Director', abbr:'CD',  role:'Campaign Vision',     desc:'Sets the big idea and creative direction.',           tokens:80_000,  maxOutput:2048, color:'#38bdf8', bg:'rgba(56,189,248,0.12)',  system:`You are a Creative Director at a top ad agency. Write a creative brief: the big campaign idea, creative concept, tone of voice, key message, emotional hook, and 3 creative territory options.` },
    { id:'ag-copy',      name:'Copywriter',        abbr:'CPY', role:'Messaging & Copy',    desc:'Writes headlines, body copy, CTAs, and taglines.',    tokens:120_000, maxOutput:4096, color:'#7dd3fc', bg:'rgba(125,211,252,0.12)', system:`You are a Senior Copywriter. Write compelling campaign copy: headline options, tagline variations, body copy for key placements, CTAs, and social media posts. Match the brand voice and strategy.` },
    { id:'ag-art',       name:'Art Director',      abbr:'AD',  role:'Visual Design',       desc:'Directs visual identity, layouts, and brand look.',   tokens:90_000,  maxOutput:3072, color:'#818cf8', bg:'rgba(129,140,248,0.12)', system:`You are an Art Director. Write a visual direction document: design system rules, typography hierarchy, imagery style, color palette, layout principles, and visual brand guidelines.` },
    { id:'ag-strategy',  name:'Brand Strategist',  abbr:'BS',  role:'Targeting & Insight', desc:'Defines audience, positioning, and key insight.',     tokens:100_000, maxOutput:3072, color:'#2dd4bf', bg:'rgba(45,212,191,0.12)',  system:`You are a Brand Strategist. Write a strategy document: consumer insight, audience personas, brand positioning statement, competitive landscape, key messages hierarchy, and success KPIs.` },
    { id:'ag-media',     name:'Media Planner',     abbr:'MP',  role:'Distribution',        desc:'Plans the media mix, channels, and campaign schedule.', tokens:80_000, maxOutput:2048, color:'#67e8f9', bg:'rgba(103,232,249,0.12)', system:`You are a Media Planner. Write a media plan: channel selection rationale, budget allocation per channel, campaign flight schedule, reach and frequency targets, and KPIs per channel.` },
  ],
  'newsroom': [
    { id:'nr-editor',    name:'Editor-in-Chief',    abbr:'EIC', role:'Editorial Direction', desc:'Sets the story angle, voice, and publication plan.',  tokens:80_000,  maxOutput:2048, color:'#f87171', bg:'rgba(248,113,113,0.12)', system:`You are an Editor-in-Chief. Write an editorial brief: story angle and hook, newsworthiness, target reader, key questions to answer, tone, structure, and publication format.` },
    { id:'nr-reporter',  name:'Reporter',            abbr:'REP', role:'Investigation',      desc:'Researches and writes the core article content.',     tokens:200_000, maxOutput:8192, color:'#fca5a5', bg:'rgba(252,165,165,0.12)', system:`You are an Investigative Reporter. Write a detailed article: compelling lede, nut graf, key findings, source descriptions, supporting evidence, key quotes, and a strong conclusion.` },
    { id:'nr-data',      name:'Data Journalist',     abbr:'DJ',  role:'Data & Viz',         desc:'Turns data into insights, charts, and infographics.', tokens:120_000, maxOutput:4096, color:'#fb923c', bg:'rgba(251,146,60,0.12)',  system:`You are a Data Journalist. Write a data analysis document: key statistics and findings, data visualization recommendations, source citations, methodology notes, and insight summaries.` },
    { id:'nr-photo',     name:'Photo Editor',        abbr:'PE',  role:'Visual Storytelling', desc:'Directs photography, image selection, and layout.',  tokens:60_000,  maxOutput:2048, color:'#fbbf24', bg:'rgba(251,191,36,0.12)',  system:`You are a Photo Editor. Write an image direction document: visual story concept, shot list, image style guide, caption writing guidelines, and layout recommendations.` },
    { id:'nr-checker',   name:'Fact Checker',        abbr:'FC',  role:'Verification',       desc:'Verifies facts, sources, and accuracy of all claims.', tokens:35_000, maxOutput:2048, color:'#a3e635', bg:'rgba(163,230,53,0.12)',  system:`You are a Fact Checker. Write a verification report: list of claims checked, sources verified, corrections required, accuracy rating, and flagged uncertainties that need resolution.` },
  ],
  'consulting': [
    { id:'co-director',   name:'Managing Director',    abbr:'MD', role:'Engagement Strategy', desc:'Leads the client engagement and defines success.',  tokens:80_000,  maxOutput:2048, color:'#fde047', bg:'rgba(253,224,71,0.12)',  system:`You are a Managing Director at a top-tier strategy consulting firm. Write an engagement charter: problem statement, project scope, working hypothesis, success criteria, team structure, and timeline.` },
    { id:'co-analyst',    name:'Data Analyst',          abbr:'DA', role:'Research & Insights', desc:'Conducts data analysis and surfaces key insights.', tokens:200_000, maxOutput:8192, color:'#facc15', bg:'rgba(250,204,21,0.12)',  system:`You are a Data Analyst. Write a data analysis report: key research findings, market sizing data, competitive benchmarks, statistical analysis, supporting evidence, and data gaps.` },
    { id:'co-strategy',   name:'Strategy Consultant',   abbr:'SC', role:'Recommendations',    desc:'Develops strategic options and recommendations.',    tokens:120_000, maxOutput:4096, color:'#fb923c', bg:'rgba(251,146,60,0.12)',  system:`You are a Strategy Consultant. Write a strategy document: situation analysis (as-is), key issues identified, strategic options evaluated, recommended path forward, and high-level implementation roadmap.` },
    { id:'co-delivery',   name:'Delivery Manager',      abbr:'DM', role:'Execution Plan',     desc:'Translates strategy into a concrete execution plan.', tokens:80_000, maxOutput:2048, color:'#4ade80', bg:'rgba(74,222,128,0.12)',  system:`You are a Delivery Manager. Write an execution plan: project phases and milestones, resource requirements, critical path dependencies, risk register, and measurable success metrics.` },
    { id:'co-specialist', name:'Industry Expert',       abbr:'IE', role:'Domain Knowledge',   desc:'Provides sector-specific expertise and intelligence.', tokens:100_000, maxOutput:3072, color:'#a3e635', bg:'rgba(163,230,53,0.12)', system:`You are an Industry Expert. Write a market intelligence brief: industry trends, regulatory environment, competitive dynamics, customer behavior shifts, and disruptive forces on the horizon.` },
  ],
};

/* ── Agent tag chips ── */
const AGENT_TAGS = {
  'pm':           ['PRD', 'ROADMAP', 'KPIs'],
  'cto':          ['ARCHITECTURE', 'API DESIGN', 'INFRA'],
  'lead-eng':     ['SPRINTS', 'CI/CD', 'CODE REVIEW'],
  'designer':     ['UI/UX', 'COMPONENTS', 'FIGMA'],
  'junior-dev':   ['REACT', 'FULL-STACK', 'FEATURES'],
  'sales':        ['GTM', 'PRICING', 'OUTREACH'],
  'qa':           ['TESTING', 'E2E', 'COVERAGE'],
  'legal':        ['GDPR', 'ToS', 'IP'],
  'gs-director':  ['DESIGN DOC', 'CORE LOOP', 'PROGRESSION'],
  'gs-engineer':  ['PHYSICS', 'COLLISION', 'ENTITIES'],
  'gs-artist':    ['ART STYLE', 'SPRITES', 'ANIMATION'],
  'gs-developer': ['CANVAS', 'GAME LOOP', 'INPUT'],
  'gs-qa':        ['BALANCE', 'BUG HUNT', 'PLAYTESTING'],
  'fp-director':  ['VISION', 'TONE', 'STORY'],
  'fp-writer':    ['SCRIPT', 'DIALOGUE', '3 ACT'],
  'fp-dop':       ['SHOTS', 'LIGHTING', 'COLOR'],
  'fp-designer':  ['SETS', 'COSTUMES', 'WORLD'],
  'fp-editor':    ['PACING', 'CUTS', 'RHYTHM'],
  'ag-creative':  ['BIG IDEA', 'CAMPAIGN', 'BRIEF'],
  'ag-copy':      ['HEADLINES', 'COPY', 'CTAs'],
  'ag-art':       ['DESIGN', 'TYPOGRAPHY', 'LAYOUT'],
  'ag-strategy':  ['PERSONAS', 'POSITIONING', 'INSIGHT'],
  'ag-media':     ['CHANNELS', 'BUDGET', 'REACH'],
  'nr-editor':    ['ANGLE', 'EDITORIAL', 'VOICE'],
  'nr-reporter':  ['REPORTING', 'SOURCES', 'AP STYLE'],
  'nr-data':      ['DATA VIZ', 'STATS', 'INSIGHTS'],
  'nr-photo':     ['IMAGERY', 'CAPTIONS', 'LAYOUT'],
  'nr-checker':   ['VERIFY', 'SOURCES', 'ACCURACY'],
  'co-director':  ['CHARTER', 'SCOPE', 'HYPOTHESIS'],
  'co-analyst':   ['DATA', 'BENCHMARKS', 'FINDINGS'],
  'co-strategy':  ['OPTIONS', 'STRATEGY', 'ROADMAP'],
  'co-delivery':  ['MILESTONES', 'RISKS', 'KPIs'],
  'co-specialist':['TRENDS', 'MARKET', 'INTELLIGENCE'],
};

/* ── Portrait fallback map — reuse existing SVGs for new agent types ── */
const PORTRAIT_FALLBACK = {
  'gs-director':'pm',  'gs-engineer':'lead-eng', 'gs-artist':'designer',
  'gs-developer':'junior-dev', 'gs-qa':'qa',
  'fp-director':'pm',  'fp-writer':'legal',      'fp-dop':'cto',
  'fp-designer':'designer',    'fp-editor':'qa',
  'ag-creative':'pm',  'ag-copy':'legal',         'ag-art':'designer',
  'ag-strategy':'sales',       'ag-media':'cto',
  'nr-editor':'pm',    'nr-reporter':'junior-dev','nr-data':'cto',
  'nr-photo':'designer',       'nr-checker':'qa',
  'co-director':'pm',  'co-analyst':'cto',        'co-strategy':'legal',
  'co-delivery':'lead-eng',    'co-specialist':'junior-dev',
};

/* ── Phase 4 live agent meta ── */
const LIVE_AGENT_META = {
  ceo:        { name:'CEO',             abbr:'CEO', color:'#00e676', bg:'rgba(0,230,118,0.15)'    },
  'lead-eng': { name:'Lead Engineer',   abbr:'LE',  color:'#4fc3f7', bg:'rgba(79,195,247,0.15)'   },
  designer:   { name:'UI Designer',     abbr:'UID', color:'#ce93d8', bg:'rgba(206,147,216,0.15)'  },
  builder:    { name:'Developer',       abbr:'DEV', color:'#ffb74d', bg:'rgba(255,183,77,0.15)'   },
  qa:         { name:'QA Engineer',     abbr:'QA',  color:'#80cbc4', bg:'rgba(128,203,196,0.15)'  },
  sales:      { name:'Sales Lead',      abbr:'SL',  color:'#f06292', bg:'rgba(240,98,146,0.15)'   },
};

const PORTRAIT_ID_MAP = {
  ceo:        'pm',
  'lead-eng': 'lead-eng',
  builder:    'junior-dev',
  designer:   'designer',
  qa:         'qa',
  sales:      'sales',
};
