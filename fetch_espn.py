#!/usr/bin/env python3
"""
Source ESPN's public match API for INDEPENDENT World Cup stats.

ESPN's data comes from a different provider than FBref (Opta), which makes it a
genuine second opinion. Two uses:

  * Layer-5 external validation — validate_external.py compares these numbers to
    FBref's data.json and flags disagreements (WARN only; never blocks).
  * Corners — soccerdata/FBref doesn't expose corners reliably; the column ships
    empty early in a tournament, so data.json currently has corners=0. ESPN
    publishes `wonCorners` per team, so we fill the corners column from here.

ESPN's site API is undocumented but stable and free. A finished match summary is
immutable, so we cache summaries on disk (.espn_cache/, gitignored) and only ever
re-fetch the live day's scoreboard. Politeness: a short delay between real fetches.

    python3 fetch_espn.py                                  # print an aggregate summary
    python3 fetch_espn.py --patch-corners public/data.json # fill the corners column
"""

from __future__ import annotations

import json
import sys
import time
import unicodedata
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

SLUG = "fifa.world"
BASE = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{SLUG}"
START = date(2026, 6, 11)                 # WC 2026 opening match
CACHE = Path(".espn_cache")
UA = {"User-Agent": "Mozilla/5.0 (world-cup-analytics validation)"}


# Characters NFKD won't fold (they aren't accent+base decompositions) but that
# the two feeds spell differently. Keeps the player name join from missing.
_TRANSLIT = str.maketrans({
    "ı": "i", "İ": "i", "ø": "o", "Ø": "o", "ł": "l", "Ł": "l",
    "đ": "d", "Đ": "d", "ð": "d", "þ": "th", "ß": "ss", "æ": "ae", "œ": "oe",
})


def norm_name(s: str) -> str:
    """Accent/case-fold a player name for joining across sources."""
    s = s.translate(_TRANSLIT)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def _get(url: str, cache_key: str | None = None):
    if cache_key:
        f = CACHE / cache_key
        if f.exists():
            return json.loads(f.read_text())
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if cache_key:
        CACHE.mkdir(exist_ok=True)
        (CACHE / cache_key).write_text(json.dumps(data))
        time.sleep(0.3)                   # be a good citizen on a real fetch
    return data


def _pos(abbr: str) -> str:
    """Map ESPN's granular position (CD-L, CM, CF, G, SUB, ...) to the
    dashboard's FW/MF/DF/GK. Returns '' for SUB/unknown (the caller keeps the
    best non-empty role it has seen for that player across matches)."""
    if not abbr:
        return ""
    head = abbr.upper().split("-")[0]
    if head in ("G", "GK"):
        return "GK"
    if head in ("CD", "CB", "LB", "RB", "LWB", "RWB", "WB", "FB", "D"):
        return "DF"
    if head in ("CM", "DM", "AM", "LM", "RM", "CDM", "CAM", "M"):
        return "MF"
    if head in ("CF", "ST", "SS", "LW", "RW", "F", "W"):
        return "FW"
    return ""


def _num(entries, name):
    """Numeric value of a named stat from an ESPN statistics list, or None."""
    for s in entries or []:
        if s.get("name") == name:
            v = s.get("value")
            if v is None:
                try:
                    v = float(s.get("displayValue"))
                except (TypeError, ValueError):
                    return None
            return v
    return None


def finished_events():
    """Every completed WC match from the opener through today (cached per past day)."""
    today = datetime.now(timezone.utc).date()
    out, d = [], START
    while d <= today:
        ymd = d.strftime("%Y%m%d")
        # Past days are settled, so cache them; always re-fetch the live day.
        key = None if d == today else f"sb_{ymd}.json"
        sb = _get(f"{BASE}/scoreboard?dates={ymd}", key)
        for e in sb.get("events", []):
            if e["competitions"][0]["status"]["type"].get("completed"):
                out.append(e)
        d += timedelta(days=1)
    return out


def _blank_team():
    return dict(name="", P=0, W=0, D=0, L=0, GF=0, GA=0, shots=0, sot=0, cor=0)


def accumulate():
    """Cumulative ESPN totals plus per-match splits across all finished matches.

    Returns (teams, players, team_games, player_games):
      teams[code]               -> {name,P,W,D,L,GF,GA,shots,sot,cor}
      players[(norm_name,code)] -> {name,pos,P,goals,assists,shots,sog}
      team_games[code]          -> [[date,opp,res,gf,ga,sh,sot,cor], ...]
      player_games[code][norm]  -> {date: [goals,assists,shots,sog]}
    """
    teams, players, seen = {}, {}, set()
    team_games, player_games = {}, {}

    for e in finished_events():
        eid = e["id"]
        if eid in seen:
            continue
        seen.add(eid)
        comp = e["competitions"][0]
        day = e.get("date", "")[:10]

        # id -> (code, goals) for the two sides, from the scoreboard competitors.
        side = {}
        for c in comp["competitors"]:
            t = c["team"]
            side[t["id"]] = (t.get("abbreviation", ""), int(c.get("score") or 0))
        id2code = {tid: code for tid, (code, _) in side.items()}

        summary = _get(f"{BASE}/summary?event={eid}", f"sum_{eid}.json")

        # Team shooting/corners from the boxscore — kept per match and summed.
        match_team = {}
        for t in summary.get("boxscore", {}).get("teams", []):
            code = t["team"].get("abbreviation") or id2code.get(t["team"].get("id"), "")
            if not code:
                continue
            sh = int(_num(t.get("statistics"), "totalShots") or 0)
            sot = int(_num(t.get("statistics"), "shotsOnTarget") or 0)
            cor = int(_num(t.get("statistics"), "wonCorners") or 0)
            match_team[code] = (sh, sot, cor)
            tt = teams.setdefault(code, _blank_team())
            tt["name"] = tt["name"] or t["team"].get("displayName", "")
            tt["shots"] += sh
            tt["sot"] += sot
            tt["cor"] += cor

        # Record + goals from the final score (covers own goals, which belong to
        # the team but to no player), and one per-match row for each side.
        if len(side) == 2:
            (ia, (ca, ga)), (ib, (cb, gb)) = list(side.items())
            for code, gf, ga_, opp in ((ca, ga, gb, cb), (cb, gb, ga, ca)):
                tt = teams.setdefault(code, _blank_team())
                tt["P"] += 1
                tt["GF"] += gf
                tt["GA"] += ga_
                res = "W" if gf > ga_ else "L" if gf < ga_ else "D"
                tt[res] += 1
                sh, sot, cor = match_team.get(code, (0, 0, 0))
                team_games.setdefault(code, []).append(
                    [day, opp, res, gf, ga_, sh, sot, cor])

        # Per-player shooting/scoring from the rosters — kept per match and summed.
        for r in summary.get("rosters", []):
            code = r["team"].get("abbreviation") or id2code.get(r["team"].get("id"), "")
            for p in r.get("roster", []):
                appeared = bool(p.get("starter")) or bool(_num(p.get("stats"), "appearances"))
                if not appeared:
                    continue
                disp = p["athlete"].get("displayName", "")
                nn = norm_name(disp)
                pp = players.setdefault((nn, code), dict(name=disp, pos="", P=0, goals=0,
                                                         assists=0, shots=0, sog=0))
                role = _pos((p.get("position") or {}).get("abbreviation"))
                if role and not pp["pos"]:      # keep the first real (non-SUB) role seen
                    pp["pos"] = role
                g = int(_num(p.get("stats"), "totalGoals") or 0)
                a = int(_num(p.get("stats"), "goalAssists") or 0)
                sh = int(_num(p.get("stats"), "totalShots") or 0)
                sog = int(_num(p.get("stats"), "shotsOnTarget") or 0)
                pp["P"] += 1
                pp["goals"] += g
                pp["assists"] += a
                pp["shots"] += sh
                pp["sog"] += sog
                player_games.setdefault(code, {}).setdefault(nn, {})[day] = [g, a, sh, sog]

    return teams, players, team_games, player_games


def build_data(teams, players, team_games, player_games) -> dict:
    """Assemble the exact data.json shape the dashboard expects from ESPN aggregates.

    Adds a `games` block for the per-match dropdowns:
      games.teams[code]           -> [[date,opp,res,gf,ga,sh,sot,cor], ...] recent-first
      games.players[code][name]   -> {date: [goals,assists,shots,sog]}
    The UI renders a player's games by walking games.teams[player.team] (so the
    full schedule shows, incl. DNPs) and looking up each date in games.players.
    """
    team_rows = []
    for code, t in teams.items():
        if not code:
            continue
        team_rows.append([code, t["name"], t["P"], t["W"], t["D"], t["L"],
                          t["GF"], t["GA"], t["shots"], t["sot"], t["cor"]])
    team_rows.sort(key=lambda x: -(x[6] / x[2]) if x[2] else 0)      # goals/game

    player_rows = []
    # Re-key each player's per-match splits from the internal norm_name to the
    # exact display name in the row, so the UI can look them up by player.name.
    pg_by_display = {}
    for (nn, code), p in players.items():
        if p["P"] == 0 or not code:
            continue
        player_rows.append([p["name"], code, p["pos"], p["P"],
                            p["goals"], p["assists"], p["shots"], p["sog"]])
        splits = player_games.get(code, {}).get(nn)
        if splits:
            pg_by_display.setdefault(code, {})[p["name"]] = splits
    # most relevant first: goals+assists, nudged by shot volume (matches old sort)
    player_rows.sort(key=lambda x: -(x[4] + x[5] + 0.1 * x[6]))

    games_teams = {code: sorted(rows, key=lambda g: g[0], reverse=True)  # recent-first
                   for code, rows in team_games.items()}

    matchday = max((r[2] for r in team_rows), default=0)
    return {
        "updated": datetime.now(timezone.utc).isoformat(),
        "matchday": matchday,
        "teams": team_rows,
        "players": player_rows,
        "games": {"teams": games_teams, "players": pg_by_display},
    }


def write_data(path: str):
    """Fetch ESPN, build data.json, and write it — the primary data pipeline."""
    teams, players, team_games, player_games = accumulate()
    data = build_data(teams, players, team_games, player_games)
    # Never overwrite good data with an empty pull (ESPN down / no matches yet).
    if not data["teams"] or not data["players"]:
        sys.exit(f"Refusing to write: got {len(data['teams'])} teams / "
                 f"{len(data['players'])} players from ESPN.")
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"Wrote {out}  ({len(data['teams'])} teams, {len(data['players'])} players, "
          f"through ~{data['matchday']} games)")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if "--summary" in sys.argv:
        teams, players, *_ = accumulate()
        print(f"ESPN: {len(teams)} teams, {len(players)} players across finished matches.")
        for p in sorted(players.values(), key=lambda p: -p["shots"])[:5]:
            print(f"  {p['name']:<22} {p['P']}g  {p['goals']}G {p['assists']}A  "
                  f"{p['shots']}sh {p['sog']}sot")
        return
    write_data(args[0] if args else "public/data.json")


if __name__ == "__main__":
    main()
