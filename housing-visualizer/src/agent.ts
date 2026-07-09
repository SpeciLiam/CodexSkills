/* Agent intent parser — the dashboard's "main point of contact". Turns one
   typed sentence into the same state changes the sidebar controls make, so
   "2bd in sunnyvale under $3k near the caltrain" is one message instead of
   five widget hunts. Deterministic regex parsing (no LLM, no network): instant,
   testable, and it can never hallucinate a filter.

   Anything it can't parse is NOT an error — the caller queues it as a request
   for the repo-side agent (agentStore.ts), which is how source additions and
   pipeline changes flow in. */

export type AgentAction =
  | { kind: "budget"; value: number }
  | { kind: "beds"; value: string }
  | { kind: "market"; value: string }
  | { kind: "region"; value: string }
  | { kind: "segment"; value: string }
  | { kind: "sort"; value: string }
  | { kind: "markFilter"; value: string }
  | { kind: "maxTransit"; value: number }
  | { kind: "maxDrive"; value: number }
  | { kind: "profile"; value: "liam" | "group" }
  | { kind: "huntMode"; value: string }
  | { kind: "point"; query: string; radius?: number }
  | { kind: "clearPoint" }
  | { kind: "inspire" }
  | { kind: "reset" }
  | { kind: "showNeedsReview"; value: boolean };

export type ParsedCommand = { actions: AgentAction[]; said: string[] };

const num = (s: string) => parseInt(s.replace(/,/g, ""), 10);
const moneyVal = (raw: string, k?: string) => {
  let v = parseFloat(raw.replace(/,/g, ""));
  if (k) v *= 1000;
  else if (v > 0 && v < 10) v *= 1000; // "under 3" means $3k in rent talk
  return Math.round(v);
};

/* Parse one message. `markets` is the live market list (for "in <market>"),
   used after point/beds/budget phrases are stripped so tokens aren't claimed
   twice. Returns null when nothing matched (caller should queue it). */
export function parseCommand(text: string, markets: string[]): ParsedCommand | null {
  let t = " " + (text || "").toLowerCase().replace(/\s+/g, " ").trim() + " ";
  if (t.trim() === "") return null;
  const actions: AgentAction[] = [];
  const said: string[] = [];
  const eat = (m: RegExpMatchArray) => { t = t.replace(m[0], " "); };

  // reset first — it wipes everything else.
  const mReset = t.match(/\b(?:reset|clear)(?: (?:all|the|my))? (?:filters?|everything|search)\b/);
  if (mReset || t.trim() === "reset") {
    return { actions: [{ kind: "reset" }], said: ["reset all filters"] };
  }

  // inspire
  if (/\binspire\b|\bsurprise me\b|\bwhat should i (?:look at|check)\b|\bshow me something\b/.test(t)) {
    actions.push({ kind: "inspire" });
    said.push("opened Inspire Me");
    t = t.replace(/\binspire( me)?\b|\bsurprise me\b/, " ");
  }

  // clear the point pin
  const mClrPt = t.match(/\b(?:clear|remove|drop)(?: the)? (?:point|pin|near|location)\b/);
  if (mClrPt) { actions.push({ kind: "clearPoint" }); said.push("cleared the point pin"); eat(mClrPt); }

  // point search — "within 2 miles of X" first (more specific), then "near X".
  const mWithin = t.match(/\bwithin (\d+(?:\.\d+)?) ?(?:mi|mile|miles) (?:of|from|around) ([^,.;]+)/);
  const mNear = mWithin ? null : t.match(/\b(?:near|around|close to|walkable to|by) (?!me\b)((?:[a-z0-9&' ]){3,}?)(?=\s*(?:$|,|\.|;|\bunder\b|\bbelow\b|\bmax\b|\bfor\b|\bwith\b|\bsort\b))/);
  if (mWithin) {
    const q = mWithin[2].trim();
    actions.push({ kind: "point", query: q, radius: parseFloat(mWithin[1]) });
    said.push(`pinned "${q}" (${mWithin[1]} mi radius)`);
    eat(mWithin);
  } else if (mNear && mNear[1].trim().length >= 3) {
    const q = mNear[1].trim();
    actions.push({ kind: "point", query: q });
    said.push(`pinned "${q}"`);
    eat(mNear);
  }

  // budget — "under/below/max/up to $3,000" or "$2.5k"
  const mBudget = t.match(/\b(?:under|below|max|less than|up to|budget(?: of)?|<=?) ?\$? ?(\d[\d,]*(?:\.\d+)?) ?(k)?\b/);
  if (mBudget) {
    const v = moneyVal(mBudget[1], mBudget[2]);
    if (v >= 300) { actions.push({ kind: "budget", value: v }); said.push(`budget ≤ $${v.toLocaleString()}`); eat(mBudget); }
  }

  // beds — "studio", "2bd", "3+ bed"
  if (/\bstudio\b/.test(t)) {
    actions.push({ kind: "beds", value: "Studio" });
    said.push("studios");
    t = t.replace(/\bstudios?\b/, " ");
  } else {
    const mBeds = t.match(/\b(\d) ?\+? ?(?:bd|br|beds?|bedrooms?)\b/);
    if (mBeds) {
      const n = Math.min(Math.max(num(mBeds[1]), 1), 6);
      actions.push({ kind: "beds", value: `${n}+ bd` });
      said.push(`${n}+ bd`);
      eat(mBeds);
    }
  }

  // commute caps — "transit under 45", "45 min transit", "drive under 30"
  const mTransit = t.match(/\b(?:transit|no.?car|train)[^\d]{0,12}(\d{2,3}) ?(?:m|min|mins|minutes)?\b/) || t.match(/\b(\d{2,3}) ?(?:m|min|mins|minutes) (?:transit|no.?car|by train)\b/);
  if (mTransit) { actions.push({ kind: "maxTransit", value: num(mTransit[1]) }); said.push(`no-car commute ≤ ${num(mTransit[1])}m`); eat(mTransit); }
  const mDrive = t.match(/\b(?:drive|driving|car)[^\d]{0,12}(\d{2,3}) ?(?:m|min|mins|minutes)?\b/) || t.match(/\b(\d{2,3}) ?(?:m|min|mins|minutes) (?:drive|driving|by car)\b/);
  if (mDrive) { actions.push({ kind: "maxDrive", value: num(mDrive[1]) }); said.push(`drive ≤ ${num(mDrive[1])}m`); eat(mDrive); }

  // sort
  const sorts: [RegExp, string][] = [
    [/\bcheapest\b|\bby price\b|\blowest (?:price|rent)\b/, "Cheapest"],
    [/\bshortest commute\b|\bfastest commute\b|\bby commute\b/, "Shortest commute"],
    [/\bnewest\b|\bmost recent\b|\blatest\b/, "Newest"],
    [/\bbest fit\b/, "Best fit"],
    [/\bboard rank\b/, "Board rank"],
    [/\bclosest\b|\bnearest\b|\bby distance\b/, "Closest first"],
  ];
  for (const [re, val] of sorts) {
    const m = t.match(re);
    if (m) { actions.push({ kind: "sort", value: val }); said.push(`sorted by ${val.toLowerCase()}`); eat(m); break; }
  }

  // marks view
  const markViews: [RegExp, string, string][] = [
    [/\b(?:show |only )?promising\b|\bstarred\b/, "promising", "showing ★ promising"],
    [/\bchecked(?: |-)?out\b/, "checked", "showing ✓ checked out"],
    [/\bpassed\b|\bskipped\b/, "skip", "showing ✕ passed"],
    [/\barchived\b|\bunavailable ones\b/, "gone", "showing ⊘ archived"],
    [/\bshow all marks\b|\ball marks\b|\beverything including marks\b/, "all", "showing every mark"],
  ];
  for (const [re, val, s] of markViews) {
    const m = t.match(re);
    if (m) { actions.push({ kind: "markFilter", value: val }); said.push(s); eat(m); break; }
  }

  // segment
  const segs: [RegExp, string][] = [
    [/\bsublets?\b|\bsubleases?\b|\bshort.?term\b/, "Subleases"],
    [/\brooms?\b(?! in 5)/, "Rooms"],
    [/\bapartments?\b|\bwhole (?:units?|apartments?)\b/, "Apartments"],
    [/\bnew today\b|\btoday'?s\b/, "New today"],
    [/\bto verify\b|\bneeds? verification\b/, "To verify"],
  ];
  for (const [re, val] of segs) {
    const m = t.match(re);
    if (m) { actions.push({ kind: "segment", value: val }); said.push(val.toLowerCase()); eat(m); break; }
  }

  // 5+ hunt lanes
  const hunts: [RegExp, string][] = [
    [/\brooms in 5\+?\b/, "Rooms in 5+ homes"],
    [/\b5\+? ?(?:bed)? ?(?:whole )?(?:homes?|houses?)\b|\bwhole homes?\b/, "5+ whole homes"],
    [/\bexact sf 5\+?\b/, "Exact SF 5+"],
    [/\bpossible 5\+?\b/, "Possible 5+"],
  ];
  for (const [re, val] of hunts) {
    const m = t.match(re);
    if (m) { actions.push({ kind: "huntMode", value: val }); said.push(val); eat(m); break; }
  }

  // profile
  if (/\bgroup\b|\broommates? (?:mode|profile|search)\b|\bwith (?:the )?(?:group|roommates)\b/.test(t)) {
    actions.push({ kind: "profile", value: "group" });
    said.push("group profile");
  } else if (/\bsolo\b|\bjust (?:me|liam)\b|\bliam(?:'s)? (?:mode|profile|search)\b/.test(t)) {
    actions.push({ kind: "profile", value: "liam" });
    said.push("Liam (solo) profile");
  }

  // needs-review visibility
  if (/\b(?:show|include) (?:review|needs.?verification|unverified)\b/.test(t)) {
    actions.push({ kind: "showNeedsReview", value: true });
    said.push("including review-needed");
  } else if (/\b(?:hide|exclude) (?:review|needs.?verification|unverified)\b/.test(t)) {
    actions.push({ kind: "showNeedsReview", value: false });
    said.push("hiding review-needed");
  }

  // region — after point/near was stripped, so "near sunnyvale" doesn't also flip region.
  const regions: [RegExp, string][] = [
    [/\bsouth bay\b/, "South Bay"],
    [/\bpeninsula\b/, "Peninsula"],
    [/\b(?:in |only )sf\b|\bsan francisco only\b|\bsf only\b/, "SF"],
    [/\beverywhere\b|\ball (?:areas|regions)\b/, "All"],
  ];
  for (const [re, val] of regions) {
    const m = t.match(re);
    if (m) { actions.push({ kind: "region", value: val }); said.push(val === "All" ? "all regions" : `region: ${val}`); eat(m); break; }
  }

  // market — match remaining text against real market names ("in mountain view").
  const already = actions.some((a) => a.kind === "market");
  if (!already) {
    let best: { mkt: string; len: number } | null = null;
    for (const mkt of markets) {
      if (mkt === "All areas") continue;
      // Match the market name or any of its slash-parts ("Palo Alto/Menlo Park" → "menlo park").
      for (const part of mkt.toLowerCase().split("/")) {
        const p = part.trim();
        if (p.length >= 3 && t.includes(p) && (!best || p.length > best.len)) best = { mkt, len: p.length };
      }
    }
    if (best) { actions.push({ kind: "market", value: best.mkt }); said.push(`area: ${best.mkt}`); }
  }

  if (!actions.length) return null;
  return { actions, said };
}
