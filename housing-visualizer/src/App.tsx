import { useMemo, useState } from "react";
import rawData from "./data/housing-data.json";

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
  available: string;
  status: string;
  score: number;
  noCarScore: number;
  carScore: number;
  overallRank: number | null;
  cityRank: number | null;
  commuteMin: number | null;
  commuteHomeMin: number | null;
  carCommuteMin: number | null;
  howToGetThere: string;
  why: string;
  source: string;
  firstSeen: string;
  lastSeen: string;
  url: string;
  notes: string;
};

type Data = {
  generatedAt: string;
  stats: { total: number; active: number; needsVerification: number; replaced: number; markets: number };
  marketOrder: string[];
  listings: Listing[];
};

const data = rawData as unknown as Data;
const BIG = 1e9;

// "Today" = the most recent date any active listing was first seen (i.e. the latest
// refresh batch), so the New-today view stays meaningful even between runs.
const NEWEST = data.listings.reduce((m, l) => (l.status === "Active" && l.firstSeen > m ? l.firstSeen : m), "");
const isNew = (l: Listing) => l.status === "Active" && !!NEWEST && l.firstSeen === NEWEST;

const money = (n: number | null) => (n ? "$" + n.toLocaleString() : "no rent");
const isFlexLease = (s: string) => /sublet|sublease|month|m2m|short|temporary|flexible/i.test(s);
const isRoom = (l: Listing) => /\broom\b|roommate|\bshared?\b|private bath/i.test(`${l.title} ${l.lease}`);
const isApt = (l: Listing) =>
  /apartment|studio|\bcondo\b|townhouse|townhome|\bflat\b|\bunit\b|\d\s*(bd|br|bed|bedroom)/i.test(`${l.title} ${l.lease}`) ||
  !!l.beds;

const SOUTH = ["Mountain View", "Sunnyvale", "Santa Clara", "North San Jose"];
const PENINSULA = ["Palo Alto/Menlo Park", "Redwood City/San Carlos/Belmont", "San Mateo/Burlingame/Millbrae"];

type Scope = "active" | "needs" | "replaced";
const SEGMENTS: { key: string; scope: Scope; test: (l: Listing) => boolean }[] = [
  { key: "Top picks", scope: "active", test: () => true },
  { key: "New today", scope: "active", test: (l) => isNew(l) },
  { key: "Subleases / M2M", scope: "active", test: (l) => isFlexLease(l.lease) },
  { key: "Rooms", scope: "active", test: (l) => isRoom(l) },
  { key: "Apartments", scope: "active", test: (l) => isApt(l) && !isRoom(l) },
  { key: "SF", scope: "active", test: (l) => l.market.startsWith("SF ") },
  { key: "South Bay", scope: "active", test: (l) => SOUTH.includes(l.market) },
  { key: "Peninsula", scope: "active", test: (l) => PENINSULA.includes(l.market) },
  { key: "To verify", scope: "needs", test: () => true },
  { key: "Expired", scope: "replaced", test: () => true },
];

const SORTS: Record<string, (a: Listing, b: Listing) => number> = {
  "Best score": (a, b) => (a.overallRank ?? BIG) - (b.overallRank ?? BIG) || b.score - a.score,
  "Shortest commute": (a, b) => (a.commuteMin ?? BIG) - (b.commuteMin ?? BIG) || b.score - a.score,
  Cheapest: (a, b) => (a.allIn ?? a.rent ?? BIG) - (b.allIn ?? b.rent ?? BIG) || b.score - a.score,
  Newest: (a, b) => (b.firstSeen || "").localeCompare(a.firstSeen || "") || (b.lastSeen || "").localeCompare(a.lastSeen || ""),
};
const SORT_KEYS = Object.keys(SORTS);

const BEDS_OPTIONS = ["Any beds", "Studio", "1+ bd", "2+ bd", "3+ bd"];
const bedsPass = (l: Listing, opt: string) => {
  if (opt === "Any beds") return true;
  if (l.bedsNum == null) return false;
  if (opt === "Studio") return l.bedsNum === 0;
  return l.bedsNum >= parseInt(opt, 10);
};
const bedsLabel = (n: number | null) => (n == null ? "" : n === 0 ? "studio" : `${n} bd`);

function Score({ n }: { n: number }) {
  const tier = n >= 75 ? "hi" : n >= 60 ? "mid" : "lo";
  return <div className={`score ${tier}`}>{n}</div>;
}

function Card({ l, rank }: { l: Listing; rank?: number }) {
  const sub = [l.neighborhood || l.city, l.market, l.source].filter(Boolean).join(" · ");
  return (
    <article className="card">
      {rank != null && <div className="rank">{rank}</div>}
      <div className="body">
        <div className="head">
          <div className="name">
            {l.url ? (
              <a href={l.url} target="_blank" rel="noreferrer">
                {l.title || "(untitled)"}
              </a>
            ) : (
              l.title || "(untitled)"
            )}
            {isNew(l) && <span className="newbadge">NEW</span>}
            <div className="sub">
              {sub}
              {l.overallRank ? <span className="ov"> · overall #{l.overallRank}</span> : null}
            </div>
          </div>
          <Score n={l.score} />
        </div>
        <div className="chips">
          <span className="chip rent">{money(l.allIn ?? l.rent)}</span>
          {l.lease && <span className={isFlexLease(l.lease) ? "chip flex" : "chip"}>{l.lease}</span>}
          {(l.bedsNum != null || l.baths) && (
            <span className="chip">
              {bedsLabel(l.bedsNum)}
              {l.bedsNum != null && l.baths ? " · " : ""}
              {l.baths && `${l.baths} ba`}
            </span>
          )}
          {l.commuteMin != null && <span className="chip commute">⏱ {l.commuteMin}m to office</span>}
          {l.status !== "Active" && <span className="chip status">{l.status}</span>}
        </div>
        {l.howToGetThere && <div className="route">🚆 {l.howToGetThere}</div>}
      </div>
    </article>
  );
}

export default function App() {
  const [tab, setTab] = useState(SEGMENTS[0].key);
  const [sort, setSort] = useState(SORT_KEYS[0]);
  const [beds, setBeds] = useState(BEDS_OPTIONS[0]);
  const [q, setQ] = useState("");

  const pools = useMemo(() => {
    const active = data.listings.filter((l) => l.status === "Active");
    const needs = data.listings.filter((l) => l.status === "Needs Verification");
    const replaced = data.listings.filter((l) => !["Active", "Needs Verification"].includes(l.status));
    return { active, needs, replaced };
  }, []);

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const seg of SEGMENTS) c[seg.key] = pools[seg.scope].filter(seg.test).length;
    return c;
  }, [pools]);

  const seg = SEGMENTS.find((s) => s.key === tab)!;
  const rows = useMemo(() => {
    const match = (l: Listing) =>
      !q.trim() ||
      [l.title, l.market, l.city, l.neighborhood, l.lease, l.source].join(" ").toLowerCase().includes(q.toLowerCase());
    return pools[seg.scope]
      .filter(seg.test)
      .filter((l) => bedsPass(l, beds))
      .filter(match)
      .sort(SORTS[sort]);
  }, [pools, seg, sort, beds, q]);

  return (
    <div className="app">
      <header>
        <h1>Bay Area Housing</h1>
        <p className="tagline">
          Flexible-first power rankings near the HackerRank Santa Clara office · updated{" "}
          {new Date(data.generatedAt).toLocaleDateString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
        </p>
        <div className="stats">
          <Stat label="Active" value={data.stats.active} />
          <Stat label="Markets" value={data.stats.markets} />
          <Stat label="To verify" value={data.stats.needsVerification} />
          <Stat label="Expired" value={data.stats.replaced} />
        </div>
      </header>

      <div className="bar">
        <div className="bar-inner">
          <nav className="tabs">
            {SEGMENTS.map((s) => (
              <button key={s.key} className={s.key === tab ? "on" : ""} onClick={() => setTab(s.key)}>
                {s.key}
                <span className="tcount">{counts[s.key]}</span>
              </button>
            ))}
          </nav>
          <div className="controls">
            <input className="search" placeholder="Search title, city, neighborhood…" value={q} onChange={(e) => setQ(e.target.value)} />
            <select className="select" value={beds} onChange={(e) => setBeds(e.target.value)} aria-label="Bedrooms">
              {BEDS_OPTIONS.map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
            <select className="select" value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort by">
              {SORT_KEYS.map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      <main>
        {rows.length ? (
          <div className="list">
            {rows.map((l, i) => (
              <Card key={l.listingKey} l={l} rank={seg.scope === "active" ? i + 1 : undefined} />
            ))}
          </div>
        ) : (
          <div className="empty">No listings in “{tab}”{q ? ` matching “${q}”` : ""}.</div>
        )}
      </main>

      <footer>
        Showing {rows.length} of {data.stats.total} · read-only mirror of <code>housing-trackers/</code>
      </footer>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="stat">
      <div className="v">{value}</div>
      <div className="l">{label}</div>
    </div>
  );
}
