#!/usr/bin/env python3
"""
Probe the BALLDONTLIE FIFA World Cup API to confirm which of the dashboard's
11 required stats are actually returned by your key's tier.

Run during the 48-hour GOAT trial (or on whatever tier you have):

    export BDL_API_KEY="your_key_here"
    python3 probe_balldontlie.py

No third-party packages required (stdlib only).

What it does:
  1. Finds a completed match.
  2. Hits each relevant endpoint and reports HTTP status (200 ok / 401 gated).
  3. DISCOVERS the stat field names in team & player match-stats records
     (the docs don't list them all) and flags which of your metrics are present.
  4. Prints a coverage matrix for all 11 required stats.
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request

BASE = "https://api.balldontlie.io/fifa/worldcup/v1"
KEY = os.environ.get("BDL_API_KEY")

# Your dashboard's required metrics, grouped by the endpoint that should carry them.
# Each metric lists keyword(s) we search for in the discovered field names.
TEAM_FROM_STANDINGS = {
    "record (W-D-L)": ["won", "drawn", "lost"],
    "goals per game": ["goals_for", "played"],
    "allowed goals per game": ["goals_against", "played"],
    "goal difference per game": ["goal_difference", "played"],
}
TEAM_FROM_MATCH_STATS = {
    "total shots per game": ["shot"],          # e.g. shots / total_shots
    "shots on target per game": ["target", "on_goal"],
    "corners per game": ["corner"],
}
PLAYER_FROM_ROSTERS = {
    "goals per game": ["goals"],
    "assists per game": ["assists"],
}
PLAYER_FROM_MATCH_STATS = {
    "shots per game": ["shot"],
    "shots on goal per game": ["target", "on_goal"],
}


def get(path, params=None):
    """Return (status_code, parsed_json_or_None). Handles 401/429 cleanly."""
    url = BASE + path
    if params:
        # urlencode with doseq so seasons[]=2026 style repeats work
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={"Authorization": KEY})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt == 0:
                print("  ... rate limited (5 req/min on trial); waiting 15s")
                time.sleep(15)
                continue
            body = ""
            try:
                body = e.read().decode()[:160]
            except Exception:
                pass
            return e.code, {"error": body}
        except Exception as e:
            return None, {"error": str(e)}
    return None, None


def discover_fields(record, prefix=""):
    """Flatten a record's keys (one level into nested dicts) for keyword search."""
    keys = []
    for k, v in record.items():
        keys.append(k)
        if isinstance(v, dict):
            keys += [f"{k}.{ik}" for ik in v.keys()]
    return keys


def find_metric(keywords, available_keys):
    """Return the first field name matching ALL/ANY keyword logic."""
    hits = [k for k in available_keys if any(kw in k.lower() for kw in keywords)]
    return hits


def banner(t):
    print("\n" + "=" * 64 + f"\n  {t}\n" + "=" * 64)


def main():
    if not KEY:
        sys.exit("Set BDL_API_KEY first:  export BDL_API_KEY='your_key'")

    results = {}  # metric -> (status_str, detail)

    banner("1. Find a completed match")
    code, data = get("/matches", {"seasons[]": 2026, "per_page": 100})
    if code != 200:
        print(f"  /matches -> HTTP {code} (GOAT-tier endpoint). {data}")
        print("  Cannot locate a match id; match-stat checks will be skipped.")
        match = None
    else:
        completed = [m for m in data.get("data", []) if m.get("status") == "completed"]
        match = completed[0] if completed else None
        if match:
            h = (match.get("home_team") or {}).get("name", "?")
            a = (match.get("away_team") or {}).get("name", "?")
            print(f"  Using match id={match['id']}: {h} vs {a}")
        else:
            print("  No completed matches found yet in the data.")

    mid = match["id"] if match else None
    tid = (match.get("home_team") or {}).get("id") if match else None

    # ---- Team Match Stats (shots / shots on target / corners) ----
    banner("2. Team Match Stats  (shots, shots on target, corners)")
    tm_keys = []
    if mid:
        code, data = get("/team_match_stats", {"match_ids[]": mid})
        print(f"  /team_match_stats -> HTTP {code}")
        if code == 200 and data.get("data"):
            rec = data["data"][0]
            tm_keys = discover_fields(rec)
            print("  Available fields:", ", ".join(sorted(set(tm_keys))))
        elif code == 401:
            print("  GATED: your tier can't access Team Match Stats (needs GOAT).")
    for metric, kws in TEAM_FROM_MATCH_STATS.items():
        hits = find_metric(kws, tm_keys)
        results["TEAM: " + metric] = ("FOUND " + str(hits)) if hits else (
            "GATED/missing" if not tm_keys else "field not found")

    # ---- Player Match Stats (shots / shots on goal) ----
    banner("3. Player Match Stats  (shots, shots on goal)")
    pm_keys = []
    if mid:
        code, data = get("/player_match_stats", {"match_ids[]": mid})
        print(f"  /player_match_stats -> HTTP {code}")
        if code == 200 and data.get("data"):
            rec = data["data"][0]
            pm_keys = discover_fields(rec)
            print("  Available fields:", ", ".join(sorted(set(pm_keys))))
        elif code == 401:
            print("  GATED: your tier can't access Player Match Stats (needs GOAT).")
    for metric, kws in PLAYER_FROM_MATCH_STATS.items():
        hits = find_metric(kws, pm_keys)
        results["PLAYER: " + metric] = ("FOUND " + str(hits)) if hits else (
            "GATED/missing" if not pm_keys else "field not found")

    # ---- Group Standings (record, goals/g, allowed/g, GD/g) ----
    banner("4. Group Standings  (record, goals, allowed, goal diff)")
    gs_keys = []
    code, data = get("/group_standings", {"seasons[]": 2026})
    print(f"  /group_standings -> HTTP {code}")
    if code == 200 and data.get("data"):
        gs_keys = discover_fields(data["data"][0])
        print("  Available fields:", ", ".join(sorted(set(gs_keys))))
    elif code == 401:
        print("  GATED: needs ALL-STAR ($9.99) or higher.")
    for metric, kws in TEAM_FROM_STANDINGS.items():
        hits = [k for k in gs_keys if any(kw in k.lower() for kw in kws)]
        results["TEAM: " + metric] = ("FOUND " + str(hits)) if len(hits) >= 1 else (
            "GATED/missing" if not gs_keys else "field not found")

    # ---- Rosters (player goals / assists, cumulative) ----
    banner("5. Rosters  (player goals, assists)")
    rs_keys = []
    params = {"seasons[]": 2026}
    if tid:
        params["team_ids[]"] = tid
    code, data = get("/rosters", params)
    print(f"  /rosters -> HTTP {code}")
    if code == 200 and data.get("data"):
        rs_keys = discover_fields(data["data"][0])
        print("  Available fields:", ", ".join(sorted(set(rs_keys))))
    elif code == 401:
        print("  GATED: needs GOAT.")
    for metric, kws in PLAYER_FROM_ROSTERS.items():
        hits = [k for k in rs_keys if any(kw in k.lower() for kw in kws)]
        results["PLAYER: " + metric] = ("FOUND " + str(hits)) if hits else (
            "GATED/missing" if not rs_keys else "field not found")

    # ---- Coverage matrix ----
    banner("COVERAGE MATRIX  (your 11 required stats)")
    order = [
        "TEAM: record (W-D-L)", "TEAM: goals per game", "TEAM: allowed goals per game",
        "TEAM: goal difference per game", "TEAM: total shots per game",
        "TEAM: shots on target per game", "TEAM: corners per game",
        "PLAYER: goals per game", "PLAYER: assists per game",
        "PLAYER: shots per game", "PLAYER: shots on goal per game",
    ]
    ok = 0
    for m in order:
        status = results.get(m, "not checked")
        mark = "OK " if status.startswith("FOUND") else "-- "
        if status.startswith("FOUND"):
            ok += 1
        print(f"  [{mark}] {m:<34} {status}")
    print(f"\n  {ok}/11 metrics available on this key's tier.")
    print("  If shots/corners/player stats show GATED, you need GOAT ($39.99).")


if __name__ == "__main__":
    main()
