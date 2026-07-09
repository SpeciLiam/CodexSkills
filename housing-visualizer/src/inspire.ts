/* Inspire Me — turn 3,000 rows of inventory into a five-listing shortlist the
   user can act on in one glance. Each pick comes from a different ANGLE so the
   set is diverse (not five near-identical top-fit rows), and each carries a
   plain-English reason. Deliberately ignores the current narrow filters — the
   point is to surface what the user's own filter bubble is hiding — but always
   respects marks (never resurfaces something they passed on).

   Pure functions over the already-scored rows from App.tsx, so every number
   shown matches the main list exactly. */

export type InspireCandidate = {
  id: string;
  title: string;
  url: string;
  sub: string;
  fit: number;
  priceLabel: string;
  mark: string;
  pricePerBedroom: number | null;
  boardFitTier: string;
  firstAgeDays: number | null;
  scamRisk: boolean;
  pipelineWhy: string;
  _price: number; // 1e9 when unknown (matches App row sentinel)
  _avg: number; // avg commute minutes, 1e9 when unknown
};

export type InspirePick = { row: InspireCandidate; angle: string; reason: string };

// Deterministic PRNG so "another round" reshuffles but a given seed is stable.
function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const money = (n: number) => "$" + n.toLocaleString();
const commuteBit = (r: InspireCandidate) => (r._avg < 1e9 ? `~${Math.round(r._avg)}m commute` : "commute unrated");
const priceBit = (r: InspireCandidate) => (r._price < 1e9 ? money(r._price) + "/mo" : "no price listed");

/* Pick up to `count` listings, one per angle, no repeats. `seed` varies the
   wildcard + tie-breaking so re-rolls feel fresh without being random noise. */
export function pickInspiration(pool: InspireCandidate[], seed: number, count = 5): InspirePick[] {
  // Never pitch something the user already triaged, and never pitch scam-risk rows.
  const cands = pool.filter((r) => !r.mark && !r.scamRisk);
  if (!cands.length) return [];
  const rand = mulberry32(seed * 2654435761 + 97);
  const used = new Set<string>();
  const take = (rows: InspireCandidate[]) => {
    for (const r of rows) if (!used.has(r.id)) { used.add(r.id); return r; }
    return null;
  };

  const byFit = [...cands].sort((a, b) => b.fit - a.fit || a._avg - b._avg);
  const decentFit = byFit.filter((r) => r.fit >= Math.min(55, byFit[0]?.fit ?? 0)); // adapts when inventory is weak
  const picks: InspirePick[] = [];
  const add = (row: InspireCandidate | null, angle: string, reason: (r: InspireCandidate) => string) => {
    if (row && picks.length < count) picks.push({ row, angle, reason: reason(row) });
  };

  // 1 · The strongest fit they haven't looked at.
  add(take(byFit), "Top fit", (r) => `Highest fit (${r.fit}) you haven't triaged yet — ${priceBit(r)}, ${commuteBit(r)}.`);

  // 2 · Best value: cheapest per bedroom (falling back to raw price) among decent fits.
  const byValue = [...decentFit].sort(
    (a, b) => (a.pricePerBedroom ?? (a._price < 1e9 ? a._price : 1e9)) - (b.pricePerBedroom ?? (b._price < 1e9 ? b._price : 1e9))
  );
  add(take(byValue.filter((r) => r._price < 1e9)), "Best value", (r) =>
    r.pricePerBedroom
      ? `${money(r.pricePerBedroom)}/bedroom — the best split among strong fits (fit ${r.fit}).`
      : `${priceBit(r)} — cheapest of the strong fits (fit ${r.fit}).`
  );

  // 3 · Quickest door-to-desk among decent fits.
  const byCommute = [...decentFit].sort((a, b) => a._avg - b._avg);
  add(take(byCommute.filter((r) => r._avg < 1e9)), "Quickest commute", (r) => `${commuteBit(r)} — shortest ride of the strong fits, ${priceBit(r)}.`);

  // 4 · Fresh this week: newest arrival that still scores well.
  const fresh = byFit.filter((r) => r.firstAgeDays != null && r.firstAgeDays <= 7);
  add(take(fresh), "Fresh this week", (r) => `Listed ${r.firstAgeDays === 0 ? "today" : `${r.firstAgeDays}d ago`} and already fits at ${r.fit} — early beats waitlists.`);

  // 5 · Wildcard: seeded draw from the top quartile, so re-rolls surface new rows.
  const quartile = byFit.slice(0, Math.max(8, Math.ceil(byFit.length / 4)));
  const unpicked = quartile.filter((r) => !used.has(r.id));
  add(unpicked.length ? unpicked[Math.floor(rand() * unpicked.length)] : null, "Wildcard", (r) =>
    `Worth a second look: fit ${r.fit}, ${priceBit(r)}, ${commuteBit(r)}${r.boardFitTier ? ` · board says ${r.boardFitTier}` : ""}.`
  );

  // Backfill if an angle had no candidates (tiny pools) — keep it at `count` when possible.
  for (const r of byFit) {
    if (picks.length >= count) break;
    if (!used.has(r.id)) { used.add(r.id); picks.push({ row: r, angle: "Also strong", reason: `Fit ${r.fit}, ${priceBit(r)}, ${commuteBit(r)}.` }); }
  }
  return picks;
}
