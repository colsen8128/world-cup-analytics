#!/usr/bin/env python3
"""
Source the World Cup dashboard from FBref (free, Opta-sourced) via soccerdata.

Outputs public/data.json in the exact shape the dashboard expects:

    {
      "updated": ISO timestamp,
      "matchday": int,
      "teams":   [[code,name,P,W,D,L,GF,GA,shots,sot,corners], ...],
      "players": [[name,team,pos,P,goals,assists,shots,sog], ...]
    }

Setup (local machine — FBref must be reachable):
    python3 -m venv venv && source venv/bin/activate
    pip install soccerdata lxml html5lib pandas
    python3 fetch_fbref.py

Notes:
  * soccerdata caches every page under ~/soccerdata and rate-limits requests;
    leave that on — it keeps you a good citizen and makes re-runs instant.
  * 10 of the 11 metrics come from soccerdata. Corners come from one extra
    direct read of FBref's team passing-types table (soccerdata doesn't expose
    it). If that table's URL/columns ever change, corners fall back to 0 and the
    script still completes — everything else is unaffected.
  * Run on a daily cron AFTER the last match of the day to satisfy the
    "update at end of each match day" requirement.
"""

import html as htmllib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import soccerdata as sd

LEAGUE = "INT-World Cup"
SEASON = "2026"
OUT = Path("public/data.json")

# Full FBref nation name -> 3-letter code (fallback: first 3 alpha chars upper).
CODES = {
    "Argentina": "ARG", "France": "FRA", "Brazil": "BRA", "Spain": "ESP",
    "England": "ENG", "Portugal": "POR", "Netherlands": "NED", "Germany": "GER",
    "United States": "USA", "Croatia": "CRO", "Mexico": "MEX", "Japan": "JPN",
    "Morocco": "MAR", "Canada": "CAN", "Senegal": "SEN", "Saudi Arabia": "KSA",
    "Belgium": "BEL", "Uruguay": "URU", "Colombia": "COL", "Italy": "ITA",
    "Switzerland": "SUI", "Denmark": "DEN", "South Korea": "KOR",
    "Korea Republic": "KOR", "Australia": "AUS", "Poland": "POL", "Serbia": "SRB",
    "Ecuador": "ECU", "Norway": "NOR", "Egypt": "EGY", "Nigeria": "NGA",
    "Ghana": "GHA", "Iran": "IRN", "Austria": "AUT", "Ukraine": "UKR",
}


def code_for(name: str) -> str:
    if name in CODES:
        return CODES[name]
    letters = re.sub(r"[^A-Za-z]", "", name).upper()
    return (letters[:3] or "UNK")


# FBref competition pages (comp id 1 = World Cup). We parse these AGGREGATE
# pages directly by their stable data-stat attributes, rather than using
# soccerdata's read_*_season_stats — those build team/player totals from each
# squad's individual page (/en/squads/.../Portugal-Men-Stats), which on FBref
# can lag the competition tables badly (e.g. a played match missing entirely).
SHOOTING_URL = "https://fbref.com/en/comps/1/shooting/World-Cup-Stats"
STATS_URL = "https://fbref.com/en/comps/1/stats/World-Cup-Stats"
PASSING_URL = "https://fbref.com/en/comps/1/passing_types/World-Cup-Stats"


def _fetch(fb: "sd.FBref", url: str) -> str:
    """Fetch a page via soccerdata's Cloudflare-aware, cached downloader."""
    page = fb.get(url).read()
    return page.decode("utf-8", "replace") if isinstance(page, bytes) else page


def _rows(page: str):
    return re.findall(r"<tr[^>]*>.*?</tr>", page, re.S)


def _cells(row: str) -> dict:
    """Map every data-stat in a row to its tag-stripped, unescaped text."""
    return {
        stat: htmllib.unescape(re.sub(r"<[^>]+>", "", val)).strip()
        for stat, val in re.findall(r'data-stat="([^"]+)"[^>]*>(.*?)</t[dh]>', row, re.S)
    }


def _squad_name(row: str):
    """Clean squad name from a row's /en/squads/ link (no flag-code prefix)."""
    m = re.search(r'href="/en/squads/[^"]*"[^>]*>([^<]+)</a>', row)
    return htmllib.unescape(m.group(1)).strip() if m else None


def _to_int(s) -> int:
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return 0


def team_shooting(fb: "sd.FBref") -> dict:
    """{team_name: (shots, shots_on_target)} from the competition shooting page.

    Reads squad summary rows from the "for" (Squad) table only: they link to
    /en/squads/, carry no per-player cell, and aren't the "vs Opponent" table.
    """
    out = {}
    for row in _rows(_fetch(fb, SHOOTING_URL)):
        if "/en/squads/" not in row or 'data-stat="player"' in row:
            continue
        c = _cells(row)
        name = _squad_name(row)
        if not name or name.lower().startswith("vs "):
            continue  # missing, or the opponent ("vs") table
        if "shots" in c:
            out.setdefault(name, (_to_int(c.get("shots")),
                                  _to_int(c.get("shots_on_target"))))
    return out


def player_rows(fb: "sd.FBref", url: str):
    """List of (player_name, team_name, cells) for each player row on a comp page."""
    out = []
    for row in _rows(_fetch(fb, url)):
        if 'data-stat="player"' not in row:
            continue
        c = _cells(row)
        name = c.get("player", "")
        if not name or name == "Player":
            continue  # repeated mid-table header rows
        out.append((name, _squad_name(row) or c.get("team", ""), c))
    return out


def team_records(schedule: pd.DataFrame) -> dict:
    """Compute P/W/D/L/GF/GA per team from completed matches in the schedule."""
    rec = {}

    def bump(t):
        rec.setdefault(t, dict(P=0, W=0, D=0, L=0, GF=0, GA=0))
        return rec[t]

    # Find home/away score either as split columns or a 'score' string "h–a".
    has_split = {"home_score", "away_score"}.issubset(
        {str(c).lower() for c in schedule.columns})

    for _, row in schedule.iterrows():
        home = row.get("home_team")
        away = row.get("away_team")
        if not isinstance(home, str) or not isinstance(away, str):
            continue
        hs = aw = None
        if has_split:
            hs, aw = row.get("home_score"), row.get("away_score")
        else:
            s = str(row.get("score", ""))
            m = re.match(r"\s*(\d+)\s*[–\-:]\s*(\d+)\s*", s)
            if m:
                hs, aw = int(m.group(1)), int(m.group(2))
        if hs is None or aw is None or pd.isna(hs) or pd.isna(aw):
            continue  # not played yet
        hs, aw = int(hs), int(aw)
        h, a = bump(home), bump(away)
        h["P"] += 1; a["P"] += 1
        h["GF"] += hs; h["GA"] += aw
        a["GF"] += aw; a["GA"] += hs
        if hs > aw:
            h["W"] += 1; a["L"] += 1
        elif hs < aw:
            a["W"] += 1; h["L"] += 1
        else:
            h["D"] += 1; a["D"] += 1
    return rec


def fetch_corners(fb: "sd.FBref") -> dict:
    """{team_name: corners_taken} from the competition passing-types page.

    soccerdata doesn't expose this table. Reads the stable data-stat="corner_kicks"
    from squad "for" rows. Best-effort: returns {} (corners fall back to 0) on
    failure or while FBref still publishes the column empty (early in a tournament).
    """
    try:
        out = {}
        for row in _rows(_fetch(fb, PASSING_URL)):
            if "/en/squads/" not in row or 'data-stat="player"' in row:
                continue
            name = _squad_name(row)
            if not name or name.lower().startswith("vs "):
                continue  # missing, or the opponent ("vs") table
            ck = _cells(row).get("corner_kicks", "")
            if ck.isdigit():
                out.setdefault(name, int(ck))
        if not out:
            print("  ! corners column is empty on FBref right now; corners set to 0",
                  file=sys.stderr)
        return out
    except Exception as e:
        print(f"  ! corners fetch failed ({e}); corners set to 0", file=sys.stderr)
        return {}


def main():
    fb = sd.FBref(leagues=LEAGUE, seasons=SEASON)

    print("Reading schedule ...")
    rec = team_records(fb.read_schedule())

    print("Reading team shooting (competition page) ...")
    tshoot = team_shooting(fb)

    print("Reading corners (competition page) ...")
    corners = fetch_corners(fb)

    teams = []
    for name in sorted(set(rec) | set(tshoot)):
        r = rec.get(name, dict(P=0, W=0, D=0, L=0, GF=0, GA=0))
        sh, sot = tshoot.get(name, (0, 0))
        teams.append([
            code_for(name), name, r["P"], r["W"], r["D"], r["L"],
            r["GF"], r["GA"], sh, sot, _to_int(corners.get(name, 0)),
        ])
    teams.sort(key=lambda x: -(x[6] / x[2]) if x[2] else 0)  # goals/game

    print("Reading player stats (competition pages) ...")
    shooting = {(p, t): c for p, t, c in player_rows(fb, SHOOTING_URL)}
    players = []
    for name, team, c in player_rows(fb, STATS_URL):
        mp = _to_int(c.get("games"))
        if mp == 0:
            continue
        sc = shooting.get((name, team), {})
        players.append([
            name, code_for(team), (c.get("position", "") or "")[:2],
            mp, _to_int(c.get("goals")), _to_int(c.get("assists")),
            _to_int(sc.get("shots")), _to_int(sc.get("shots_on_target")),
        ])
    # keep the most relevant first: goals+assists, with a nudge for shot volume
    players.sort(key=lambda x: -(x[4] + x[5] + 0.1 * x[6]))

    matchday = max((t[2] for t in teams), default=0)
    payload = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "matchday": matchday,
        "teams": teams,
        "players": players,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"\nWrote {OUT}  ({len(teams)} teams, {len(players)} players, "
          f"through ~{matchday} games)")


if __name__ == "__main__":
    main()
