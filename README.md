# World Cup Analytics · 2026

A three-page dashboard of per-game team and player statistics for the 2026 FIFA
World Cup, with a data pipeline that refreshes automatically at the end of each
match day.

- **Home** — top-5 leaderboards for the headline team and player stats
- **Teams** — full sortable table: record, goals/game, allowed/game, goal
  diff/game, shots/game, shots on target/game, corners/game
- **Players** — full sortable table: goals/game, assists/game, shots/game,
  shots on goal/game

The dashboard reads a single `public/data.json`. A scheduled job regenerates
that file from FBref each day. Swap the data source without touching the UI — the
front end only knows about `data.json`.

---

## Project layout

```
World Cup Analytics/
├── index.html                 # Vite host page
├── package.json               # front-end deps + scripts
├── vite.config.js
├── src/
│   ├── main.jsx               # React entry point
│   └── Dashboard.jsx          # the three-page dashboard
├── public/
│   └── data.json              # the data the dashboard reads (sample to start)
├── fetch_fbref.py             # data pipeline: FBref -> public/data.json
├── probe_balldontlie.py       # optional: tier-check a BALLDONTLIE API key
└── .github/workflows/update.yml  # daily auto-refresh
```

---

## 1. Run the dashboard

Requires Node 18+.

```bash
npm install
npm run dev          # http://localhost:5173
```

It renders the bundled sample data immediately, then replaces it with
`public/data.json` if that file is present. Build for production with
`npm run build` (output in `dist/`).

## 2. Generate real data from FBref

Requires Python 3.10+. FBref must be reachable from the machine you run this on.

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install soccerdata lxml html5lib pandas
python3 fetch_fbref.py            # writes public/data.json
```

Then reload the dashboard — the footer flips from "Sample data" to "Live data".

### How the eleven stats are sourced
- **Goals, assists, matches played** — FBref *standard* table (via soccerdata)
- **Shots, shots on target** (teams and players) — FBref *shooting* table
- **Record (W-D-L), goals for/against** — computed from the match schedule
- **Corners** — one direct read of FBref's team passing-types table, because
  soccerdata doesn't expose it. If that table changes, corners fall back to 0
  and the rest of the run is unaffected.

soccerdata caches every page under `~/soccerdata` and rate-limits requests —
leave that on. Re-runs are fast and stay polite to FBref. Review FBref's data
usage terms before any commercial use.

## 3. Automate the daily refresh

`.github/workflows/update.yml` runs `fetch_fbref.py` on a cron and commits the
updated `public/data.json`. Adjust the cron time to a few hours after the last
match of the day in your time zone.

- **Vercel / Netlify**: connect the repo; the commit from the workflow triggers
  a redeploy automatically. Nothing else needed.
- **GitHub Pages**: add a deploy step that runs `npm ci && npm run build` and
  publishes `dist/` (e.g. with `actions/deploy-pages`), triggered on push to
  `main`.

---

## Optional: BALLDONTLIE tier check

If you ever consider the paid BALLDONTLIE FIFA API instead of FBref,
`probe_balldontlie.py` reports which of the eleven stats your API key's tier can
actually reach:

```bash
export BDL_API_KEY="your_key"
python3 probe_balldontlie.py
```

On the FIFA World Cup API, the free tier returns only teams/stadiums, ALL-STAR
($9.99) adds group standings, and the match-level shot/corner and player stats
require GOAT ($39.99). A 48-hour GOAT trial lets you verify everything before
paying — run the probe during that window.

## Data source options considered

| Source | Cost | Your 11 stats | Notes |
|---|---|---|---|
| **FBref via soccerdata** | Free | 10 direct + corners via 1 extra read | Opta-sourced, accurate; you maintain a scraper |
| Community CSV datasets | Free | Yes (incl. corners) | Lowest effort; depends on a maintainer, gaps possible |
| API-Football | ~€19/mo | Yes | Cheaper paid option; older-school API |
| BALLDONTLIE | $39.99/mo (GOAT) | Yes | Cleanest integration, xG/shot maps |
| Sportmonks / TheStatsAPI | €50-100+/mo | Yes | Most reliable live; priciest |

Current choice: **FBref**. The pipeline is isolated in `fetch_fbref.py`, so
switching later only means rewriting that one file to emit the same
`data.json` shape.
