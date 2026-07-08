/* Golden test for the UI derivation math (src/derive.js).
 *
 * This is the "is the SITE showing the right thing" guarantee. validate.py
 * checks the DATA is right; this checks a correct data.json renders to the
 * right per-game numbers. Run with:  npm test   (node --test)
 *
 * No framework/deps — Node's built-in node:test + node:assert.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { deriveData } from "../src/derive.js";

const RAW = {
  updated: "2026-06-24T00:00:00Z",
  matchday: 2,
  teams: [
    // code, name, P, W, D, L, GF, GA, shots, sot, cor
    ["ARG", "Argentina", 2, 2, 0, 0, 5, 1, 22, 11, 9],
    ["NEW", "Newcomer", 0, 0, 0, 0, 0, 0, 0, 0, 0], // 0-game: must not divide by zero
  ],
  players: [
    // name, teamCode, pos, P, goals, assists, shots, sog
    ["Lionel Messi", "ARG", "FW", 2, 5, 0, 13, 8],
    ["Unknown Guy", "XYZ", "MF", 1, 0, 1, 2, 1], // team code with no team row
  ],
};

test("team per-game math is exact", () => {
  const { teams } = deriveData(RAW);
  const arg = teams.find((t) => t.code === "ARG");
  assert.equal(arg.pts, 6);          // 3W + D
  assert.equal(arg.gpg, 2.5);        // 5 / 2
  assert.equal(arg.apg, 0.5);        // 1 / 2
  assert.equal(arg.gdpg, 2.0);       // (5 - 1) / 2
  assert.equal(arg.spg, 11);         // 22 / 2
  assert.equal(arg.sotpg, 5.5);      // 11 / 2
  assert.equal(arg.cpg, 4.5);        // 9 / 2
});

test("player per-game math is exact (the Messi 6.5 case)", () => {
  const { players } = deriveData(RAW);
  const messi = players.find((p) => p.name === "Lionel Messi");
  assert.equal(messi.gpg, 2.5);      // 5 / 2
  assert.equal(messi.apg, 0);        // 0 / 2
  assert.equal(messi.shpg, 6.5);     // 13 / 2  <-- the number in question
  assert.equal(messi.sogpg, 4.0);    // 8 / 2
  assert.equal(messi.teamName, "Argentina"); // code resolves to full name
});

test("zero games never produces NaN or Infinity", () => {
  const { teams } = deriveData(RAW);
  const nw = teams.find((t) => t.code === "NEW");
  for (const k of ["gpg", "apg", "gdpg", "spg", "sotpg", "cpg"]) {
    assert.equal(nw[k], 0, `${k} should be 0 for a 0-game team`);
    assert.ok(Number.isFinite(nw[k]), `${k} must be finite`);
  }
});

test("unknown team code falls back to the code itself", () => {
  const { players } = deriveData(RAW);
  const p = players.find((p) => p.name === "Unknown Guy");
  assert.equal(p.teamName, "XYZ");
});
