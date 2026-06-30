/* ──────────────────────────────────────────────────────────────────────────
   regions.ts — Bay Area REGION + SF-NEIGHBORHOOD taxonomy

   This is the single source of truth for the radar/spider chart's axes. Each
   axis ("edge" of the radar) is one geographic preference dimension the visitor
   can dial up or down. A listing belongs to exactly one axis, decided by its
   data `market` string (the strings that actually appear in housing-data.json:
   `marketOrder` + every distinct `listing.market`) with a light city fallback.

   Conventions mirror App.tsx:
     • SF markets are the ones prefixed "SF " (see App.tsx regionPass / transitMethod).
     • Peninsula = App.tsx PENINSULA list; South Bay = App.tsx SOUTH list.
     • 0..10 scales like the sidebar weights, accent via var(--accent), light theme.

   Axis design goal: cover every active market, split SF into its real
   neighborhood markets, keep Peninsula corridor + South Bay near the office
   high, and sink far East/North Bay — without ever zeroing a region.
   ────────────────────────────────────────────────────────────────────────── */

export type RegionAxis = { key: string; label: string; markets: string[] };

/* Every active data `market` string is mapped to exactly one axis below.
   SF gets five neighborhood axes (the data already carries these strings, plus
   "SF Dogpatch/Potrero/Showplace" which the scraper emits for that corridor and
   a bare "SF" catch-all for un-neighborhooded SF listings). The Peninsula and
   South Bay markets each get their own axis so the corridor reads clearly on the
   radar, and "Elsewhere" absorbs "Other Bay Area" (East/North Bay + outliers). */
export const REGION_AXES: RegionAxis[] = [
  {
    key: "sf-soma",
    label: "SF · SoMa / Mission Bay",
    markets: ["SF SoMa/South Beach/Mission Bay"],
  },
  {
    key: "sf-mission",
    label: "SF · Mission / Valencia",
    markets: ["SF Mission/Valencia"],
  },
  {
    key: "sf-hayes",
    label: "SF · Hayes / Castro",
    markets: ["SF Hayes/Lower Haight/Castro/Duboce"],
  },
  {
    key: "sf-dogpatch",
    label: "SF · Dogpatch / Potrero",
    markets: ["SF Dogpatch/Potrero/Showplace"],
  },
  {
    key: "sf-west",
    label: "SF · Sunset / Richmond / Marina",
    // Bare "SF" lands here too: the western/northern half is the default for
    // un-neighborhooded SF listings and keeps every SF market on a real axis.
    markets: ["SF Sunset/Richmond/Marina/North Beach", "SF"],
  },
  {
    key: "peninsula-mid",
    label: "Peninsula · San Mateo / Burlingame",
    markets: ["San Mateo/Burlingame/Millbrae"],
  },
  {
    key: "peninsula-rwc",
    label: "Peninsula · Redwood City / San Carlos",
    markets: ["Redwood City/San Carlos/Belmont"],
  },
  {
    key: "peninsula-pa",
    label: "Peninsula · Palo Alto / Menlo Park",
    markets: ["Palo Alto/Menlo Park"],
  },
  {
    key: "south-mtv",
    label: "South Bay · Mountain View",
    markets: ["Mountain View"],
  },
  {
    key: "south-sunnyvale",
    label: "South Bay · Sunnyvale",
    markets: ["Sunnyvale"],
  },
  {
    key: "south-santaclara",
    label: "South Bay · Santa Clara (office)",
    markets: ["Santa Clara"],
  },
  {
    key: "south-sj",
    label: "South Bay · North San Jose",
    // The stray "South Bay" market string the scraper occasionally emits sits
    // here rather than getting its own near-empty axis.
    markets: ["North San Jose", "South Bay"],
  },
  {
    key: "elsewhere",
    label: "Elsewhere · East / North Bay",
    markets: ["Other Bay Area"],
  },
];

// market string -> axis key (built once from REGION_AXES so the two never drift).
const MARKET_TO_AXIS: Record<string, string> = (() => {
  const out: Record<string, string> = {};
  for (const axis of REGION_AXES) for (const m of axis.markets) out[m] = axis.key;
  return out;
})();

const ELSEWHERE = "elsewhere";

/* Light city fallback for the ~3% of listings whose `market` is blank or an
   off-list string (e.g. "Other Bay Area" rows whose city is actually a corridor
   town, or a future market string the scraper hasn't been mapped yet). Mirrors
   the geocode() ordering in App.tsx so classification stays consistent. Returns
   "" when the city gives no signal, letting listingAxisKey fall to "elsewhere". */
function cityAxisKey(city: string): string {
  const t = (city || "").toLowerCase();
  const has = (...ks: string[]) => ks.some((k) => t.includes(k));
  if (!t.trim()) return "";
  // SF — bare/neighborhood-less SF text lands on the western SF axis.
  if (has("san francisco") || /\bsf\b/.test(t)) {
    if (has("soma", "south beach", "mission bay")) return "sf-soma";
    if (has("dogpatch", "potrero", "showplace")) return "sf-dogpatch";
    if (has("hayes", "lower haight", "castro", "duboce")) return "sf-hayes";
    if (has("mission", "valencia")) return "sf-mission";
    return "sf-west";
  }
  // South Bay (closest to the Santa Clara office) before Peninsula.
  if (has("santa clara")) return "south-santaclara";
  if (has("sunnyvale")) return "south-sunnyvale";
  if (has("mountain view")) return "south-mtv";
  if (has("north san jose", "milpitas", "san jose")) return "south-sj";
  // Peninsula corridor.
  if (has("palo alto", "menlo park", "east palo alto", "los altos")) return "peninsula-pa";
  if (has("redwood city", "san carlos", "belmont")) return "peninsula-rwc";
  if (has("san mateo", "burlingame", "millbrae")) return "peninsula-mid";
  return "";
}

/* Return the axis key for a listing. `market` is authoritative; `city` only
   resolves blanks / off-list markets. Always returns a valid axis key (never
   throws, never empty) so callers can index DEFAULT_REGION_VALUES safely. */
export function listingAxisKey(market: string, city: string): string {
  const direct = MARKET_TO_AXIS[market];
  if (direct) return direct;
  const byCity = cityAxisKey(city);
  if (byCity) return byCity;
  return ELSEWHERE;
}

/* Sensible 0..10 starting preferences. Liam's office is HackerRank / Santa
   Clara, with a strong Caltrain-corridor + SF-rail bias (see App.tsx OFFICE +
   transitMethod). So: SF rail-served neighborhoods and the mid/lower Peninsula
   corridor + near-office South Bay rank high; far East/North Bay sinks low.
   Every axis key in REGION_AXES has an entry. */
export const DEFAULT_REGION_VALUES: Record<string, number> = {
  // SF — rail-/transit-strong, Liam likes the city. SoMa/Mission Bay is the
  // most office-commutable (Caltrain at 4th & King) so it edges out the rest.
  "sf-soma": 9,
  "sf-mission": 8,
  "sf-dogpatch": 8,
  "sf-hayes": 7,
  "sf-west": 6,
  // Peninsula corridor — straight-shot Caltrain to Santa Clara, climbs as it
  // nears the office.
  "peninsula-mid": 7,
  "peninsula-rwc": 8,
  "peninsula-pa": 8,
  // South Bay — Santa Clara is the office itself; neighbors are easy commutes.
  "south-mtv": 7,
  "south-sunnyvale": 8,
  "south-santaclara": 9,
  "south-sj": 6,
  // Far East/North Bay + outliers — possible but a hard commute. Low, not zero.
  elsewhere: 3,
};

/* regionBoost(value) → multiplier applied to a listing's fit by how much the
   visitor wants that listing's region.

   Formula (linear, documented):
       boost = MIN + (MAX - MIN) * (value / 10)
   with MIN = 0.55 and MAX = 1.25. So:
       value 0  → 0.55   (unwanted region: fit sinks ~45%, but never to 0)
       value 5  → 0.90   (neutral: slight damping)
       value 7  → 1.04   (wanted: small lift)
       value 10 → 1.25   (most-wanted region: fit rises 25%)

   Multiplicative + bounded means a region preference re-ranks listings without
   ever erasing a strong-on-other-axes listing (no zeroing), matching App.tsx's
   weighted-but-never-hard-filter scoring philosophy. `value` is clamped to
   0..10 so out-of-range inputs stay inside the [MIN, MAX] envelope. */
export function regionBoost(value: number): number {
  const MIN = 0.55;
  const MAX = 1.25;
  const v = Math.max(0, Math.min(10, value));
  return MIN + (MAX - MIN) * (v / 10);
}
