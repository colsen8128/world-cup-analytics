import { useState, useMemo, useEffect, Fragment } from "react";
import { deriveData } from "./derive.js";

/* ------------------------------------------------------------------ *
 *  DATA LAYER
 *  ---------
 *  Everything below comes from a single object shaped like the
 *  data.json your scheduled job writes at the end of each match day.
 *  To go live, replace getData() with a fetch:
 *
 *      const [data, setData] = useState(null);
 *      useEffect(() => {
 *        fetch("./data.json").then(r => r.json()).then(setData);
 *      }, []);
 *
 *  Store RAW TOTALS per team/player; per-game stats are derived in the
 *  UI (see useMemo blocks). That keeps the pipeline dumb and the math
 *  in one place. Numbers below are illustrative sample data.
 * ------------------------------------------------------------------ */

const SAMPLE = {
  updated: "2026-06-22T03:10:00Z",
  matchday: 3,
  teams: [
    // code, name, played, W, D, L, GF, GA, shots, sot (on target), corners
    ["ARG", "Argentina", 3, 3, 0, 0, 8, 2, 47, 22, 19],
    ["FRA", "France", 3, 2, 1, 0, 7, 3, 51, 20, 21],
    ["BRA", "Brazil", 3, 2, 1, 0, 6, 2, 49, 19, 24],
    ["ESP", "Spain", 3, 2, 1, 0, 7, 4, 55, 23, 27],
    ["ENG", "England", 3, 2, 0, 1, 5, 3, 44, 17, 18],
    ["POR", "Portugal", 3, 2, 0, 1, 6, 4, 46, 18, 20],
    ["NED", "Netherlands", 3, 1, 2, 0, 5, 3, 41, 15, 17],
    ["GER", "Germany", 3, 1, 1, 1, 4, 4, 48, 16, 22],
    ["USA", "United States", 3, 1, 1, 1, 4, 4, 38, 14, 15],
    ["CRO", "Croatia", 3, 1, 1, 1, 3, 3, 36, 12, 14],
    ["MEX", "Mexico", 3, 1, 1, 1, 3, 4, 34, 11, 13],
    ["JPN", "Japan", 3, 1, 0, 2, 3, 5, 33, 12, 12],
    ["MAR", "Morocco", 3, 1, 0, 2, 2, 4, 31, 10, 11],
    ["CAN", "Canada", 3, 0, 2, 1, 2, 4, 29, 9, 10],
    ["SEN", "Senegal", 3, 0, 1, 2, 2, 6, 27, 8, 9],
    ["KSA", "Saudi Arabia", 3, 0, 1, 2, 1, 7, 22, 6, 7],
  ],
  players: [
    // name, teamCode, pos, played, goals, assists, shots, sog (shots on goal)
    ["L. Messi", "ARG", "FW", 3, 4, 3, 16, 9],
    ["J. Álvarez", "ARG", "FW", 3, 3, 1, 13, 7],
    ["K. Mbappé", "FRA", "FW", 3, 4, 2, 18, 10],
    ["O. Dembélé", "FRA", "FW", 3, 1, 3, 11, 5],
    ["Vinícius Jr.", "BRA", "FW", 3, 3, 2, 15, 8],
    ["Rodrygo", "BRA", "FW", 3, 2, 2, 12, 6],
    ["L. Yamal", "ESP", "FW", 3, 2, 4, 14, 7],
    ["Á. Morata", "ESP", "FW", 3, 3, 0, 13, 8],
    ["H. Kane", "ENG", "FW", 3, 3, 1, 15, 9],
    ["B. Saka", "ENG", "FW", 3, 1, 2, 10, 5],
    ["C. Ronaldo", "POR", "FW", 3, 3, 0, 14, 7],
    ["B. Fernandes", "POR", "MF", 3, 1, 3, 9, 4],
    ["C. Gakpo", "NED", "FW", 3, 2, 1, 11, 6],
    ["J. Musiala", "GER", "MF", 3, 2, 2, 12, 6],
    ["K. Havertz", "GER", "FW", 3, 1, 1, 9, 4],
    ["C. Pulisic", "USA", "FW", 3, 2, 1, 11, 5],
    ["W. McKennie", "USA", "MF", 3, 1, 1, 7, 3],
    ["L. Modrić", "CRO", "MF", 3, 1, 2, 8, 3],
    ["S. Giménez", "MEX", "FW", 3, 1, 1, 9, 4],
    ["K. Mitoma", "JPN", "FW", 3, 2, 0, 10, 5],
    ["A. Hakimi", "MAR", "DF", 3, 1, 1, 6, 3],
    ["A. Davies", "CAN", "DF", 3, 0, 2, 5, 2],
    ["S. Mané", "SEN", "FW", 3, 1, 0, 8, 3],
    ["N. Williams", "ESP", "FW", 3, 2, 1, 12, 6],
    ["F. Wirtz", "GER", "MF", 3, 1, 2, 9, 4],
    ["P. Foden", "ENG", "MF", 3, 1, 1, 8, 4],
    ["Raphinha", "BRA", "FW", 3, 1, 2, 10, 5],
    ["A. Griezmann", "FRA", "FW", 3, 1, 2, 9, 4],
  ],
};

/* ------------------------------------------------------------------ *
 *  STYLES — floodlit-night broadcast palette
 * ------------------------------------------------------------------ */
const CSS = `
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=Inter:wght@400;500;600;700&display=swap');

.wc {
  --base:#0C1320; --surface:#131C2E; --surface2:#0F1726;
  --line:#233148; --line2:#2E3F5A;
  --text:#EAF0F8; --muted:#8595AD; --muted2:#5E6E89;
  --gold:#F5B945; --blue:#4DA3FF; --pos:#46C98B; --neg:#F2647A;
  background:var(--base); color:var(--text);
  font-family:'Inter',system-ui,sans-serif;
  min-height:100vh; line-height:1.4;
}
.wc *{box-sizing:border-box;}
.wc .cond{font-family:'Barlow Condensed','Inter',sans-serif;}
.wc .tnum{font-variant-numeric:tabular-nums;}

.wc .nav{position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:24px;
  padding:14px 28px;background:rgba(12,19,32,.86);backdrop-filter:blur(10px);
  border-bottom:1px solid var(--line);}
.wc .brand{font-family:'Barlow Condensed';font-weight:700;font-size:26px;letter-spacing:.04em;
  text-transform:uppercase;display:flex;align-items:baseline;gap:8px;}
.wc .brand .yr{color:var(--gold);}
.wc .navspace{flex:1;}
.wc .tab{appearance:none;background:none;border:none;cursor:pointer;color:var(--muted);
  font-family:'Barlow Condensed';font-weight:600;font-size:17px;letter-spacing:.05em;
  text-transform:uppercase;padding:6px 2px;position:relative;}
.wc .tab:hover{color:var(--text);}
.wc .tab.on{color:var(--text);}
.wc .tab.on::after{content:"";position:absolute;left:0;right:0;bottom:-15px;height:2px;background:var(--gold);}
.wc .tab:focus-visible{outline:2px solid var(--blue);outline-offset:3px;border-radius:2px;}
.wc .stamp{font-size:11px;color:var(--muted2);text-align:right;letter-spacing:.02em;}
.wc .stamp b{color:var(--muted);font-weight:600;}

.wc .wrap{max-width:1180px;margin:0 auto;padding:32px 28px 64px;}
.wc .hero .eyebrow{font-family:'Barlow Condensed';font-weight:600;letter-spacing:.18em;
  text-transform:uppercase;color:var(--gold);font-size:13px;}
.wc .hero h1{font-family:'Barlow Condensed';font-weight:700;text-transform:uppercase;
  font-size:clamp(34px,6vw,58px);line-height:.95;margin:6px 0 0;letter-spacing:.01em;}
.wc .hero p{color:var(--muted);max-width:560px;margin:12px 0 0;font-size:15px;}

.wc .sechead{display:flex;align-items:baseline;gap:14px;margin:44px 0 18px;}
.wc .sechead h2{font-family:'Barlow Condensed';font-weight:700;text-transform:uppercase;
  font-size:24px;letter-spacing:.04em;margin:0;}
.wc .sechead .rule{flex:1;height:1px;background:var(--line);}
.wc .sechead .kick{color:var(--blue);font-family:'Barlow Condensed';font-weight:600;
  font-size:13px;letter-spacing:.14em;text-transform:uppercase;}

.wc .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(248px,1fr));gap:16px;}
.wc .card{background:var(--surface);border:1px solid var(--line);border-radius:12px;
  padding:16px 16px 12px;}
.wc .card .ch{display:flex;align-items:baseline;justify-content:space-between;
  margin-bottom:12px;padding-bottom:10px;border-bottom:1px solid var(--line);}
.wc .card .ch .t{font-family:'Barlow Condensed';font-weight:600;font-size:16px;
  text-transform:uppercase;letter-spacing:.03em;}
.wc .card .ch .u{font-size:10px;color:var(--muted2);text-transform:uppercase;letter-spacing:.08em;}

.wc .row{display:grid;grid-template-columns:18px 1fr auto;align-items:center;gap:10px;
  padding:7px 0;}
.wc .row .rk{font-family:'Barlow Condensed';font-weight:700;font-size:15px;color:var(--muted2);text-align:center;}
.wc .row.first .rk{color:var(--gold);}
.wc .row .nm{font-size:13px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.wc .row .nm .sub{color:var(--muted2);font-size:11px;margin-left:6px;}
.wc .row .vw{display:flex;flex-direction:column;align-items:flex-end;gap:4px;min-width:74px;}
.wc .row .val{font-family:'Barlow Condensed';font-weight:700;font-size:17px;}
.wc .row.first .val{color:var(--gold);}
.wc .bar{width:72px;height:4px;background:var(--surface2);border-radius:3px;overflow:hidden;}
.wc .bar i{display:block;height:100%;background:var(--blue);border-radius:3px;}
.wc .row.first .bar i{background:var(--gold);}

.wc .panel{background:var(--surface);border:1px solid var(--line);border-radius:14px;overflow:hidden;}
.wc .tblscroll{overflow-x:auto;}
.wc table{width:100%;border-collapse:collapse;min-width:680px;}
.wc thead th{font-family:'Barlow Condensed';font-weight:600;text-transform:uppercase;
  letter-spacing:.04em;font-size:13px;color:var(--muted);text-align:right;
  padding:13px 14px;border-bottom:1px solid var(--line2);cursor:pointer;user-select:none;
  white-space:nowrap;background:var(--surface2);}
.wc thead th:first-child,.wc tbody td:first-child{text-align:left;position:sticky;left:0;
  background:var(--surface);}
.wc thead th:first-child{background:var(--surface2);}
.wc thead th.on{color:var(--gold);}
.wc thead th .ar{font-size:10px;margin-left:4px;}
.wc thead th:focus-visible{outline:2px solid var(--blue);outline-offset:-2px;}
.wc tbody td{padding:11px 14px;text-align:right;font-size:14px;border-bottom:1px solid var(--line);
  white-space:nowrap;}
.wc tbody tr:last-child td{border-bottom:none;}
.wc tbody tr:hover td{background:rgba(77,163,255,.06);}
.wc tbody tr:hover td:first-child{background:#16213422;}
.wc .team-cell{display:flex;align-items:center;gap:10px;font-weight:600;}
.wc .badge{font-family:'Barlow Condensed';font-weight:700;font-size:11px;letter-spacing:.04em;
  color:var(--base);background:var(--blue);border-radius:4px;padding:2px 6px;min-width:38px;text-align:center;}
.wc .rec{font-variant-numeric:tabular-nums;color:var(--muted);font-size:13px;}
.wc .pos{color:var(--pos);} .wc .neg{color:var(--neg);}
.wc .pill{font-size:11px;color:var(--muted2);border:1px solid var(--line2);border-radius:20px;
  padding:1px 7px;}

.wc .filters{display:flex;flex-wrap:wrap;align-items:flex-end;gap:14px;margin:0 0 16px;}
.wc .filters .fld{display:flex;flex-direction:column;gap:6px;}
.wc .filters label{font-family:'Barlow Condensed';font-weight:600;font-size:12px;
  letter-spacing:.07em;text-transform:uppercase;color:var(--muted);}
.wc .filters select,.wc .filters input{background:var(--surface2);color:var(--text);
  border:1px solid var(--line2);border-radius:8px;padding:9px 11px;font-family:'Inter',sans-serif;
  font-size:13px;min-width:190px;}
.wc .filters select:focus,.wc .filters input:focus{outline:none;border-color:var(--blue);}
.wc .filters .clear{appearance:none;background:none;border:1px solid var(--line2);color:var(--muted);
  border-radius:8px;padding:9px 13px;cursor:pointer;font-size:12px;}
.wc .filters .clear:hover{color:var(--text);border-color:var(--blue);}
.wc .filters .count{margin-left:auto;color:var(--muted2);font-size:12px;
  font-variant-numeric:tabular-nums;align-self:center;}
.wc .empty{padding:28px 16px;text-align:center;color:var(--muted2);font-size:14px;
  background:var(--surface);border:1px solid var(--line);border-radius:14px;}

.wc .foot{margin-top:40px;padding-top:18px;border-top:1px solid var(--line);
  color:var(--muted2);font-size:12px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:10px;}

/* Mobile-only "Sort by" control (hidden on desktop; tables sort via headers). */
.wc .msort{display:none;}

/* ---- Phones / small tablets: turn the wide stat tables into stacked cards ---- */
@media (max-width:720px){
  .wc .msort{display:flex;align-items:center;gap:10px;margin:0 0 14px;}
  .wc .msort .msort-l{font-family:'Barlow Condensed';font-weight:600;font-size:12px;
    text-transform:uppercase;letter-spacing:.06em;color:var(--muted);white-space:nowrap;}
  .wc .msort select{flex:1;min-width:0;background:var(--surface2);color:var(--text);
    border:1px solid var(--line2);border-radius:8px;padding:10px 11px;
    font-family:'Inter',sans-serif;font-size:14px;}
  .wc .msort select:focus,.wc .msort .msort-dir:focus-visible{outline:none;border-color:var(--blue);}
  .wc .msort .msort-dir{background:var(--surface2);color:var(--text);border:1px solid var(--line2);
    border-radius:8px;padding:10px 14px;cursor:pointer;font-size:13px;line-height:1;}

  /* Each table row becomes a self-contained card. */
  .wc .panel{background:transparent;border:none;border-radius:0;overflow:visible;}
  .wc .tblscroll{overflow-x:visible;}
  .wc table{min-width:0;}
  .wc thead{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);} /* a11y-hide header */
  .wc table,.wc tbody,.wc tr,.wc td{display:block;width:100%;}
  .wc tbody tr{background:var(--surface);border:1px solid var(--line);border-radius:12px;
    padding:12px 15px;margin-bottom:12px;}
  .wc tbody tr:last-child{margin-bottom:0;}
  .wc tbody tr:hover td,.wc tbody tr:hover td:first-child{background:none;}
  .wc tbody td{display:flex;justify-content:space-between;align-items:center;gap:16px;
    padding:7px 0;border:none;text-align:right;white-space:normal;}
  .wc tbody td::before{content:attr(data-label);font-family:'Barlow Condensed',sans-serif;
    font-weight:600;text-transform:uppercase;letter-spacing:.04em;font-size:12px;
    color:var(--muted);text-align:left;flex:0 0 auto;}
  /* First cell = card title: full width, no label, divider beneath. */
  .wc tbody td:first-child{position:static;display:block;padding:0 0 11px;margin-bottom:7px;
    border-bottom:1px solid var(--line);font-size:16px;font-weight:600;}
  .wc tbody td:first-child::before{content:none;}

  /* Filters & leaderboards stack full-width for easier tapping. */
  .wc .filters{flex-direction:column;align-items:stretch;}
  .wc .filters .fld,.wc .filters select,.wc .filters input{width:100%;min-width:0;}
  .wc .filters .count{margin-left:0;}
  .wc .grid{grid-template-columns:1fr;}
}

@media (max-width:640px){
  .wc .nav{flex-wrap:wrap;gap:14px 18px;padding:12px 18px;}
  .wc .stamp{flex-basis:100%;text-align:left;}
  .wc .wrap{padding:24px 18px 56px;}
}
@media (prefers-reduced-motion:reduce){.wc *{transition:none!important;}}

/* ---- Accordion: clicking a row reveals its games as rows aligned to the same
       columns (so a game's stats sit under the season per-game averages). ---- */
.wc tbody tr.clickable{cursor:pointer;}
.wc tbody tr.clickable:hover td{background:rgba(77,163,255,.06);}
.wc tbody tr.open td{background:rgba(77,163,255,.10);}

.wc .reschip{display:inline-block;font-family:'Barlow Condensed','Inter',sans-serif;font-weight:700;
  font-size:11px;min-width:17px;height:17px;line-height:17px;text-align:center;border-radius:3px;
  padding:0 3px;color:var(--base);}
.wc .reschip.r-W{background:var(--pos);} .wc .reschip.r-L{background:var(--neg);} .wc .reschip.r-D{background:var(--muted2);}
.wc .gres{display:inline-flex;align-items:center;gap:8px;}

.wc tbody tr.gamerow td{background:var(--surface2);}
.wc tbody tr.gamerow td:first-child{background:var(--surface2);box-shadow:inset 3px 0 0 var(--line2);}
.wc tbody tr.gamerow:hover td{background:var(--surface2);}
.wc .gcell-lbl{padding-left:12px;font-weight:500;}
.wc .gcell-lbl .badge{background:var(--line2);color:var(--text);}
.wc .gsub{color:var(--muted2);font-size:12px;}
.wc .gdnp{font-size:10px;color:var(--muted2);border:1px solid var(--line2);border-radius:20px;padding:0 6px;text-transform:uppercase;letter-spacing:.04em;}
.wc .gdash{color:var(--muted2);}

/* ---- Country flag beside the code badge ---- */
.wc .ntag{display:inline-flex;align-items:center;gap:6px;}
.wc .flag{width:20px;height:14px;object-fit:cover;border-radius:2px;display:block;
  box-shadow:0 0 0 1px rgba(255,255,255,.14);flex:0 0 auto;}

/* ---- Rank number in the first column ---- */
.wc .rankwrap{display:flex;align-items:center;}
.wc .ranknum{flex:0 0 auto;min-width:24px;margin-right:12px;text-align:right;color:var(--muted2);
  font-family:'Barlow Condensed','Inter',sans-serif;font-weight:700;font-size:14px;font-variant-numeric:tabular-nums;}

/* ---- Pagination ---- */
.wc .pager{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin:16px 2px 0;}
.wc .pg-count{color:var(--muted2);font-size:12px;font-variant-numeric:tabular-nums;}
.wc .pg-controls{display:flex;align-items:center;gap:6px;margin-left:auto;}
.wc .pg-btn{appearance:none;min-width:32px;height:32px;padding:0 8px;background:var(--surface2);
  color:var(--muted);border:1px solid var(--line2);border-radius:8px;cursor:pointer;
  font-family:'Barlow Condensed','Inter',sans-serif;font-weight:600;font-size:14px;font-variant-numeric:tabular-nums;}
.wc .pg-btn:hover:not(:disabled){color:var(--text);border-color:var(--blue);}
.wc .pg-btn.on{background:var(--blue);color:var(--base);border-color:var(--blue);}
.wc .pg-btn:disabled{opacity:.4;cursor:default;}
.wc .pg-gap{color:var(--muted2);padding:0 2px;}
@media (max-width:640px){.wc .pg-controls{margin-left:0;}}

@media (max-width:720px){
  .wc tbody tr.open{margin-bottom:0;}
  .wc td.gempty{display:none;}                 /* hide value-less cells in card mode */
  .wc tbody tr.gamerow{background:var(--surface2);margin-top:-8px;}
  .wc .gcell-lbl{padding-left:0;}
}
`;

/* ------------------------------------------------------------------ *
 *  LEADERBOARD CARD (home page top-5)
 * ------------------------------------------------------------------ */
function Leaderboard({ title, unit, items, fmt, lowerIsBetter }) {
  const sorted = [...items].sort((a, b) =>
    lowerIsBetter ? a.value - b.value : b.value - a.value
  ).slice(0, 5);
  const max = Math.max(...sorted.map((s) => Math.abs(s.value)), 0.0001);
  const min = Math.min(...sorted.map((s) => Math.abs(s.value)));
  return (
    <div className="card">
      <div className="ch">
        <span className="t">{title}</span>
        <span className="u">{unit}</span>
      </div>
      {sorted.map((it, i) => {
        // Higher-is-better: bar scales with value. Lower-is-better (e.g. fewest
        // goals allowed): best=longest, scaled within the visible range. Both
        // handle 0 cleanly (a clean sheet no longer divides by zero).
        const v = Math.abs(it.value);
        const w = lowerIsBetter
          ? (max === min ? 100 : (1 - (v - min) / (max - min)) * 100)
          : (v / max) * 100;
        return (
          <div className={"row" + (i === 0 ? " first" : "")} key={it.label + i}>
            <span className="rk">{i + 1}</span>
            <span className="nm">
              {it.label}
              {it.sub && <span className="sub">{it.sub}</span>}
            </span>
            <span className="vw">
              <span className="val tnum">{fmt(it.value)}</span>
              <span className="bar"><i style={{ width: `${Math.max(8, w)}%` }} /></span>
            </span>
          </div>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ *
 *  PAGER — numbered pages with ellipses, prev/next, and an X–Y of Z count
 * ------------------------------------------------------------------ */
function pageItems(cur, count) {
  const out = [];
  for (let p = 1; p <= count; p++) {
    if (p === 1 || p === count || (p >= cur - 1 && p <= cur + 1)) out.push(p);
    else if (out[out.length - 1] !== "…") out.push("…");
  }
  return out;
}

function Pager({ page, pageCount, total, from, to, onGo }) {
  return (
    <div className="pager">
      <span className="pg-count">Showing {from}–{to} of {total}</span>
      <div className="pg-controls">
        <button className="pg-btn" onClick={() => onGo(page - 1)} disabled={page <= 1}
          aria-label="Previous page">‹</button>
        {pageItems(page, pageCount).map((p, i) =>
          p === "…"
            ? <span key={"e" + i} className="pg-gap">…</span>
            : <button key={p} className={"pg-btn" + (p === page ? " on" : "")}
                onClick={() => onGo(p)} aria-current={p === page ? "page" : undefined}>{p}</button>
        )}
        <button className="pg-btn" onClick={() => onGo(page + 1)} disabled={page >= pageCount}
          aria-label="Next page">›</button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ *
 *  SORTABLE TABLE
 * ------------------------------------------------------------------ */
function SortTable({ columns, rows, initialSort, rowKey, gamesFor, rank, pageSize }) {
  const [sort, setSort] = useState(initialSort);
  const [open, setOpen] = useState(null);   // accordion: at most one expanded
  const [page, setPage] = useState(1);
  const keyOf = rowKey || ((r) => r.code || (r.name + (r.team || "")));
  const expandable = typeof gamesFor === "function";
  const toggle = (k) => setOpen((cur) => (cur === k ? null : k));
  const sorted = useMemo(() => {
    const col = columns.find((c) => c.key === sort.key);
    const dir = sort.dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const av = col.sortVal ? col.sortVal(a) : a[sort.key];
      const bv = col.sortVal ? col.sortVal(b) : b[sort.key];
      if (typeof av === "string") return av.localeCompare(bv) * dir;
      return (av - bv) * dir;
    });
  }, [rows, sort, columns]);

  const onSort = (key, defDir) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: defDir }));
  const pickSort = (key) =>
    setSort({ key, dir: columns.find((c) => c.key === key)?.defDir || "desc" });
  const flipDir = () => setSort((s) => ({ key: s.key, dir: s.dir === "asc" ? "desc" : "asc" }));

  // Pagination: back to page 1 whenever the sort or the underlying rows (filter/
  // search) change, so you never land on a now-empty page.
  const size = pageSize || 20;
  useEffect(() => { setPage(1); setOpen(null); }, [sort, rows]);
  const total = sorted.length;
  const pageCount = Math.max(1, Math.ceil(total / size));
  const cur = Math.min(page, pageCount);
  const start = (cur - 1) * size;
  const pageRows = sorted.slice(start, start + size);

  return (
    <>
      {/* Mobile-only sort control: column headers are hidden in card view. */}
      <div className="msort">
        <span className="msort-l">Sort by</span>
        <select value={sort.key} onChange={(e) => pickSort(e.target.value)} aria-label="Sort by">
          {columns.map((c) => (
            <option key={c.key} value={c.key}>{c.title || c.label}</option>
          ))}
        </select>
        <button className="msort-dir" onClick={flipDir}
          aria-label={sort.dir === "asc" ? "Ascending" : "Descending"}>
          {sort.dir === "asc" ? "▲" : "▼"}
        </button>
      </div>

      <div className="panel">
        <div className="tblscroll">
          <table>
            <thead>
              <tr>
                {columns.map((c) => (
                  <th
                    key={c.key}
                    className={sort.key === c.key ? "on" : ""}
                    onClick={() => onSort(c.key, c.defDir || "desc")}
                    onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onSort(c.key, c.defDir || "desc"))}
                    tabIndex={0}
                    title={c.title || c.label}
                  >
                    {c.label}
                    {sort.key === c.key && <span className="ar">{sort.dir === "asc" ? "▲" : "▼"}</span>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pageRows.map((r, i) => {
                const k = keyOf(r);
                const isOpen = expandable && open === k;
                const rnk = start + i + 1;   // continuous rank across pages
                return (
                  <Fragment key={k || rnk}>
                    <tr
                      className={(expandable ? "clickable" : "") + (isOpen ? " open" : "")}
                      onClick={expandable ? () => toggle(k) : undefined}
                      onKeyDown={expandable ? (e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), toggle(k)) : undefined}
                      tabIndex={expandable ? 0 : undefined}
                      aria-expanded={expandable ? isOpen : undefined}
                    >
                      {columns.map((c, ci) => (
                        <td key={c.key} data-label={c.label}>
                          {rank && ci === 0 ? (
                            <span className="rankwrap">
                              <span className="ranknum">{rnk}</span>
                              {c.render ? c.render(r) : r[c.key]}
                            </span>
                          ) : (c.render ? c.render(r) : r[c.key])}
                        </td>
                      ))}
                    </tr>
                    {isOpen && gamesFor(r).map((ctx, gi) => (
                      <tr className="gamerow" key={k + ":" + (ctx.date || gi)}>
                        {columns.map((c) => (
                          <td key={c.key} data-label={c.label}
                            className={c.gameCell ? undefined : "gempty"}>
                            {c.gameCell ? c.gameCell(ctx) : null}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {pageCount > 1 && (
        <Pager page={cur} pageCount={pageCount} total={total}
          from={start + 1} to={Math.min(start + size, total)} onGo={setPage} />
      )}
    </>
  );
}

const f2 = (n) => n.toFixed(2);
const fSigned = (n) => (n > 0 ? "+" : "") + n.toFixed(2);
const fmtDate = (iso) =>
  new Date(iso + "T00:00:00Z").toLocaleDateString("en-US",
    { month: "short", day: "numeric", timeZone: "UTC" });

// Per-match game contexts for a team / player row, fed to each column's gameCell.
const teamGamesFor = (t, games) =>
  (games.teams?.[t.code] || []).map(([date, opp, res, gf, ga, sh, sot, cor]) =>
    ({ date, opp, res, gf, ga, sh, sot, cor }));

const playerGamesFor = (p, games) => {
  const mine = games.players?.[p.team]?.[p.name] || {};
  return (games.teams?.[p.team] || []).map(([date, opp, res, gf, ga]) => {
    const s = mine[date];   // [goals, assists, shots, sog] or undefined => DNP
    return { date, opp, res, gf, ga, played: !!s,
      g: s?.[0], a: s?.[1], sh: s?.[2], sog: s?.[3] };
  });
};

// First-column label for a game row: opponent badge + date (+ DNP tag).
const gameLabel = (ctx, nameByCode, dnp) => (
  <span className="team-cell gcell-lbl">
    <TeamTag code={ctx.opp} title={nameByCode[ctx.opp] || ctx.opp} />
    <span className="gsub">{fmtDate(ctx.date)}</span>
    {dnp && <span className="gdnp">DNP</span>}
  </span>
);
const gNum = (v) => (v == null ? <span className="gdash">—</span> : v);
const resChip = (res) => <span className={"reschip r-" + res}>{res}</span>;

// FIFA 3-letter code -> flagcdn slug (ISO 3166-1 alpha-2, or a UK subdivision).
const FLAG = {
  ALG: "dz", ARG: "ar", AUS: "au", AUT: "at", BEL: "be", BIH: "ba", BRA: "br", CAN: "ca",
  CIV: "ci", COD: "cd", COL: "co", CPV: "cv", CRO: "hr", CUW: "cw", CZE: "cz", ECU: "ec",
  EGY: "eg", ENG: "gb-eng", ESP: "es", FRA: "fr", GER: "de", GHA: "gh", HAI: "ht", IRN: "ir",
  IRQ: "iq", JOR: "jo", JPN: "jp", KOR: "kr", KSA: "sa", MAR: "ma", MEX: "mx", NED: "nl",
  NOR: "no", NZL: "nz", PAN: "pa", PAR: "py", POR: "pt", QAT: "qa", RSA: "za", SCO: "gb-sct",
  SEN: "sn", SUI: "ch", SWE: "se", TUN: "tn", TUR: "tr", URU: "uy", USA: "us", UZB: "uz",
};

function Flag({ code }) {
  const iso = FLAG[code];
  if (!iso) return null;   // unmapped code: just show the badge, no broken image
  return <img className="flag" src={`https://flagcdn.com/${iso}.svg`} alt="" loading="lazy"
    onError={(e) => { e.currentTarget.style.display = "none"; }} />;
}

// Flag + code badge, used wherever a country appears in the tables.
function TeamTag({ code, title }) {
  return (
    <span className="ntag">
      <Flag code={code} />
      <span className="badge" title={title}>{code}</span>
    </span>
  );
}

/* ------------------------------------------------------------------ *
 *  PAGES
 * ------------------------------------------------------------------ */
function Home({ data, go }) {
  const { teams, players } = data;
  const tItems = (key) => teams.map((t) => ({ label: t.name, value: t[key] }));
  const pItems = (key) => players.map((p) => ({ label: p.name, sub: p.team, value: p[key] }));

  return (
    <div className="wrap">
      <div className="hero">
        <div className="eyebrow">Matchday {data.matchday} · Group Stage</div>
        <h1>Tournament Stat Leaders</h1>
        <p>Live per-game leaders across all 48 nations. Tables refresh automatically at the
          close of every match day. Dig into the full breakdowns on the Teams and Players pages.</p>
      </div>

      <div className="sechead">
        <span className="kick">01</span>
        <h2>Team Statistics</h2>
        <span className="rule" />
        <button className="tab" onClick={() => go("teams")}>All teams →</button>
      </div>
      <div className="grid">
        <Leaderboard title="Goals / game" unit="per match" items={tItems("gpg")} fmt={f2} />
        <Leaderboard title="Goal diff / game" unit="per match" items={tItems("gdpg")} fmt={fSigned} />
        <Leaderboard title="Fewest allowed / game" unit="per match" items={tItems("apg")} fmt={f2} lowerIsBetter />
        <Leaderboard title="Shots on target / game" unit="per match" items={tItems("sotpg")} fmt={f2} />
      </div>

      <div className="sechead">
        <span className="kick">02</span>
        <h2>Player Statistics</h2>
        <span className="rule" />
        <button className="tab" onClick={() => go("players")}>All players →</button>
      </div>
      <div className="grid">
        <Leaderboard title="Goals / game" unit="per match" items={pItems("gpg")} fmt={f2} />
        <Leaderboard title="Assists / game" unit="per match" items={pItems("apg")} fmt={f2} />
        <Leaderboard title="Shots / game" unit="per match" items={pItems("shpg")} fmt={f2} />
        <Leaderboard title="Shots on goal / game" unit="per match" items={pItems("sogpg")} fmt={f2} />
      </div>
    </div>
  );
}

function Teams({ data }) {
  const nameByCode = useMemo(
    () => Object.fromEntries(data.teams.map((t) => [t.code, t.name])), [data.teams]);
  // Each column also knows how to render one game's value, so the per-match rows
  // line up under the same columns as the season per-game averages.
  const cols = [
    { key: "name", label: "Team", defDir: "asc",
      render: (t) => <span className="team-cell"><TeamTag code={t.code} />{t.name}</span>,
      gameCell: (g) => gameLabel(g, nameByCode) },
    { key: "rec", label: "Record", title: "Win–Draw–Loss", sortVal: (t) => t.pts,
      render: (t) => <span className="rec">{t.W}–{t.D}–{t.L}</span>,
      gameCell: (g) => resChip(g.res) },
    { key: "gpg", label: "GF/g", title: "Goals per game", render: (t) => <b className="tnum">{f2(t.gpg)}</b>,
      gameCell: (g) => <b className="tnum">{g.gf}</b> },
    { key: "apg", label: "GA/g", title: "Allowed goals per game", render: (t) => <span className="tnum">{f2(t.apg)}</span>,
      gameCell: (g) => <span className="tnum">{g.ga}</span> },
    { key: "gdpg", label: "GD/g", title: "Goal difference per game",
      render: (t) => <span className={"tnum " + (t.gdpg >= 0 ? "pos" : "neg")}>{fSigned(t.gdpg)}</span>,
      gameCell: (g) => <span className={"tnum " + (g.gf - g.ga >= 0 ? "pos" : "neg")}>{(g.gf - g.ga > 0 ? "+" : "") + (g.gf - g.ga)}</span> },
    { key: "spg", label: "Shots/g", title: "Total shots per game", render: (t) => <span className="tnum">{f2(t.spg)}</span>,
      gameCell: (g) => <span className="tnum">{g.sh}</span> },
    { key: "sotpg", label: "SoT/g", title: "Shots on target per game", render: (t) => <span className="tnum">{f2(t.sotpg)}</span>,
      gameCell: (g) => <span className="tnum">{g.sot}</span> },
    { key: "cpg", label: "Corners/g", title: "Corners per game", render: (t) => <span className="tnum">{f2(t.cpg)}</span>,
      gameCell: (g) => <span className="tnum">{g.cor}</span> },
    { key: "P", label: "P", title: "Matches played", render: (t) => <span className="pill tnum">{t.P}</span> },
  ];
  return (
    <div className="wrap">
      <div className="hero">
        <div className="eyebrow">All 48 nations</div>
        <h1>Team Statistics</h1>
        <p>Every metric is normalized per game so teams at different points in the schedule stay
          comparable. Tap any column to sort, or a team to see its game-by-game log.</p>
      </div>
      <div style={{ marginTop: 28 }}>
        <SortTable columns={cols} rows={data.teams} initialSort={{ key: "gpg", dir: "desc" }}
          rowKey={(t) => t.code} rank pageSize={15}
          gamesFor={(t) => teamGamesFor(t, data.games)} />
      </div>
    </div>
  );
}

function Players({ data }) {
  const [team, setTeam] = useState("ALL");
  const [query, setQuery] = useState("");
  const nameByCode = useMemo(
    () => Object.fromEntries(data.teams.map((t) => [t.code, t.name])), [data.teams]);
  // gameCell renders one match's value under the same column as the season rate;
  // for a match the player didn't play, stats show "—" and the label is tagged DNP.
  const cols = [
    { key: "name", label: "Player", defDir: "asc", render: (p) => <span style={{ fontWeight: 600 }}>{p.name}</span>,
      gameCell: (g) => gameLabel(g, nameByCode, !g.played) },
    { key: "team", label: "Team", defDir: "asc", render: (p) => <TeamTag code={p.team} />,
      gameCell: (g) => <span className="gres">{resChip(g.res)}<span className="tnum">{g.gf}–{g.ga}</span></span> },
    { key: "pos", label: "Pos", defDir: "asc", render: (p) => <span className="pill">{p.pos}</span> },
    { key: "gpg", label: "Goals/g", title: "Goals per game", render: (p) => <b className="tnum">{f2(p.gpg)}</b>,
      gameCell: (g) => <b className="tnum">{gNum(g.g)}</b> },
    { key: "apg", label: "Assists/g", title: "Assists per game", render: (p) => <span className="tnum">{f2(p.apg)}</span>,
      gameCell: (g) => <span className="tnum">{gNum(g.a)}</span> },
    { key: "shpg", label: "Shots/g", title: "Shots per game", render: (p) => <span className="tnum">{f2(p.shpg)}</span>,
      gameCell: (g) => <span className="tnum">{gNum(g.sh)}</span> },
    { key: "sogpg", label: "SoG/g", title: "Shots on goal per game", render: (p) => <span className="tnum">{f2(p.sogpg)}</span>,
      gameCell: (g) => <span className="tnum">{gNum(g.sog)}</span> },
    { key: "P", label: "P", title: "Matches played", render: (p) => <span className="pill tnum">{p.P}</span> },
  ];

  // Teams that actually have players, as [code, fullName], sorted by name.
  const teamOptions = useMemo(() => {
    const seen = new Map();
    for (const p of data.players) if (!seen.has(p.team)) seen.set(p.team, p.teamName);
    return [...seen.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  }, [data.players]);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return data.players.filter(
      (p) =>
        (team === "ALL" || p.team === team) &&
        (!q || p.name.toLowerCase().includes(q))
    );
  }, [data.players, team, query]);

  const filtered = team !== "ALL" || query.trim() !== "";

  return (
    <div className="wrap">
      <div className="hero">
        <div className="eyebrow">Individual leaders</div>
        <h1>Player Statistics</h1>
        <p>Per-game scoring and shooting output for every player on the pitch. Filter by team or
          search by name, then tap any column to sort — or a player to see their game-by-game log.</p>
      </div>
      <div style={{ marginTop: 28 }}>
        <div className="filters">
          <div className="fld">
            <label htmlFor="team-filter">Team</label>
            <select id="team-filter" value={team} onChange={(e) => setTeam(e.target.value)}>
              <option value="ALL">All teams</option>
              {teamOptions.map(([code, name]) => (
                <option key={code} value={code}>{name}</option>
              ))}
            </select>
          </div>
          <div className="fld">
            <label htmlFor="player-search">Search player</label>
            <input
              id="player-search"
              type="search"
              placeholder="e.g. Messi"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          {filtered && (
            <button className="clear" onClick={() => { setTeam("ALL"); setQuery(""); }}>
              Clear
            </button>
          )}
          <span className="count">
            {rows.length} player{rows.length === 1 ? "" : "s"}
          </span>
        </div>
        {rows.length ? (
          <SortTable columns={cols} rows={rows} initialSort={{ key: "gpg", dir: "desc" }}
            rowKey={(p) => p.name + "|" + p.team} rank pageSize={15}
            gamesFor={(p) => playerGamesFor(p, data.games)} />
        ) : (
          <div className="empty">No players match this filter.</div>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ *
 *  APP SHELL
 * ------------------------------------------------------------------ */
export default function App() {
  const [data, setData] = useState(() => deriveData(SAMPLE));
  const [live, setLive] = useState(false);
  const [page, setPage] = useState("home");

  // Render sample immediately, then swap in the pipeline's data.json if present.
  useEffect(() => {
    fetch(import.meta.env.BASE_URL + "data.json", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((raw) => { setData(deriveData(raw)); setLive(true); })
      .catch(() => {/* keep sample fallback */});
  }, []);
  const stamp = new Date(data.updated).toLocaleString("en-US", {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });

  const tabs = [
    ["home", "Home"],
    ["teams", "Teams"],
    ["players", "Players"],
  ];

  return (
    <div className="wc">
      <style>{CSS}</style>
      <nav className="nav">
        <span className="brand cond">Matchday <span className="yr">’26</span></span>
        {tabs.map(([id, label]) => (
          <button
            key={id}
            className={"tab" + (page === id ? " on" : "")}
            onClick={() => setPage(id)}
            aria-current={page === id ? "page" : undefined}
          >
            {label}
          </button>
        ))}
        <span className="navspace" />
        <span className="stamp">
          Updated <b>{stamp}</b><br />after Matchday {data.matchday}
        </span>
      </nav>

      {page === "home" && <Home data={data} go={setPage} />}
      {page === "teams" && <Teams data={data} />}
      {page === "players" && <Players data={data} />}

      <div className="wrap" style={{ paddingTop: 0 }}>
        <div className="foot">
          <span>{live
            ? "Live data from public/data.json (FBref via soccerdata)."
            : "Sample data shown — run fetch_fbref.py to generate public/data.json."}</span>
          <span>FIFA World Cup 2026 · 48 teams · 104 matches</span>
        </div>
      </div>
    </div>
  );
}
