#!/usr/bin/env python3
"""
Validate public/data.json before it gets committed/published.

Run automatically by refresh.sh right after fetch_fbref.py. A single ERROR
aborts the commit, so a bad scrape can never overwrite the last good data.json.
WARNINGs are printed for human review but do not block.

    python3 validate.py [path/to/data.json]   # default: public/data.json
    exit 0 = clean (or warnings only) ; exit 1 = at least one ERROR

This covers the first three validation layers (see the project's validation
plan). Each catches a different class of bug; together they make most scrape
errors impossible to publish silently:

  Layer 1  Schema/structure  — right shape, types, codes, counts
  Layer 2  Invariants        — football's rules each row must obey
  Layer 3  Reconciliation    — the same fact in two tables must agree
  Layer 4  Temporal          — vs the last commit: totals only go up, sanely

The previous data.json is read from `git show HEAD:public/data.json` (or an
explicit `--prev <file>` for testing). On the first commit, or outside a git
repo, the temporal layer simply skips.

Layer 5 (cross-source vs ESPN, independent of Opta) lives in validate_external.py
— it is advisory/non-blocking, so it is deliberately kept out of this gating
script. Layer 6 (distributional anomaly flags) is still planned.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_PATH = Path("public/data.json")

# Column layout of each row in data.json (keep in sync with fetch_fbref.py).
TEAM_COLS = ["code", "name", "P", "W", "D", "L", "GF", "GA", "shots", "sot", "cor"]
PLAYER_COLS = ["name", "team", "pos", "P", "goals", "assists", "shots", "sog"]
TEAM_INTS = ["P", "W", "D", "L", "GF", "GA", "shots", "sot", "cor"]
PLAYER_INTS = ["P", "goals", "assists", "shots", "sog"]

MAX_TEAMS = 48          # 2026 World Cup field
MAX_TEAM_GAMES = 7      # group (3) + R32/R16/QF/SF/final = at most 7

# Layer 4 — cumulative season totals that must never decrease commit-to-commit.
TEAM_CUMULATIVE = ["P", "W", "D", "L", "GF", "GA", "shots", "sot", "cor"]
PLAYER_CUMULATIVE = ["P", "goals", "assists", "shots", "sog"]
# Generous per-added-game caps; a jump above this since the last commit is a
# spike worth a human look (WARN), not a hard block. dP==0 still allows one
# game's worth so a legitimate FBref correction doesn't trip the alarm.
TEAM_GROWTH_CAP = {"shots": 45, "sot": 25, "GF": 12, "GA": 12, "cor": 20}
PLAYER_GROWTH_CAP = {"shots": 15, "sog": 12, "goals": 7, "assists": 7}


class Report:
    """Collects ERROR/WARN findings keyed by check name; ERRORs block the commit."""

    def __init__(self):
        self.errors = []
        self.warns = []

    def error(self, check, msg):
        self.errors.append((check, msg))

    def warn(self, check, msg):
        self.warns.append((check, msg))

    def ok(self):
        return not self.errors

    def render(self):
        lines = []
        for check, msg in self.errors:
            lines.append(f"  ERROR [{check}] {msg}")
        for check, msg in self.warns:
            lines.append(f"  WARN  [{check}] {msg}")
        return "\n".join(lines)


# ----------------------------------------------------------------------------
# Layer 1 — schema & structure
# ----------------------------------------------------------------------------
def check_schema(data, rep):
    for key in ("updated", "matchday", "teams", "players"):
        if key not in data:
            rep.error("schema", f"missing top-level key: {key!r}")

    if "updated" in data:
        try:
            datetime.fromisoformat(str(data["updated"]).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            rep.error("schema", f"'updated' is not an ISO timestamp: {data['updated']!r}")

    if not isinstance(data.get("matchday"), int):
        rep.error("schema", "'matchday' must be an int")

    teams = data.get("teams")
    players = data.get("players")
    if not isinstance(teams, list) or not teams:
        rep.error("schema", "'teams' must be a non-empty list")
        teams = []
    if not isinstance(players, list) or not players:
        rep.error("schema", "'players' must be a non-empty list")
        players = []

    if len(teams) > MAX_TEAMS:
        rep.error("schema", f"{len(teams)} teams (> {MAX_TEAMS} in the field)")

    seen_codes = set()
    for i, t in enumerate(teams):
        if not isinstance(t, list) or len(t) != len(TEAM_COLS):
            rep.error("schema", f"team row {i} has {len(t) if isinstance(t, list) else '?'} "
                                f"cols, expected {len(TEAM_COLS)}")
            continue
        row = dict(zip(TEAM_COLS, t))
        if not isinstance(row["code"], str) or not row["code"] or row["code"] == "UNK":
            rep.error("schema", f"team row {i} has a bad code: {row['code']!r}")
        elif row["code"] in seen_codes:
            rep.error("schema", f"duplicate team code: {row['code']!r}")
        else:
            seen_codes.add(row["code"])
        if not isinstance(row["name"], str) or not row["name"]:
            rep.error("schema", f"team row {i} has an empty name")
        elif row["name"].lower().startswith("vs "):
            rep.error("schema", f"team row {i} is an opponent ('vs') row: {row['name']!r}")
        for col in TEAM_INTS:
            if not isinstance(row[col], int):
                rep.error("schema", f"team {row.get('code', i)} field {col} not an int: {row[col]!r}")

    seen_players = set()
    for i, p in enumerate(players):
        if not isinstance(p, list) or len(p) != len(PLAYER_COLS):
            rep.error("schema", f"player row {i} has {len(p) if isinstance(p, list) else '?'} "
                                f"cols, expected {len(PLAYER_COLS)}")
            continue
        row = dict(zip(PLAYER_COLS, p))
        if not isinstance(row["name"], str) or not row["name"]:
            rep.error("schema", f"player row {i} has an empty name")
        if not isinstance(row["team"], str) or not row["team"]:
            rep.error("schema", f"player {row.get('name', i)} has an empty team code")
        key = (row.get("name"), row.get("team"))
        if key in seen_players:
            rep.warn("schema", f"duplicate player row: {key}")
        seen_players.add(key)
        for col in PLAYER_INTS:
            if not isinstance(row[col], int):
                rep.error("schema", f"player {row.get('name', i)} field {col} not an int: {row[col]!r}")


# ----------------------------------------------------------------------------
# Layer 2 — invariants (football's rules each row must obey)
# ----------------------------------------------------------------------------
def check_invariants(teams, players, rep):
    for t in teams:
        code = t["code"]
        if any(t[c] < 0 for c in TEAM_INTS):
            rep.error("invariant", f"{code}: negative count in {[(c, t[c]) for c in TEAM_INTS if t[c] < 0]}")
        if t["P"] != t["W"] + t["D"] + t["L"]:
            rep.error("invariant", f"{code}: P={t['P']} != W+D+L={t['W'] + t['D'] + t['L']}")
        if t["P"] > MAX_TEAM_GAMES:
            rep.error("invariant", f"{code}: P={t['P']} exceeds max {MAX_TEAM_GAMES} games")
        if t["sot"] > t["shots"]:
            rep.error("invariant", f"{code}: shots on target {t['sot']} > total shots {t['shots']}")

    team_P = {t["code"]: t["P"] for t in teams}
    for p in players:
        name, code = p["name"], p["team"]
        if any(p[c] < 0 for c in PLAYER_INTS):
            rep.error("invariant", f"{name} ({code}): negative count")
        # A goal is on target by definition, and a shot on target is a shot.
        if not (p["goals"] <= p["sog"] <= p["shots"]):
            rep.error("invariant",
                      f"{name} ({code}): violates goals({p['goals']}) <= "
                      f"sog({p['sog']}) <= shots({p['shots']})")
        if code in team_P and p["P"] > team_P[code]:
            rep.error("invariant",
                      f"{name} ({code}): player games {p['P']} > team games {team_P[code]}")


# ----------------------------------------------------------------------------
# Layer 3 — cross-table reconciliation (the same fact, two places, must agree)
# ----------------------------------------------------------------------------
def _sum_by_team(players, field):
    out = {}
    for p in players:
        out[p["team"]] = out.get(p["team"], 0) + p[field]
    return out


def check_reconciliation(teams, players, matchday, rep):
    by_code = {t["code"]: t for t in teams}

    # Every player's team must exist as a team row.
    for p in players:
        if p["team"] not in by_code:
            rep.error("reconcile", f"player {p['name']} has team code {p['team']!r} with no team row")

    # Sum of player shots / shots-on-goal per team must equal the team total.
    # (These come from the same FBref shooting page, so a mismatch means a row
    # was mis-parsed or a player's name didn't join across the two tables.)
    pshots = _sum_by_team(players, "shots")
    psog = _sum_by_team(players, "sog")
    # ESPN reports team shot totals and per-player shots from different parts of
    # the feed, so they legitimately differ by a shot or two (unattributed /
    # revised shots). Tolerate that small gap; a large one is still a real parse
    # bug (e.g. the wrong table, or half the roster dropped).
    def _far(a, b):
        return abs(a - b) > max(2, 0.10 * max(a, b))

    for code, t in by_code.items():
        if code in pshots and _far(pshots[code], t["shots"]):
            rep.error("reconcile",
                      f"{code}: sum of player shots {pshots[code]} vs team shots {t['shots']} "
                      f"(beyond tolerance)")
        if code in psog and _far(psog[code], t["sot"]):
            rep.error("reconcile",
                      f"{code}: sum of player SoG {psog[code]} vs team SoT {t['sot']} "
                      f"(beyond tolerance)")

    # Sum of player goals per team cannot exceed team goals-for (the gap is own
    # goals, which are credited to the team but to no player).
    pgoals = _sum_by_team(players, "goals")
    for code, g in pgoals.items():
        if code in by_code and g > by_code[code]["GF"]:
            rep.error("reconcile",
                      f"{code}: sum of player goals {g} > team goals-for {by_code[code]['GF']}")

    # Global goal conservation: every goal scored is a goal conceded by someone.
    gf, ga = sum(t["GF"] for t in teams), sum(t["GA"] for t in teams)
    if gf != ga:
        rep.error("reconcile", f"total goals-for {gf} != total goals-against {ga} across all teams")

    # Each match contributes two team-appearances, so the sum of games is even.
    total_P = sum(t["P"] for t in teams)
    if total_P % 2 != 0:
        rep.error("reconcile", f"sum of team games {total_P} is odd (a match is missing a side)")

    # matchday should be the furthest any team has progressed.
    max_P = max((t["P"] for t in teams), default=0)
    if matchday != max_P:
        rep.warn("reconcile", f"matchday {matchday} != max team games {max_P}")


# ----------------------------------------------------------------------------
# Layer 4 — temporal monotonicity (vs the previously committed data.json)
# ----------------------------------------------------------------------------
def _index(rows, cols, key):
    """{key_value: row_dict} for rows shaped like cols; skips malformed rows."""
    out = {}
    for r in rows:
        if isinstance(r, list) and len(r) == len(cols):
            d = dict(zip(cols, r))
            out[key(d)] = d
    return out


def check_temporal(prev, cur_teams, cur_players, rep):
    """Compare against the last commit: cumulative totals only ever grow, and
    not by an implausible amount; teams/players don't silently vanish.

    Targets the stale/regressed-scrape class (e.g. commit 285987a) where a page
    lagged and totals went backwards or a row dropped out."""
    try:
        prev_teams = _index(prev.get("teams", []), TEAM_COLS, lambda d: d["code"])
        prev_players = _index(prev.get("players", []), PLAYER_COLS,
                              lambda d: (d["name"], d["team"]))
    except Exception:
        rep.warn("temporal", "previous data.json unreadable; skipping temporal checks")
        return

    cur_teams_ix = {t["code"]: t for t in cur_teams}
    cur_players_ix = {(p["name"], p["team"]): p for p in cur_players}

    def compare(prev_row, cur_row, fields, caps, label, hard_drop):
        dP = cur_row["P"] - prev_row["P"]
        for f in fields:
            drop = prev_row[f] - cur_row[f]
            if drop <= 0:
                continue
            # ESPN revises live stats, so a small dip (a goal reattributed, a shot
            # recounted) is expected and only worth a WARN. A big drop is the
            # stale/partial-scrape regression we actually want to block on.
            if hard_drop is not None and drop > hard_drop(prev_row[f]):
                rep.error("temporal",
                          f"{label}: {f} dropped {prev_row[f]} -> {cur_row[f]} "
                          f"(large regression)")
            else:
                rep.warn("temporal", f"{label}: {f} revised {prev_row[f]} -> {cur_row[f]}")
        for f, per_game in caps.items():
            growth = cur_row[f] - prev_row[f]
            cap = per_game * max(dP, 1)
            if growth > cap:
                rep.warn("temporal",
                         f"{label}: {f} jumped +{growth} since last commit over "
                         f"{dP} new game(s) (cap {cap})")

    # Teams block on a real regression (drop beyond max(3, 10%)); individual
    # player dips are advisory only (never block on one athlete's revision).
    team_hard = lambda prev: max(3, 0.10 * prev)

    # A large fall in roster size is itself a partial-scrape signal.
    if len(cur_players) < 0.85 * len(prev_players):
        rep.error("temporal", f"player count fell {len(prev_players)} -> {len(cur_players)} "
                              f"(partial scrape?)")

    # Teams: a missing team is a partial scrape (standings rows persist all tournament).
    missing_teams = set()
    for code, prev_t in prev_teams.items():
        cur_t = cur_teams_ix.get(code)
        if cur_t is None:
            missing_teams.add(code)
            rep.error("temporal", f"team {code} was present last commit but is now missing")
        else:
            compare(prev_t, cur_t, TEAM_CUMULATIVE, TEAM_GROWTH_CAP, f"team {code}", team_hard)

    # Players: vanishing is suspicious but not a hard block (rosters/filters shift).
    # Skip players whose whole team already flagged missing — that's one bug, not N.
    for key, prev_p in prev_players.items():
        if key[1] in missing_teams:
            continue
        cur_p = cur_players_ix.get(key)
        if cur_p is None:
            rep.warn("temporal", f"player {key[0]} ({key[1]}) dropped out since last commit")
        else:
            compare(prev_p, cur_p, PLAYER_CUMULATIVE, PLAYER_GROWTH_CAP,
                    f"{key[0]} ({key[1]})", hard_drop=None)


def load_previous(path):
    """Previous data.json: from `--prev <file>` if given, else `git show HEAD:`.
    Returns None (skip temporal) on the first commit or outside a git repo."""
    if "--prev" in sys.argv:
        return json.loads(Path(sys.argv[sys.argv.index("--prev") + 1]).read_text())
    try:
        out = subprocess.run(["git", "show", f"HEAD:{path.as_posix()}"],
                             capture_output=True, text=True)
        return json.loads(out.stdout) if out.returncode == 0 else None
    except (OSError, json.JSONDecodeError):
        return None


# ----------------------------------------------------------------------------
# Layer 3b — per-match splits must sum to the season totals (guards the games
# block that powers the game-by-game dropdowns). Season totals ARE the sum of
# these rows, so any mismatch is a pipeline bug, not a rounding difference.
# ----------------------------------------------------------------------------
def check_games(data, teams, players, rep):
    games = data.get("games")
    if not games:
        return
    gt = games.get("teams", {})
    for t in teams:
        rows = gt.get(t["code"])
        if rows is None:
            rep.error("games", f"{t['code']}: no per-match rows but P={t['P']}")
            continue
        if len(rows) != t["P"]:
            rep.error("games", f"{t['code']}: {len(rows)} game rows != P {t['P']}")
        for i, col in ((3, "GF"), (4, "GA"), (5, "shots"), (6, "sot"), (7, "cor")):
            s = sum(g[i] for g in rows)
            if s != t[col]:
                rep.error("games", f"{t['code']}: per-match {col} sum {s} != season {t[col]}")

    gp = games.get("players", {})
    for p in players:
        splits = gp.get(p["team"], {}).get(p["name"])
        if not splits:
            continue  # missing splits are advisory; a name-join gap, not a total error
        for i, col in ((0, "goals"), (1, "assists"), (2, "shots"), (3, "sog")):
            s = sum(v[i] for v in splits.values())
            if s != p[col]:
                rep.error("games",
                          f"{p['name']} ({p['team']}): per-match {col} sum {s} != season {p[col]}")


def validate(data, prev=None):
    rep = Report()
    check_schema(data, rep)
    # Only run value-level checks if the structure is sound enough to trust.
    if rep.ok():
        teams = [dict(zip(TEAM_COLS, t)) for t in data["teams"]]
        players = [dict(zip(PLAYER_COLS, p)) for p in data["players"]]
        check_invariants(teams, players, rep)
        check_reconciliation(teams, players, data["matchday"], rep)
        check_games(data, teams, players, rep)
        if prev is not None:
            check_temporal(prev, teams, players, rep)
    return rep


def main():
    args = [a for a in sys.argv[1:] if a != "--prev"]
    # First non-flag arg is the data file; the value after --prev (if any) is
    # consumed by load_previous, so drop it from the positional list.
    if "--prev" in sys.argv:
        prev_val = sys.argv[sys.argv.index("--prev") + 1]
        args = [a for a in args if a != prev_val]
    path = Path(args[0]) if args else DEFAULT_PATH
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        print(f"FAIL: cannot read {path}: {e}", file=sys.stderr)
        sys.exit(1)

    prev = load_previous(path)
    if prev is None and "--prev" not in sys.argv:
        print("note: no previous commit of this file; skipping temporal checks",
              file=sys.stderr)
    rep = validate(data, prev)
    out = rep.render()
    if out:
        print(out, file=sys.stderr)

    n_err, n_warn = len(rep.errors), len(rep.warns)
    if rep.ok():
        msg = f"OK: {path} passed validation"
        if n_warn:
            msg += f" with {n_warn} warning(s)"
        print(msg)
        sys.exit(0)
    else:
        print(f"\nFAIL: {n_err} error(s), {n_warn} warning(s). "
              f"Refusing to publish {path}.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
