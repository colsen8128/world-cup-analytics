#!/usr/bin/env python3
"""
Layer 5 — cross-source audit: ESPN data.json (primary) vs FBref (second opinion).

Since the flip to ESPN as source of truth, FBref plays the validator. When FBref
has caught up it should agree with ESPN, which is your confidence signal. When it
lags a match — its Opta-fed competition pages update hours after kickoff — that is
EXPECTED and reported as "behind", not a discrepancy. A real disagreement at the
same game count (a goal or shot count that differs) is what's worth a look.

LOCAL ONLY and NON-BLOCKING. FBref/Cloudflare blocks datacenter IPs, so this can't
run in CI — run it from your Mac. It never fails the pipeline: it writes
validation_external.txt and always exits 0. If FBref is unreachable, it skips.

    python3 validate_external.py [espn_data.json]   # default: public/data.json
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from fetch_espn import norm_name

TEAM_COLS = ["code", "name", "P", "W", "D", "L", "GF", "GA", "shots", "sot", "cor"]
PLAYER_COLS = ["name", "team", "pos", "P", "goals", "assists", "shots", "sog"]
TOL_ABS, TOL_REL = 2, 0.15     # providers differ a little on shots/SoT counting


def _tolerant(a, b):
    return abs(a - b) > max(TOL_ABS, TOL_REL * max(abs(a), abs(b)))


def fbref_snapshot():
    """Run fetch_fbref.py to a temp file; return its parsed data, or None if FBref
    is unreachable (blocked IP / no venv / scrape failure)."""
    py = "venv/bin/python" if Path("venv/bin/python").exists() else sys.executable
    tmp = Path(tempfile.mkdtemp()) / "fbref.json"
    try:
        r = subprocess.run([py, "fetch_fbref.py", str(tmp)],
                           capture_output=True, text=True, timeout=900)
    except Exception as e:
        print(f"skip: could not run fetch_fbref.py ({e})")
        return None
    if r.returncode != 0 or not tmp.exists():
        tail = (r.stderr.strip().splitlines() or ["(no output)"])[-1]
        print(f"skip: FBref fetch failed (blocked IP / no venv?): {tail}")
        return None
    return json.loads(tmp.read_text())


def audit(espn, fb):
    lines, behind, unmatched = [], set(), 0
    fb_teams = {t[0]: dict(zip(TEAM_COLS, t)) for t in fb["teams"]}

    # ---- Teams ----------------------------------------------------------------
    for row in espn["teams"]:
        e = dict(zip(TEAM_COLS, row))
        f = fb_teams.get(e["code"])
        if not f:
            lines.append(f"TEAM {e['code']}: not in FBref yet")
            continue
        if f["P"] < e["P"]:                       # expected: FBref trailing live
            behind.add(e["code"])
            lines.append(f"TEAM {e['code']} BEHIND: FBref {f['P']}g vs ESPN {e['P']}g "
                         f"(FBref catching up — players suppressed)")
            continue
        if f["P"] > e["P"]:                        # unexpected: ESPN would be stale
            lines.append(f"TEAM {e['code']}: FBref {f['P']}g AHEAD of ESPN {e['P']}g (unexpected)")
            continue
        for k in ("W", "D", "L", "GF", "GA"):     # same game count -> exact
            if e[k] != f[k]:
                lines.append(f"TEAM {e['code']} {k}: ESPN {e[k]} vs FBref {f[k]}")
        for k in ("shots", "sot"):                # tolerant
            if _tolerant(e[k], f[k]):
                lines.append(f"TEAM {e['code']} {k}: ESPN {e[k]} vs FBref {f[k]}")

    # ---- Players (skip teams FBref hasn't caught up on) ------------------------
    fb_players = {(norm_name(p[0]), p[1]): dict(zip(PLAYER_COLS, p)) for p in fb["players"]}
    for row in espn["players"]:
        e = dict(zip(PLAYER_COLS, row))
        if e["team"] in behind:
            continue
        f = fb_players.get((norm_name(e["name"]), e["team"]))
        if not f:
            if e["goals"] or e["shots"] >= 3:     # only surface players with real stats
                lines.append(f"PLAYER {e['name']} ({e['team']}): not in FBref (name diff / lag?)")
            unmatched += 1
            continue
        for k in ("P", "goals", "assists"):       # exact
            if e[k] != f[k]:
                lines.append(f"PLAYER {e['name']} ({e['team']}) {k}: ESPN {e[k]} vs FBref {f[k]}")
        for k in ("shots", "sog"):                # tolerant
            if _tolerant(e[k], f[k]):
                lines.append(f"PLAYER {e['name']} ({e['team']}) {k}: ESPN {e[k]} vs FBref {f[k]}")

    return lines, behind, unmatched


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("public/data.json")
    espn = json.loads(path.read_text())

    print("Fetching FBref snapshot for cross-check (local only) ...")
    fb = fbref_snapshot()
    if fb is None:
        print("Cross-check skipped; nothing written.")
        sys.exit(0)

    lines, behind, unmatched = audit(espn, fb)
    report = Path("validation_external.txt")
    note = f" {len(behind)} team(s) still behind in FBref." if behind else ""
    header = (f"External validation (ESPN data.json vs FBref second opinion)\n"
              f"  {len(espn['teams'])} teams, {len(espn['players'])} players checked; "
              f"{unmatched} player(s) unmatched in FBref.{note}\n")
    body = "\n".join(f"  {l}" for l in lines) if lines else "  Full agreement (within tolerance)."
    report.write_text(header + body + "\n")
    print(header + body)
    print(f"\n{len(lines)} line(s). Report -> {report}. (Advisory only — does not block.)")
    sys.exit(0)


if __name__ == "__main__":
    main()
