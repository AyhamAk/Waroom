# War Room

A multi-agent AI simulation where autonomous agents plan, design, and ship a real product together — live in your browser.

You write a brief. Pick your team. Hit start. Six AI agents wake up, collaborate, and build a working website in real time — cycling forever, improving every round.

---

## Features

- **6 autonomous agents** — CEO, Lead Engineer, Designer, Developer, QA, Sales
- **Infinite cycles** — agents keep building, improving, and fixing on their own
- **Live preview** — real HTML/CSS/JS shipped to your browser every cycle
- **CEO sees the site** — gets a screenshot before deciding what to build next
- **Inject a crisis** — production down, investor pulled out, competitor launched
- **Customer feedback** — drop in as a user mid-session, CEO reprioritizes immediately
- **Auto-pause** — pipeline pauses when you close the tab, resumes when you return
- **Multiple company types** — Tech Startup, Game Studio, Film Production, Ad Agency, Newsroom, Consulting

---

## Getting Started

**1. Clone and install**
```bash
git clone https://github.com/your-username/warroom.git
cd warroom
npm install
```

**2. Add your API key**
```bash
cp .env.example .env
```
Open `.env` and replace the placeholder with your key (see API Keys below).

**3. Run**
```bash
npm start
```
Open [http://localhost:3000](http://localhost:3000)

---

## API Keys

War Room supports two providers. You only need one.

### Anthropic Claude (recommended)
Best results. Paid — charged per token.
Get your key at [console.anthropic.com](https://console.anthropic.com)

```env
ANTHROPIC_API_KEY=your_key_here
```

### Google Gemini (free tier available)
Free quota available. Good for experimentation.
Get your key at [aistudio.google.com](https://aistudio.google.com)

```env
GOOGLE_API_KEY=your_key_here
```

You select which provider to use in the app UI before launching a session.

---

## How It Works

Each session runs in a continuous loop:

```
CEO → Lead Engineer + Designer (parallel) → Developer → QA → repeat
```

| Agent | Role |
|-------|------|
| **CEO** | Reads current site state + screenshot, decides what to build next |
| **Lead Engineer** | Writes technical spec based on CEO decision |
| **Designer** | Writes UI/design spec |
| **Developer** | Ships real HTML, CSS, and JS every cycle |
| **QA** | Flags broken logic — CEO reads it next round |
| **Sales** | Writes cold outreach emails for the product being built |

Every cycle the developer builds on top of what was shipped before. The site grows and improves on its own.

---

## Company Categories

| Category | What agents build |
|----------|------------------|
| Tech Startup | Web apps, dashboards, SaaS products |
| Game Studio | Playable HTML5 canvas games |
| Film Production | Cinematic editorial sites |
| Ad Agency | High-converting landing pages |
| Newsroom | Editorial news and magazine sites |
| Consulting | Strategy decks and professional reports |

---

## Stack

- **Backend** — Node.js, Express
- **AI** — Anthropic Claude API / Google Gemini API
- **Real-time** — Server-Sent Events (SSE)
- **Frontend** — Vanilla JS, no framework

---

## License

MIT — see [LICENSE](LICENSE)
