/* ------------------------------------------------------------------ *
 *  DERIVATION LAYER
 *  ---------------
 *  Turns the RAW totals in data.json into the per-game numbers the UI
 *  shows. Kept in its own module (not inside Dashboard.jsx) so it can be
 *  unit-tested in isolation — see test/derive.test.mjs. This is the
 *  "is the SITE showing the right thing" guarantee, separate from
 *  "is the DATA right" (validate.py). A division bug here would make a
 *  correct data.json render wrong, so the golden test pins the math.
 *
 *  RAW shape:
 *    teams:   [code, name, P, W, D, L, GF, GA, shots, sot, cor]
 *    players: [name, teamCode, pos, P, goals, assists, shots, sog]
 * ------------------------------------------------------------------ */
export function deriveData(RAW) {
  const teams = RAW.teams.map(([code, name, P, W, D, L, GF, GA, shots, sot, cor, sa = 0, sota = 0]) => {
    const pts = W * 3 + D;
    const per = (n) => (P > 0 ? n / P : 0); // avoid NaN/Infinity for 0-game teams
    return {
      code, name, P, W, D, L, GF, GA, shots, sot, cor, sa, sota, pts,
      gpg: per(GF),           // goals per game
      apg: per(GA),           // allowed goals per game
      gdpg: per(GF - GA),     // goal difference per game
      spg: per(shots),        // total shots per game
      sotpg: per(sot),        // shots on target per game
      sapg: per(sa),          // shots against per game
      sotapg: per(sota),      // shots on target against per game
      cpg: per(cor),          // corners per game
    };
  });
  const teamByCode = Object.fromEntries(teams.map((t) => [t.code, t]));
  const players = RAW.players.map(([name, team, pos, P, G, A, sh, sog]) => {
    const per = (n) => (P > 0 ? n / P : 0);
    return {
      name, team, pos, P, G, A, sh, sog,
      gpg: per(G),     // goals per game
      apg: per(A),     // assists per game
      shpg: per(sh),   // shots per game
      sogpg: per(sog), // shots on goal per game
      teamName: teamByCode[team]?.name ?? team,
    };
  });
  // Per-match splits for the game-by-game dropdowns (optional; older data.json
  // predates it). Passed through untouched.
  const games = RAW.games ?? { teams: {}, players: {} };
  return { updated: RAW.updated, matchday: RAW.matchday, teams, players, games };
}
