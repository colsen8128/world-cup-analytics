# World Cup Analytics · 2026

A three-page dashboard of per-game team and player statistics for the 2026 FIFA
World Cup, with a data pipeline that refreshes automatically at the end of each
match day.

- **Home** — top-5 leaderboards for the headline team and player stats
- **Teams** — full sortable table: record, goals/game, allowed/game, goal
  diff/game, shots/game, shots on target/game, corners/game
- **Players** — full sortable table: goals/game, assists/game, shots/game,
  shots on goal/game

The dashboard reads a single `public/data.json`. A scheduled GitHub Actions job
regenerates that file from **ESPN** (near-live, and its public API isn't
IP-blocked, so it runs in CI). **FBref** is kept as an independent second opinion
to validate the numbers. Swap the data source without touching the UI — the front
end only knows about `data.json`.

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
├── fetch_espn.py              # PRIMARY data pipeline: ESPN -> public/data.json
├── fetch_fbref.py             # FBref pipeline, now used as the validator source
├── validate.py                # gating validation (schema/invariant/reconcile/temporal)
├── validate_external.py       # advisory cross-source audit vs FBref (local only)
├── test/derive.test.mjs       # golden test for the UI per-game math
├── probe_balldontlie.py       # optional: tier-check a BALLDONTLIE API key
└── .github/workflows/
    ├── refresh-data.yml       # scheduled ESPN fetch + validate + commit
    └── deploy.yml             # build + publish to GitHub Pages on push
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

## 2. Generate real data from ESPN

Requires Python 3.9+ — standard library only, nothing to install.

```bash
python3 fetch_espn.py            # writes public/data.json
```

Then reload the dashboard — the footer flips from "Sample data" to "Live data".

### How the eleven stats are sourced (ESPN)
- **Goals, assists, shots, shots on target, matches played** — ESPN match
  summaries (`rosters[].roster[].stats`), accumulated across every finished match
- **Total shots / on target / corners** (teams) — ESPN match boxscore team stats
- **Record (W-D-L), goals for/against** — the final scores from the scoreboard

ESPN match summaries are immutable once final, so `fetch_espn.py` caches them under
`.espn_cache/` (gitignored) and only re-fetches the live day — re-runs are fast and
polite. ESPN's data comes from a different provider than FBref (Opta), which is why
FBref makes a good independent validator (below).

## 3. Refresh the data and publish

This is **automated in CI**. `.github/workflows/refresh-data.yml` runs on a
schedule: it fetches ESPN, runs `validate.py` (which blocks the commit on any
error), commits `public/data.json`, and pushes. That push triggers
`deploy.yml`, which rebuilds and republishes to GitHub Pages in ~1–2 minutes.
ESPN's public API isn't IP-blocked, so unlike the old FBref pipeline this runs
fine on GitHub's runners — no local machine required.

To refresh by hand (and additionally run the FBref second opinion), use:

```bash
npm run refresh        # or: ./refresh.sh
```

`refresh.sh` does the ESPN fetch + validation locally, then — if you've set up
the `venv` (see below) — runs `validate_external.py`, the advisory cross-check
against FBref. That check is local-only because FBref/Cloudflare blocks
datacenter IPs; it never blocks publishing.

## 4. Validate the data

Two independent guards keep the numbers honest:

- **`validate.py` (gating)** — schema, football invariants, cross-table
  reconciliation, and temporal monotonicity vs the last commit. A single error
  aborts the refresh so a bad scrape can't overwrite good data. Runs in CI.
- **`validate_external.py` (advisory, local)** — cross-checks ESPN's numbers
  against FBref (Opta). When FBref has caught up it should agree; when it lags a
  just-finished match it's reported as "behind", not an error. Needs the FBref
  venv and a residential IP.

The UI's per-game math has its own golden test: `npm test`.

### FBref validator setup (optional)

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install soccerdata lxml html5lib pandas
python3 validate_external.py      # ESPN data.json vs FBref, writes a report
```

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
| **ESPN hidden API** | Free | Yes (incl. corners) | Near-live, no key, **not IP-blocked → runs in CI**; undocumented but stable |
| FBref via soccerdata | Free | 10 direct + corners via 1 extra read | Opta-sourced; datacenter-IP-blocked, lags live by hours. Now the **validator** |
| API-Football | Free tier / ~€19/mo | Yes | Independent; free tier had no 2026 fixtures loaded when checked |
| BALLDONTLIE | $39.99/mo (GOAT) | Yes | Shots/corners gated behind the paid tier |
| Sportmonks / TheStatsAPI | €50-100+/mo | Yes | Most reliable live; priciest |

Current choice: **ESPN** as source of truth, **FBref** as an independent
validator. Each pipeline is isolated (`fetch_espn.py` / `fetch_fbref.py`) and
emits the same `data.json` shape, so the UI never changes. ESPN was chosen after
FBref repeatedly lagged just-finished matches (its Opta comp pages update hours
after kickoff), which stale-data incidents kept surfacing.
