# Chemistry Skill Map

Build and view **prerequisite graphs** from Cambridge Chemistry syllabuses (O Level 5070, AS & A Level 9701).

Inspired by [Marble's os-taxonomy](https://github.com/withmarbleapp/os-taxonomy) — nodes + dependency edges as teachable micro-skills.

## Quick start (local)

```bash
python -m pip install -r pipeline/requirements.txt
npm run serve
# http://localhost:5000/       — 2D graph
# http://localhost:5000/3d.html — 3D pyramid view
# http://localhost:5000/create.html — upload PDF (needs Python server)
```

Regenerate map data from a syllabus PDF:

```bash
npm run build      # python pipeline/run.py
npm run validate
```

## Deploy on Vercel (viewers only)

The repo includes `vercel.json` — it publishes the `viz/` folder as a static site.

1. Push this repo to GitHub
2. Import the project at [vercel.com/new](https://vercel.com/new)
3. Deploy (no env vars needed)

**On Vercel:** 2D/3D viewers and all bundled maps work. PDF upload, export zip, and `create.html` need the Python server (`npm run serve` on a VPS/Lightsail).

## Deploy full app (create + export)

Run on a VPS / Lightsail / Oracle Always Free:

```bash
pip install -r pipeline/requirements.txt
PORT=5000 npm start
```

Use systemd or similar to keep it running.

## Share locally with Cloudflare Tunnel (free)

Expose your running dev server to the internet without VS Code dev-tunnel limits.

**One-time:** install cloudflared

```bash
winget install Cloudflare.cloudflared
```

**Two terminals:**

```bash
# Terminal 1 — app server
npm run serve

# Terminal 2 — public HTTPS URL (trycloudflare.com)
npm run tunnel
```

Copy the `https://….trycloudflare.com` URL from the tunnel terminal and open it in a browser. PDF upload and export work through the tunnel (unlike Vercel static deploy).

## Project layout

```
sources/           Syllabus PDF(s) — drop 5070 PDF here
pipeline/
  extract.py       PDF → structured syllabus JSON
  build.py         syllabus → topics + dependencies + standards
  dependency_rules.json   Curated cross-topic prerequisite edges
  run.py           Runs extract + build
data/              Generated graph dataset (JSON)
viz/               Interactive graph viewer
scripts/
  validate.mjs     Integrity + cycle checks
  serve.py         Local HTTP server for the viewer
```

## What gets generated

| File | Contents |
|------|----------|
| `topics.json` | **296 micro-skills** (Marble-style teachable units) |
| `dependencies.json` | Prerequisite edges between micro-skills |
| `curriculum-standards.json` | Raw syllabus objectives from the PDF (341) |
| `manifest.json` | Counts and checksums |

Granularity: `microskills` — each node has `evidence`, `assessmentPrompt`, and links to syllabus standards.

## Graph viewer

**3D (default)** — Marble-inspired at `/` (or `3d.html`):
- Rotating 3D constellation of colored dots
- **Height** = prerequisite depth (foundations low, advanced high)
- **Threads** = prerequisite links with particle flow
- **Gold star** = syllabus start (`1.1.1`)
- Drag to spin, scroll to zoom, click a dot for prerequisite chain

**2D** — `/2d.html` for flat force/hierarchical layout + search

## Updating the syllabus

Replace the PDF in `sources/` and run `python pipeline/run.py` again.

## Notes

- Cross-topic dependencies are defined in `pipeline/dependency_rules.json` and can be edited manually.
- Within-topic edges are auto-generated sequentially (soft).
- Cambridge syllabus text is © Cambridge Assessment; use responsibly.
