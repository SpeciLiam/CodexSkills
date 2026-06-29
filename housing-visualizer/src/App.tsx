import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import rawData from "./data/housing-data.json";
import { fetchRemoteMarks, upsertRemoteMark, deleteRemoteMark } from "./marksStore";

/* ──────────────────────────────────────────────────────────────────────────
   Bay Area Housing Hunt — implementation of Housing Hunt.dc.html
   Accent: deep blue (#245ea8). Reads the real housing-data.json mirror.
   ────────────────────────────────────────────────────────────────────────── */

const ACCENT = "#245ea8"; // deep blue
const DENSITY: "comfortable" | "compact" = "comfortable";

// Remember the visitor's last selections + per-listing marks in their browser.
const STORE_KEY = "hh-prefs-v1";
const MARKS_KEY = "hh-marks-v1"; // listingKey -> "checked" | "promising" | "skip"
const loadPrefs = (): Record<string, any> => {
  try { return JSON.parse(localStorage.getItem(STORE_KEY) || "{}"); } catch { return {}; }
};
const loadMarks = (): Record<string, string> => {
  try { return JSON.parse(localStorage.getItem(MARKS_KEY) || "{}"); } catch { return {}; }
};
const FALLBACK_PEOPLE: Person[] = [{ id: 1, name: "You", company: "HackerRank", address: "Santa Clara, CA" }];

const SF_KEY = "Google (San Francisco)";
const SC_KEY = "HackerRank (Santa Clara)";
const SOUTH = ["Mountain View", "Sunnyvale", "Santa Clara", "North San Jose"];
const PENINSULA = ["Palo Alto/Menlo Park", "Redwood City/San Carlos/Belmont", "San Mateo/Burlingame/Millbrae"];

type Listing = {
  listingKey: string;
  title: string;
  market: string;
  city: string;
  neighborhood: string;
  rent: number | null;
  allIn: number | null;
  beds: string;
  bedsNum: number | null;
  baths: string;
  lease: string;
  status: string;
  firstSeen: string;
  officeCommutes: Record<string, { transit: number; drive: number }>;
  source: string;
  url: string;
};
type Data = {
  generatedAt: string;
  stats: { active: number; markets: number };
  marketOrder: string[];
  listings: Listing[];
  defaultPeople?: { name: string; company: string; address: string }[];
};
type Person = { id: number; name: string; company: string; address: string };

const data = rawData as unknown as Data;

// Shared roommate config: the scrape's household.json seeds the dashboard's default
// people list (the visitor's own edits, saved below, take precedence).
const houseDefault: Person[] =
  data.defaultPeople && data.defaultPeople.length
    ? data.defaultPeople.map((p, i) => ({ id: i + 1, name: p.name || "Person " + (i + 1), company: p.company || "", address: p.address || "" }))
    : FALLBACK_PEOPLE;

const clamp = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, n));
const money = (n: number | null) => (n ? "$" + n.toLocaleString() : "no price");
const isFlex = (s: string) => /sublet|sublease|month|m2m|short|temporary|flexible/i.test(s || "");
const isRoom = (l: Listing) => /\broom\b|roommate|\bshared?\b|private bath/i.test(`${l.title} ${l.lease}`);
const isApt = (l: Listing) =>
  /apartment|studio|\bcondo\b|townhouse|townhome|\bflat\b|\bunit\b|\d\s*(bd|br|bed|bedroom)/i.test(`${l.title} ${l.lease}`) || !!l.beds;

function transitMethod(market: string) {
  if (/^SF /.test(market)) return "Caltrain + Muni";
  if (/Palo Alto|Redwood|San Mateo|Burlingame|Millbrae|Menlo/.test(market)) return "Caltrain";
  if (/Mountain View|Sunnyvale|Santa Clara|San Jose/.test(market)) return "VTA + Caltrain";
  return "transit";
}

// Map any company/address text to a geographic weight between SF (0) and Santa Clara (1),
// plus a few extra minutes for off-corridor spots. This is what lets the tool score a
// commute to ANY company, not just the two seed offices.
function geocode(text: string): { w: number; x: number; c: string; ok: boolean } {
  const t = (text || "").toLowerCase();
  const m = (...ks: string[]) => ks.some((k) => t.includes(k));
  if (m("oakland", "berkeley", "emeryville", "alameda", "hayward", "san leandro", "fremont", "union city", "newark", "dublin", "pleasanton", "walnut creek", "concord")) return { w: 0.5, x: 28, c: "East Bay", ok: true };
  if (m("marin", "sausalito", "san rafael", "novato", "mill valley")) return { w: 0.0, x: 24, c: "North Bay", ok: true };
  if (m("south san francisco")) return { w: 0.12, x: 4, c: "South SF", ok: true };
  if (m("daly city")) return { w: 0.1, x: 6, c: "Daly City", ok: true };
  if (m("san bruno")) return { w: 0.2, x: 2, c: "San Bruno", ok: true };
  if (m("millbrae")) return { w: 0.25, x: 0, c: "Millbrae", ok: true };
  if (m("burlingame")) return { w: 0.3, x: 0, c: "Burlingame", ok: true };
  if (m("san mateo")) return { w: 0.38, x: 0, c: "San Mateo", ok: true };
  if (m("belmont", "san carlos")) return { w: 0.45, x: 0, c: "San Carlos", ok: true };
  if (m("redwood city")) return { w: 0.5, x: 0, c: "Redwood City", ok: true };
  if (m("east palo alto")) return { w: 0.58, x: 4, c: "East Palo Alto", ok: true };
  if (m("menlo park")) return { w: 0.55, x: 0, c: "Menlo Park", ok: true };
  if (m("palo alto")) return { w: 0.6, x: 0, c: "Palo Alto", ok: true };
  if (m("los altos")) return { w: 0.66, x: 2, c: "Los Altos", ok: true };
  if (m("mountain view")) return { w: 0.72, x: 0, c: "Mountain View", ok: true };
  if (m("sunnyvale")) return { w: 0.8, x: 0, c: "Sunnyvale", ok: true };
  if (m("cupertino")) return { w: 0.86, x: 4, c: "Cupertino", ok: true };
  if (m("milpitas")) return { w: 0.9, x: 6, c: "Milpitas", ok: true };
  if (m("santa clara")) return { w: 1.0, x: 0, c: "Santa Clara", ok: true };
  if (m("north san jose")) return { w: 0.95, x: 0, c: "North San Jose", ok: true };
  if (m("campbell", "los gatos", "saratoga")) return { w: 0.95, x: 10, c: "West Valley", ok: true };
  if (m("san jose")) return { w: 0.97, x: 4, c: "San Jose", ok: true };
  if (m("san francisco", "soma", "mission bay", "mission district", "financial district", "nob hill", "hayes valley", "the castro", "sunset", "richmond district", "marina district", "potrero", "dogpatch", "embarcadero", "tenderloin")) return { w: 0.0, x: 0, c: "San Francisco", ok: true };
  return { w: 0.55, x: 8, c: "", ok: false };
}

function estimate(l: Listing, place: { w: number; x: number }, pref: string): { t: number | null; mode: string } {
  const oc = l.officeCommutes;
  if (!oc) return { t: null, mode: "transit" };
  const sf = oc[SF_KEY], sc = oc[SC_KEY];
  if (!sf || !sc) return { t: null, mode: "transit" };
  const w = place.w, x = place.x || 0;
  const transit = Math.round(sf.transit + (sc.transit - sf.transit) * w) + x;
  const drive = Math.round(sf.drive + (sc.drive - sf.drive) * w) + Math.round(x * 0.7);
  if (pref === "transit") return { t: transit, mode: "transit" };
  if (pref === "drive") return { t: drive, mode: "drive" };
  return { t: Math.min(transit, drive), mode: drive < transit ? "drive" : "transit" };
}

function resolvedText(company: string, address: string): { text: string; color: string } {
  if (((company || "") + (address || "")).trim() === "") return { text: "Enter a company or address", color: "#b0a99c" };
  const g = geocode((company || "") + " " + (address || ""));
  if (g.ok) return { text: "✓ placed near " + g.c, color: "var(--accent)" };
  return { text: "≈ couldn't place — estimating mid-Peninsula", color: "#b07d1a" };
}

const segPass = (l: Listing, seg: string, newest: string) => {
  if (seg === "All") return true;
  if (seg === "New today") return !!newest && l.firstSeen === newest;
  if (seg === "Subleases") return isFlex(l.lease);
  if (seg === "Rooms") return isRoom(l);
  if (seg === "Apartments") return isApt(l) && !isRoom(l);
  return true; // To verify / Expired — pool already scoped
};
const bedsPass = (l: Listing, opt: string) => {
  if (opt === "Any") return true;
  if (l.bedsNum == null) return false;
  if (opt === "Studio") return l.bedsNum === 0;
  return l.bedsNum >= parseInt(opt, 10);
};
const regionPass = (l: Listing, r: string) => {
  if (r === "All") return true;
  if (r === "SF") return /^SF /.test(l.market) || l.market === "SF";
  if (r === "Peninsula") return PENINSULA.includes(l.market);
  if (r === "South Bay") return SOUTH.includes(l.market);
  return true;
};
const matchQ = (l: Listing, q: string) =>
  !q.trim() || [l.title, l.market, l.city, l.neighborhood, l.lease, l.source].join(" ").toLowerCase().includes(q.toLowerCase());

const SEG_NAMES = ["All", "New today", "Subleases", "Rooms", "Apartments", "To verify", "Expired"];
const SORT_OPTIONS = ["Best fit", "Cheapest", "Shortest commute", "Newest"];
const BEDS_OPTIONS = ["Any", "Studio", "1+ bd", "2+ bd", "3+ bd", "4+ bd"];

// per-listing marks
const MARK_FILTERS = [
  { key: "active", label: "Active", tone: "#1c1a17" },
  { key: "promising", label: "★ Promising", tone: "var(--accent)" },
  { key: "checked", label: "✓ Checked out", tone: "#5a8f6a" },
  { key: "skip", label: "✕ Passed", tone: "#b4502f" },
  { key: "all", label: "All", tone: "#8a8378" },
];
const markChip = (on: boolean, tone: string): CSSProperties => ({
  cursor: "pointer", padding: "5px 11px", borderRadius: 999, fontSize: 12, fontWeight: 600,
  border: `1px solid ${on ? tone : "#e0dacd"}`,
  background: on ? `color-mix(in srgb, ${tone} 12%, #fff)` : "#fffdf8",
  color: on ? tone : "#8a8378",
});
const markBtn = (on: boolean, tone: string): CSSProperties => ({
  cursor: "pointer", padding: "4px 9px", borderRadius: 7, fontSize: 11.5, fontWeight: 600,
  border: `1px solid ${on ? tone : "#e6e1d6"}`,
  background: on ? `color-mix(in srgb, ${tone} 13%, #fff)` : "transparent",
  color: on ? tone : "#8a8378",
});

// shared inline style fragments
const sectionLabel: CSSProperties = {
  fontSize: 11, textTransform: "uppercase", letterSpacing: "0.08em", color: "#8a8378",
  fontWeight: 700, fontFamily: "'Space Grotesk',sans-serif",
};
const fieldStyle: CSSProperties = {
  width: "100%", border: "1px solid #e0dacd", background: "#fdfbf6", borderRadius: 10,
  padding: "9px 12px", fontSize: 13, color: "#1c1a17", outline: "none",
};
const selectStyle: CSSProperties = {
  flex: 1, minWidth: 0, border: "1px solid #e0dacd", background: "#fdfbf6", borderRadius: 10,
  padding: "9px 10px", fontSize: 13, fontWeight: 600, color: "#1c1a17", cursor: "pointer", outline: "none",
};

function Weight({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
        <span style={{ fontSize: 13, fontWeight: 600 }}>{label}</span>
        <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 12, fontWeight: 600, color: "var(--accent)" }}>{value}</span>
      </div>
      <input type="range" min={0} max={100} step={5} value={value} onChange={(e) => onChange(+e.target.value)} style={{ width: "100%" }} />
    </div>
  );
}

export default function App() {
  const [saved] = useState(loadPrefs);
  const [pref, setPref] = useState<string>(saved.pref ?? "fastest");
  const [people, setPeople] = useState<Person[]>(
    Array.isArray(saved.people) && saved.people.length ? saved.people : houseDefault
  );
  const [weights, setWeights] = useState<{ commute: number; price: number; flex: number }>(saved.weights ?? { commute: 60, price: 30, flex: 10 });
  const [q, setQ] = useState("");
  const [beds, setBeds] = useState<string>(saved.beds ?? "Any");
  const [market, setMarket] = useState<string>(saved.market ?? "All areas");
  const [source, setSource] = useState<string>(saved.source ?? "All sources");
  const [region, setRegion] = useState<string>(saved.region ?? "All");
  const [segment, setSegment] = useState<string>(saved.segment ?? "All");
  const [sort, setSort] = useState<string>(saved.sort ?? "Best fit");
  const [maxPrice, setMaxPrice] = useState<number>(saved.maxPrice ?? 3000);
  const [budgetCustom, setBudgetCustom] = useState<boolean>(saved.budgetCustom ?? false);
  const [markFilter, setMarkFilter] = useState<string>(saved.markFilter ?? "active");
  const [marks, setMarks] = useState<Record<string, string>>(loadMarks);

  const dense = DENSITY === "compact";
  const pad = dense ? "12px 15px" : "16px 17px";

  // Budget: rule of thumb is $3k per tenant; the visitor can override (custom) and that sticks.
  const tenants = people.length;
  const ruleOfThumb = 3000 * tenants;
  const budgetSliderMax = Math.max(8000, ruleOfThumb + 3000);
  const budget = budgetCustom ? Math.min(maxPrice, budgetSliderMax) : ruleOfThumb;
  const budgetIsAny = budget >= budgetSliderMax;

  // persist last selections (browser-local)
  useEffect(() => {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify({ pref, people, weights, beds, market, source, region, segment, sort, maxPrice, budgetCustom, markFilter }));
    } catch { /* storage unavailable — ignore */ }
  }, [pref, people, weights, beds, market, source, region, segment, sort, maxPrice, budgetCustom, markFilter]);
  useEffect(() => {
    try { localStorage.setItem(MARKS_KEY, JSON.stringify(marks)); } catch { /* ignore */ }
  }, [marks]);

  // Keys the user has toggled since mount — excluded from the load-merge so a fresh
  // edit made during the initial fetch isn't clobbered by the (stale) remote value.
  const touchedKeys = useRef<Set<string>>(new Set());

  // Cross-device sync: pull the durable marks from Supabase once on load and merge
  // them over the local cache (remote wins per key, except keys the user just touched).
  // Offline -> keep local.
  useEffect(() => {
    let alive = true;
    fetchRemoteMarks()
      .then((remote) => {
        if (!alive) return;
        setMarks((local) => {
          const out = { ...local };
          for (const k in remote) if (!touchedKeys.current.has(k)) out[k] = remote[k];
          return out;
        });
      })
      .catch(() => { /* offline / unreachable — localStorage stays the source */ });
    return () => { alive = false; };
  }, []);

  // toggle a per-listing mark; clicking the active mark clears it. Optimistic local
  // update + background push to the durable store (fire-and-forget; offline is fine).
  const setMark = (key: string, val: string) => {
    touchedKeys.current.add(key);
    setMarks((m) => {
      const n = { ...m };
      if (n[key] === val) { delete n[key]; deleteRemoteMark(key).catch(() => {}); }
      else { n[key] = val; upsertRemoteMark(key, val).catch(() => {}); }
      return n;
    });
  };
  // copy the current household so it can be pasted into household.json (drives the scrape)
  const copyScrapeConfig = () => {
    const cfg = JSON.stringify({ people: people.map((p) => ({ name: p.name, company: p.company, address: p.address })) }, null, 2);
    try { navigator.clipboard.writeText(cfg); } catch { /* ignore */ }
  };
  const markCounts = useMemo(() => {
    const c: Record<string, number> = { promising: 0, checked: 0, skip: 0 };
    for (const k in marks) if (c[marks[k]] != null) c[marks[k]]++;
    return c;
  }, [marks]);

  const setW = (k: "commute" | "price" | "flex", v: number) => setWeights((s) => ({ ...s, [k]: v }));
  const setPerson = (id: number, field: keyof Person, value: string) =>
    setPeople((s) => s.map((p) => (p.id === id ? { ...p, [field]: value } : p)));
  const removePerson = (id: number) => setPeople((s) => (s.length <= 1 ? s : s.filter((p) => p.id !== id)));
  const addPerson = () =>
    setPeople((s) => {
      const id = s.reduce((m, p) => Math.max(m, p.id), 0) + 1;
      return [...s, { id, name: "Roommate " + (s.length + 1), company: "", address: "" }];
    });

  const active = useMemo(() => data.listings.filter((l) => l.status === "Active"), []);
  const newest = useMemo(() => active.reduce((m, l) => (l.firstSeen > m ? l.firstSeen : m), ""), [active]);
  const sourceOptions = useMemo(() => ["All sources", ...Array.from(new Set(active.map((l) => l.source)))], [active]);
  const marketOptions = useMemo(() => ["All areas", ...(data.marketOrder || [])], []);

  const rows = useMemo(() => {
    const pool =
      segment === "To verify"
        ? data.listings.filter((l) => l.status === "Needs Verification")
        : segment === "Expired"
        ? data.listings.filter((l) => !["Active", "Needs Verification"].includes(l.status))
        : active;

    const sum = weights.commute + weights.price + weights.flex || 1;
    const wc = weights.commute / sum, wp = weights.price / sum, wf = weights.flex / sum;
    const roster = people;

    const list = pool
      .filter((l) => segPass(l, segment, newest))
      .filter((l) => bedsPass(l, beds))
      .filter((l) => market === "All areas" || l.market === market)
      .filter((l) => source === "All sources" || l.source === source)
      .filter((l) => regionPass(l, region))
      .filter((l) => {
        const p = l.allIn ?? l.rent;
        return p == null || budgetIsAny || p <= budget;
      })
      .filter((l) => matchQ(l, q))
      .filter((l) => {
        const mk = marks[l.listingKey];
        if (markFilter === "all") return true;
        if (markFilter === "active") return mk !== "skip"; // default: hide passed
        return mk === markFilter; // promising | checked | skip
      })
      .map((l) => {
        const per = roster.map((person) => {
          const g = geocode((person.company || "") + " " + (person.address || ""));
          const cm = estimate(l, g, pref);
          const dest = [person.company, g.c].filter(Boolean).join(" · ") || "their office";
          return { name: person.name || "—", t: cm.t, mode: cm.mode, dest };
        });
        const times = per.map((x) => x.t).filter((x): x is number => x != null);
        const avg = times.length ? times.reduce((a, b) => a + b, 0) / times.length : null;
        const max = times.length ? Math.max(...times) : null;
        const cScore = avg == null ? 0 : clamp((100 * (85 - avg)) / 70, 0, 100);
        const price = l.allIn ?? l.rent;
        const pScore = price == null ? 50 : clamp((100 * (4000 - price)) / 3300, 0, 100);
        const fScore = isFlex(l.lease) ? 100 : 50;
        const segC = wc * cScore, segP = wp * pScore, segF = wf * fScore;
        const fit = Math.round(segC + segP + segF);
        const tier = fit >= 70 ? "hi" : fit >= 52 ? "mid" : "lo";

        const routes = per.map((x) => {
          const isWorst = x.t != null && x.t === max && times.length > 1;
          return {
            name: x.name, dest: x.dest,
            timeLabel: x.t == null ? "n/a" : "~" + x.t + "m",
            timeColor: isWorst ? "#b4502f" : "#1c1a17",
            method: x.t == null ? "no route data" : x.mode === "drive" ? "drive" : transitMethod(l.market),
          };
        });

        const specBits: string[] = [];
        if (l.bedsNum != null) specBits.push(l.bedsNum === 0 ? "studio" : l.bedsNum + " bd");
        else if (l.beds) specBits.push(l.beds);
        if (l.baths) specBits.push(l.baths + " ba");

        const routesTitle =
          roster.length > 1
            ? "How everyone gets to work" + (avg == null ? "" : ` · ${Math.round(avg)}m avg, ${Math.round(max!)}m worst`)
            : "How you get there";

        return {
          id: l.listingKey, title: l.title || "(untitled)", url: l.url || "#",
          sub: [l.neighborhood || l.city, l.market, l.source].filter(Boolean).join(" · "),
          isNew: l.status === "Active" && !!newest && l.firstSeen === newest,
          priceLabel: money(price) + (price ? "/mo" : ""),
          leaseLabel: l.lease || "lease n/a",
          specLabel: specBits.join(" · "), hasSpec: specBits.length > 0,
          status: l.status, routes, routesTitle, mark: marks[l.listingKey] || "",
          fit, segC, segP, segF,
          fitFg: tier === "hi" ? "var(--accent)" : tier === "mid" ? "#b07d1a" : "#9a9384",
          _avg: avg == null ? 1e9 : avg, _price: price == null ? 1e9 : price, _first: l.firstSeen || "", _score: fit,
        };
      });

    const SB: Record<string, (a: typeof list[number], b: typeof list[number]) => number> = {
      "Best fit": (a, b) => b._score - a._score || a._avg - b._avg,
      Cheapest: (a, b) => a._price - b._price || b._score - a._score,
      "Shortest commute": (a, b) => a._avg - b._avg || b._score - a._score,
      Newest: (a, b) => (b._first || "").localeCompare(a._first || "") || b._score - a._score,
    };
    list.sort(SB[sort] || SB["Best fit"]);
    return list;
  }, [active, newest, people, weights, q, beds, market, source, region, segment, sort, budget, budgetIsAny, pref, marks, markFilter]);

  const prefBtn = (k: string): CSSProperties => {
    const on = pref === k;
    return {
      flex: 1, cursor: "pointer", padding: "7px 4px", borderRadius: 8, fontSize: 12, fontWeight: 600,
      border: `1px solid ${on ? "var(--accent)" : "#e0dacd"}`, background: on ? "var(--accent)" : "#fffdf8", color: on ? "#fffdf8" : "#6f6a61",
    };
  };
  const chip = (on: boolean, dark = true): CSSProperties => ({
    cursor: "pointer", padding: "7px 14px", borderRadius: 999, fontSize: 13, fontWeight: 600,
    border: `1px solid ${on ? (dark ? "#1c1a17" : "var(--accent)") : "#e0dacd"}`,
    background: on ? (dark ? "#1c1a17" : "color-mix(in srgb, var(--accent) 12%, #fff)") : "#fffdf8",
    color: on ? (dark ? "#fffdf8" : "var(--accent)") : "#6f6a61",
  });

  const counts = useMemo(() => {
    const needs = data.listings.filter((l) => l.status === "Needs Verification").length;
    const expired = data.listings.filter((l) => !["Active", "Needs Verification"].includes(l.status)).length;
    return { needs, expired };
  }, []);

  const viewLabel = segment === "All" ? "All listings" : segment;
  const updated = data.generatedAt
    ? new Date(data.generatedAt).toLocaleDateString(undefined, { month: "short", day: "numeric" })
    : "–";

  return (
    <div style={{ ["--accent" as any]: ACCENT, minHeight: "100vh", display: "flex", flexDirection: "column" } as CSSProperties}>
      {/* header */}
      <header
        style={{
          display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 24,
          padding: "20px 28px 18px", background: "#fffdf8", borderBottom: "1px solid #e6e1d6", flexWrap: "wrap",
        }}
      >
        <div style={{ display: "flex", alignItems: "flex-start", gap: 14 }}>
          <div style={{ width: 38, height: 38, borderRadius: 11, background: "var(--accent)", display: "flex", alignItems: "center", justifyContent: "center", flex: "0 0 auto", marginTop: 2 }}>
            <div style={{ width: 13, height: 13, border: "2.5px solid #fffdf8", borderRadius: 3 }} />
          </div>
          <div>
            <h1 style={{ margin: 0, fontFamily: "'Space Grotesk',sans-serif", fontSize: 23, fontWeight: 700, letterSpacing: "-0.4px", lineHeight: 1 }}>
              Bay Area Housing Hunt
            </h1>
            <p style={{ margin: "6px 0 0", fontSize: 13, color: "#6f6a61" }}>Scraped listings, ranked by who has to commute · updated {updated}</p>
          </div>
        </div>
        <div style={{ display: "flex", gap: 22 }}>
          <Stat value={data.stats.active} label="Active" />
          <Stat value={data.stats.markets} label="Markets" />
        </div>
      </header>

      <div className="hh-grid" style={{ display: "grid", gridTemplateColumns: "344px minmax(0,1fr)", flex: 1, alignItems: "start" }}>
        {/* SIDEBAR */}
        <aside className="hh-aside" style={{ position: "sticky", top: 0, height: "100vh", overflowY: "auto", background: "#fffdf8", borderRight: "1px solid #e6e1d6", padding: "20px 20px 40px" }}>
          <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8, marginBottom: 4 }}>
            <div style={sectionLabel}>Who's commuting</div>
            <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 11, fontWeight: 600, color: "#b0a99c" }}>
              {people.length} {people.length === 1 ? "person" : "people"}
            </div>
          </div>
          <div style={{ fontSize: 12.5, color: "#6f6a61", marginBottom: 10 }}>
            {people.length > 1 ? "Ranked by how everyone gets to work." : "Where do you work? Commute is scored to here."}
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 9, marginBottom: 10 }}>
            {people.map((p, idx) => {
              const rt = resolvedText(p.company, p.address);
              const lead = idx === 0;
              return (
                <div key={p.id} style={{ border: lead ? "1.5px solid var(--accent)" : "1px solid #e6e1d6", borderRadius: 12, padding: "10px 11px", background: lead ? "color-mix(in srgb, var(--accent) 6%, #fffdf8)" : "#fdfbf6" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                    <div style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--accent)", flex: "0 0 auto" }} />
                    <input value={p.name} onChange={(e) => setPerson(p.id, "name", e.target.value)} placeholder="Name" style={{ flex: 1, minWidth: 0, border: "none", background: "transparent", fontSize: 14, fontWeight: 600, color: "#1c1a17", outline: "none", padding: 0 }} />
                    {people.length > 1 && (
                      <button onClick={() => removePerson(p.id)} title="Remove" style={{ border: "none", background: "transparent", cursor: "pointer", color: "#b0a99c", fontSize: 17, lineHeight: 1, padding: "0 2px" }}>×</button>
                    )}
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <input value={p.company} onChange={(e) => setPerson(p.id, "company", e.target.value)} placeholder="Company name" style={{ ...fieldStyle, borderRadius: 8, padding: "7px 9px", fontSize: 12.5, fontWeight: 600 }} />
                    <input value={p.address} onChange={(e) => setPerson(p.id, "address", e.target.value)} placeholder="Work address or city" style={{ ...fieldStyle, borderRadius: 8, padding: "7px 9px", fontSize: 12 }} />
                    <div style={{ fontSize: 11, fontWeight: 600, color: rt.color }}>{rt.text}</div>
                  </div>
                </div>
              );
            })}
            <button onClick={addPerson} style={{ border: "1.5px dashed #d4cdbf", background: "transparent", cursor: "pointer", padding: 10, borderRadius: 11, fontSize: 13, fontWeight: 600, color: "#6f6a61" }}>
              + Add a roommate
            </button>
            <button onClick={copyScrapeConfig} title="Copy this household as JSON to paste into scripts/household.json — that's what the scraper searches for" style={{ border: "none", background: "transparent", cursor: "pointer", padding: "2px 2px", fontSize: 11.5, fontWeight: 600, color: "var(--accent)", textAlign: "left" }}>
              ⧉ Copy as scrape config
            </button>
          </div>

          {/* pref mode */}
          <div style={{ display: "flex", gap: 6, margin: "14px 0 22px" }}>
            <button onClick={() => setPref("fastest")} style={prefBtn("fastest")}>Fastest</button>
            <button onClick={() => setPref("transit")} style={prefBtn("transit")}>Transit</button>
            <button onClick={() => setPref("drive")} style={prefBtn("drive")}>Drive</button>
          </div>

          {/* weights */}
          <div style={{ ...sectionLabel, marginBottom: 14 }}>What matters most</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 16, marginBottom: 24 }}>
            <Weight label="Short commute" value={weights.commute} onChange={(v) => setW("commute", v)} />
            <Weight label="Low price" value={weights.price} onChange={(v) => setW("price", v)} />
            <Weight label="Flexible lease" value={weights.flex} onChange={(v) => setW("flex", v)} />
          </div>

          {/* filters */}
          <div style={{ ...sectionLabel, marginBottom: 12 }}>Narrow it down</div>
          <div style={{ display: "flex", gap: 6, marginBottom: 11, flexWrap: "wrap" }}>
            {["All", "SF", "Peninsula", "South Bay"].map((name) => (
              <button key={name} onClick={() => setRegion(name)} style={{ ...chip(region === name, false), padding: "6px 13px", fontSize: 12.5 }}>{name}</button>
            ))}
          </div>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search title, neighborhood…" style={{ ...fieldStyle, padding: "10px 12px", fontSize: 13.5, marginBottom: 10 }} />
          <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
            <select value={beds} onChange={(e) => setBeds(e.target.value)} style={selectStyle}>
              {BEDS_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
            <select value={market} onChange={(e) => setMarket(e.target.value)} style={selectStyle}>
              {marketOptions.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          </div>
          <select value={source} onChange={(e) => setSource(e.target.value)} style={{ ...selectStyle, width: "100%", marginBottom: 10 }}>
            {sourceOptions.map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>Budget — max all-in</span>
            <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 12, fontWeight: 700, color: budgetCustom ? "var(--accent)" : "#6f6a61" }}>{budgetIsAny ? "Any" : "$" + budget.toLocaleString()}</span>
          </div>
          <input type="range" min={500} max={budgetSliderMax} step={100} value={Math.min(budget, budgetSliderMax)} onChange={(e) => { setMaxPrice(+e.target.value); setBudgetCustom(true); }} style={{ width: "100%" }} />
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8, marginTop: 5 }}>
            <span style={{ fontSize: 11, color: "#8a8378" }}>
              Rule of thumb <strong style={{ color: "#6f6a61", fontWeight: 700 }}>$3k × {tenants}</strong> {tenants === 1 ? "tenant" : "tenants"} = ${ruleOfThumb.toLocaleString()}
            </span>
            {budgetCustom && (
              <button onClick={() => setBudgetCustom(false)} style={{ border: "none", background: "transparent", cursor: "pointer", fontSize: 11, fontWeight: 600, color: "var(--accent)", padding: 0, whiteSpace: "nowrap" }}>↺ reset</button>
            )}
          </div>
        </aside>

        {/* MAIN */}
        <main style={{ padding: "20px 26px 60px" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 14, marginBottom: 18, flexWrap: "wrap" }}>
            <div style={{ display: "flex", gap: 7, flexWrap: "wrap" }}>
              {SEG_NAMES.map((name) => {
                const c = name === "To verify" ? counts.needs : name === "Expired" ? counts.expired : null;
                return (
                  <button key={name} onClick={() => setSegment(name)} style={chip(segment === name)}>
                    {name}{c != null ? ` ${c}` : ""}
                  </button>
                );
              })}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 12, color: "#8a8378", fontWeight: 600 }}>Sort</span>
              <select value={sort} onChange={(e) => setSort(e.target.value)} style={{ border: "1px solid #e0dacd", background: "#fffdf8", borderRadius: 9, padding: "7px 10px", fontSize: 13, fontWeight: 600, color: "#1c1a17", cursor: "pointer", outline: "none" }}>
                {SORT_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, marginBottom: 14, flexWrap: "wrap" }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
              <span style={{ fontFamily: "'Space Grotesk',sans-serif", fontSize: 15, fontWeight: 600 }}>{viewLabel}</span>
              <span style={{ fontSize: 13, color: "#8a8378" }}>{rows.length} homes · ranked by best fit</span>
            </div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {MARK_FILTERS.map((mf) => (
                <button key={mf.key} onClick={() => setMarkFilter(mf.key)} style={markChip(markFilter === mf.key, mf.tone)}>
                  {mf.label}{(mf.key === "promising" || mf.key === "checked" || mf.key === "skip") ? ` ${markCounts[mf.key] || 0}` : ""}
                </button>
              ))}
            </div>
          </div>

          {rows.length === 0 ? (
            <div style={{ textAlign: "center", color: "#8a8378", padding: "54px 20px", border: "1px dashed #d8d1c3", borderRadius: 15, background: "#fffdf8" }}>
              No homes match these filters. Try widening the price or area.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {rows.map((r, i) => (
                <article key={r.id} style={{ display: "grid", gridTemplateColumns: "34px 1fr auto", gap: 14, alignItems: "start", background: r.mark === "checked" ? "#fbf9f3" : "#fffdf8", border: r.mark === "promising" ? "1.5px solid var(--accent)" : "1px solid #e6e1d6", borderRadius: 15, padding: pad, boxShadow: "0 1px 2px rgba(28,26,23,0.03)", opacity: r.mark === "skip" ? 0.6 : 1 }}>
                  <div style={{ fontFamily: "'Space Grotesk',sans-serif", fontSize: 15, fontWeight: 700, color: "#b8b1a2", textAlign: "center", fontVariantNumeric: "tabular-nums", paddingTop: 2 }}>{i + 1}</div>

                  <div style={{ minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                      <a href={r.url} target="_blank" rel="noreferrer" style={{ fontSize: 15, fontWeight: 650, color: "#1c1a17", textDecoration: "none", lineHeight: 1.3 }}>{r.title}</a>
                      {r.isNew && <span style={{ fontSize: 9.5, fontWeight: 800, letterSpacing: "0.06em", color: "var(--accent)", background: "color-mix(in srgb, var(--accent) 14%, #fff)", padding: "2px 6px", borderRadius: 5 }}>NEW</span>}
                      {r.status !== "Active" && <span style={{ fontSize: 9.5, fontWeight: 800, letterSpacing: "0.06em", color: "#b4502f", background: "#f8ece6", padding: "2px 6px", borderRadius: 5 }}>{r.status.toUpperCase()}</span>}
                    </div>
                    <div style={{ fontSize: 12.5, color: "#8a8378", marginTop: 3 }}>{r.sub}</div>

                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 10 }}>
                      <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 12, fontWeight: 600, padding: "4px 9px", borderRadius: 7, background: "color-mix(in srgb, var(--accent) 11%, #fff)", color: "var(--accent)" }}>{r.priceLabel}</span>
                      <span style={{ fontSize: 12, fontWeight: 600, padding: "4px 9px", borderRadius: 7, background: "#efece6", color: "#5a554c" }}>{r.leaseLabel}</span>
                      {r.hasSpec && <span style={{ fontSize: 12, fontWeight: 600, padding: "4px 9px", borderRadius: 7, background: "#efece6", color: "#5a554c" }}>{r.specLabel}</span>}
                    </div>

                    <div style={{ marginTop: 10, paddingTop: 9, borderTop: "1px solid #f0ece3" }}>
                      <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: "0.06em", color: "#b0a99c", fontWeight: 700, marginBottom: 5 }}>{r.routesTitle}</div>
                      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        {r.routes.map((rt, j) => (
                          <div key={j} style={{ display: "flex", alignItems: "baseline", gap: 7, fontSize: 12.5, flexWrap: "wrap" }}>
                            <span style={{ fontWeight: 700, color: "#1c1a17" }}>{rt.name}</span>
                            <span style={{ color: "#c2bbac" }}>→</span>
                            <span style={{ color: "#6f6a61" }}>{rt.dest}</span>
                            <span style={{ color: "#d8d1c3" }}>·</span>
                            <span style={{ fontFamily: "'JetBrains Mono',monospace", fontWeight: 600, color: rt.timeColor }}>{rt.timeLabel}</span>
                            <span style={{ color: "#8a8378" }}>{rt.method}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* mark this listing */}
                    <div style={{ display: "flex", gap: 6, marginTop: 11, flexWrap: "wrap" }}>
                      <button onClick={() => setMark(r.id, "checked")} style={markBtn(r.mark === "checked", "#5a8f6a")}>✓ Checked out</button>
                      <button onClick={() => setMark(r.id, "promising")} style={markBtn(r.mark === "promising", "var(--accent)")}>★ Promising</button>
                      <button onClick={() => setMark(r.id, "skip")} style={markBtn(r.mark === "skip", "#b4502f")}>✕ Not for me</button>
                    </div>
                  </div>

                  {/* fit */}
                  <div style={{ textAlign: "right", minWidth: 104, display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 7 }}>
                    <div style={{ display: "flex", alignItems: "baseline", gap: 5 }}>
                      <span style={{ fontFamily: "'Space Grotesk',sans-serif", fontSize: 26, fontWeight: 700, lineHeight: 1, fontVariantNumeric: "tabular-nums", color: r.fitFg }}>{r.fit}</span>
                      <span style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em", color: "#b0a99c", fontWeight: 700 }}>fit</span>
                    </div>
                    <div style={{ width: 104, height: 7, borderRadius: 5, background: "#ece8df", overflow: "hidden", display: "flex" }}>
                      <span style={{ height: "100%", width: `${r.segC}%`, background: "var(--accent)" }} />
                      <span style={{ height: "100%", width: `${r.segP}%`, background: "#8aa1b8" }} />
                      <span style={{ height: "100%", width: `${r.segF}%`, background: "#cbb588" }} />
                    </div>
                    <div style={{ fontSize: 10, color: "#b0a99c", lineHeight: 1.4, textAlign: "right" }}>commute · price · lease</div>
                  </div>
                </article>
              ))}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

function Stat({ value, label }: { value: number; label: string }) {
  return (
    <div style={{ textAlign: "right" }}>
      <div style={{ fontFamily: "'Space Grotesk',sans-serif", fontSize: 22, fontWeight: 700, lineHeight: 1, fontVariantNumeric: "tabular-nums" }}>{value}</div>
      <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: "0.07em", color: "#8a8378", fontWeight: 600, marginTop: 4 }}>{label}</div>
    </div>
  );
}
