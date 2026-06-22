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


def col(df: pd.DataFrame, leaf: str, group: str | None = None):
    """Return a column Series from a (possibly MultiIndex) DataFrame by leaf name.

    Prefers an exact, case-insensitive match on the leaf (last) level, optionally
    constrained to a column group. Falls back to a 'contains' match. Returns a
    zero Series if nothing matches so the pipeline never crashes on a rename.
    """
    def leaf_of(c):
        return c[-1] if isinstance(c, tuple) else c

    def group_of(c):
        return c[0] if isinstance(c, tuple) else ""

    # exact leaf match
    for c in df.columns:
        if str(leaf_of(c)).lower() == leaf.lower():
            if group is None or group.lower() in str(group_of(c)).lower():
                return pd.to_numeric(df[c], errors="coerce").fillna(0)
    # fallback: contains
    for c in df.columns:
        if leaf.lower() in str(leaf_of(c)).lower():
            if group is None or group.lower() in str(group_of(c)).lower():
                return pd.to_numeric(df[c], errors="coerce").fillna(0)
    print(f"  ! column '{leaf}'"
          f"{' in '+group if group else ''} not found; using 0", file=sys.stderr)
    return pd.Series(0, index=df.index)


def text_col(df: pd.DataFrame, name: str) -> pd.Series:
    """Return a flat (non-numeric) column by name, matching ANY MultiIndex level.

    Flat single-level columns can land in either tuple position depending on the
    pandas version (e.g. ('pos','') on pandas 3.x vs ('','pos') earlier), so we
    check every level rather than assuming the leaf. Returns "" if absent.
    """
    for c in df.columns:
        parts = c if isinstance(c, tuple) else (c,)
        if any(str(p).lower() == name.lower() for p in parts):
            return df[c].fillna("").astype(str)
    return pd.Series("", index=df.index)


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
    """Pull corner kicks (CK) per team from FBref's passing-types page.

    soccerdata doesn't expose this table, so we fetch the page through its own
    Cloudflare-aware, cached downloader (fb.get) — plain urllib gets a 403 — and
    parse the stable `data-stat="corner_kicks"` attribute rather than read_html,
    whose multi-row headers misalign the columns.

    We read squad-level rows from the "for" (Squad) table only: those rows link
    to /en/squads/, carry no per-player cell, and aren't the "vs Opponent" table.
    Returns {team_full_name: corners_taken}. Best-effort; returns {} on failure
    or while FBref still publishes the column empty (early in the tournament).
    """
    url = "https://fbref.com/en/comps/1/passing_types/World-Cup-Stats"

    def cell(row: str, stat: str) -> str | None:
        m = re.search(r'data-stat="%s"[^>]*>(.*?)</t[dh]>' % stat, row, re.S)
        if not m:
            return None
        return htmllib.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()

    try:
        page = fb.get(url).read()
        if isinstance(page, bytes):
            page = page.decode("utf-8", "replace")
        out = {}
        for row in re.findall(r"<tr[^>]*>.*?</tr>", page, re.S):
            # squad summary rows link to a squad page and have no player cell
            if "/en/squads/" not in row or 'data-stat="player"' in row:
                continue
            m = re.search(r'data-stat="team"[^>]*>.*?<a [^>]*>(.*?)</a>', row, re.S)
            if not m:
                continue
            name = htmllib.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
            if not name or name.lower().startswith("vs "):
                continue  # skip the opponent ("vs") table
            ck = cell(row, "corner_kicks")
            if ck and ck.isdigit():
                out.setdefault(name, int(ck))  # first table = "for"
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
    schedule = fb.read_schedule()
    rec = team_records(schedule)

    print("Reading team shooting ...")
    tshoot = fb.read_team_season_stats(stat_type="shooting")
    t_sh = col(tshoot, "Sh", group="Standard")
    t_sot = col(tshoot, "SoT", group="Standard")

    print("Reading corners (direct FBref) ...")
    corners = fetch_corners(fb)

    # team full name lives in the last index level
    def name_of(idx):
        return idx[-1] if isinstance(idx, tuple) else idx

    teams = []
    for idx in tshoot.index:
        name = name_of(idx)
        r = rec.get(name, dict(P=0, W=0, D=0, L=0, GF=0, GA=0))
        teams.append([
            code_for(name), name, r["P"], r["W"], r["D"], r["L"],
            r["GF"], r["GA"], int(t_sh.loc[idx]), int(t_sot.loc[idx]),
            int(corners.get(name, 0)),
        ])
    teams.sort(key=lambda x: (-(x[3] and (x[6] / x[2]) or 0)))  # rough: goals/game

    print("Reading player standard + shooting ...")
    pstd = fb.read_player_season_stats(stat_type="standard")
    pshoot = fb.read_player_season_stats(stat_type="shooting")
    p_mp = col(pstd, "MP", group="Playing")
    p_g = col(pstd, "Gls", group="Performance")
    p_a = col(pstd, "Ast", group="Performance")
    p_pos = text_col(pstd, "pos")
    p_sh = col(pshoot, "Sh", group="Standard")
    p_sot = col(pshoot, "SoT", group="Standard")

    players = []
    for idx in pstd.index:
        # index is (league, season, team, player)
        team = idx[-2] if isinstance(idx, tuple) and len(idx) >= 2 else ""
        player = idx[-1] if isinstance(idx, tuple) else idx
        mp = int(p_mp.loc[idx]) if idx in p_mp.index else 0
        if mp == 0:
            continue
        sh = int(p_sh.loc[idx]) if idx in p_sh.index else 0
        sot = int(p_sot.loc[idx]) if idx in p_sot.index else 0
        players.append([
            player, code_for(team), str(p_pos.loc[idx])[:2] or "",
            mp, int(p_g.loc[idx]), int(p_a.loc[idx]), sh, sot,
        ])
    # keep the most relevant: sort by goals+assists desc, cap for a lean file
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
