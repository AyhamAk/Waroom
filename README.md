# War Room

A multi-agent AI simulation where autonomous agents plan, design, and ship a real product together — live in your browser.

You write a brief. Pick your team. Hit start. AI agents wake up, collaborate over a streaming SSE feed, and build a working artifact in real time — cycling, fixing, and improving every round.

---

## Studios

War Room ships three studios, each with its own pipeline:

| Studio | Agents | Output |
|--------|--------|--------|
| **Tech Startup** | CEO, Lead Engineer, Designer, Developer, QA, Sales (and others) | Web apps, dashboards, SaaS products. Multiple categories: Tech Startup, Game Studio (2D), Film Production, Ad Agency, Newsroom, Consulting. |
| **3D Game Studio** | Game Director, Level Designer, Asset Lead, Engine Engineer, Tech-Art, Gameplay Programmer, Vision Playtester | A playable Three.js game served at `/preview-game`. LangGraph-orchestrated, level/asset/material JSON pipeline, Vite build, vision-based playtester. |
| **Blender Studio** | Blender Artist (3D), Animator, Renderer, QA | Procedural Blender scenes rendered to PNG/MP4. |

---

## Getting Started

**1. Clone**
```bash
git clone https://github.com/AyhamAk/Waroom.git
cd warroom
```

**2. Install Python deps**
```bash
cd backend
pip install -r requirements.txt
```

**3. Add your API key**
Create `.env` at the repo root:
```env
ANTHROPIC_API_KEY=your_key_here
```

**4. Run**
```bash
cd backend && python main.py
```
Open [http://localhost:3000](http://localhost:3000).

Switch tabs at the top of the page to enter a studio.

---

## How It Works

Each studio runs a continuous loop. The Tech Startup default looks roughly like:

```
CEO → Lead Engineer + Designer (parallel) → Developer → QA → repeat
```

The 3D Game Studio runs a LangGraph state machine:

```
Director → Level Designer → Asset Lead → Engine ↘
                                                 → Gameplay → Playtester → loop
                                          Tech-Art ↗
```

Agents stream their thinking and tool calls over an SSE feed (`/api/stream`). The frontend renders a live agent roster, status badges, and a preview iframe that auto-refreshes when the build artifact changes.

---

## Stack

- **Backend** — Python (FastAPI + uvicorn), LangGraph for the 3D pipeline, Anthropic SDK with prompt caching
- **AI** — Anthropic Claude (streaming, tool use)
- **Real-time** — Server-Sent Events (SSE)
- **Frontend** — Vanilla JS, no build step (loaded directly from `public/`)
- **Preview runtime** — Vite-built Three.js bundle served from the active session's workspace

---

## Project layout

```
backend/
├── main.py                  FastAPI app: studios, SSE, preview routing
├── agents/                  Per-agent tool loops (base.py is the engine)
├── graph/                   LangGraph state machine for 3D Game Studio
├── recipes/games/           Genre recipes (top-down shooter, FPS arena, …)
├── templates/game_base/     Vite + Three.js project template the agents extend
├── tools/                   File ops, asset bridge, vision playtester
└── assets/                  Bundled HDRIs, textures, sounds

public/                      Static frontend, no build step
workspace/                   Per-session generated artifacts (gitignored)
```

---

## License

MIT — see [LICENSE](LICENSE)
