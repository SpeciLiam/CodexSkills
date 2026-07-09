import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import rawData from "./data/housing-data.json";
import { fetchRemoteMarks, upsertRemoteMark, deleteRemoteMark } from "./marksStore";
import { fetchConfig, saveConfig } from "./configStore";
import RadarChart from "./RadarChart";
import { MAIN_AXES, SF_AXES, listingAxisKey, DEFAULT_REGION_VALUES, regionBoost } from "./regions";
import { resolvePoint, marketCentroids, listingDistanceMiles, fmtMiles, type Point } from "./pointSearch";
import { pickInspiration } from "./inspire";
import { parseCommand } from "./agent";
import AgentPanel from "./AgentPanel";

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
// Liam's profile is fixed to the HackerRank office.
const LIAM_OFFICE = "2350 Mission College Blvd #750, Santa Clara, CA 95054";
const DEFAULT_LIAM: Person = { id: 0, name: "Liam", company: "HackerRank", address: LIAM_OFFICE, arrival: "09:00", car: true, bike: true };
const FALLBACK_PEOPLE: Person[] = [{ id: 1, name: "Liam", company: "HackerRank", address: LIAM_OFFICE, arrival: "09:00", car: true, bike: true }];

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
  isFivePlus?: boolean;
  unitScope?: "whole" | "room" | "unknown" | string;
  baths: string;
  lease: string;
  available?: string;
  status: string;
  firstSeen: string;
  lastSeen?: string;
  officeCommutes?: Record<string, { transit: number; drive: number }>;
  commuteOrigin?: string; // python-derived geocodable origin (matches the cached commute)
  source: string;
  sourceTier?: string;
  sourceHealth?: string;
  sfMarket?: boolean;
  exactSf?: boolean;
  strictSfCity?: boolean;
  locationConfidence?: string;
  score?: number;
  fitTier?: string; // pipeline fit band: Great / Good / Fair / Weak
  scoreBreakdown?: {
    value?: number; flexibility?: number; flexibilityReason?: string; quality?: number;
    confidence?: number; neighborhood?: number; commuteNoCar?: number; commuteCar?: number;
    perPersonRent?: number | null; fitTier?: string;
  };
  noCarScore?: number;
  carScore?: number;
  overallRank?: number | null;
  cityRank?: number | null;
  commuteMin?: number | null;
  carCommuteMin?: number | null;
  commuteSource?: string;
  howToGetThere?: string;
  why?: string;
  notes?: string;
  url: string;
};
type CfgPerson = { name: string; company: string; address: string; arrival?: string; car?: boolean; bike?: boolean };
type Data = {
  generatedAt: string;
  dashboardBuiltAt?: string;
  pipelineRunAt?: string | null;
  runHealth?: {
    overall?: string;
    finishedAt?: string;
    summary?: Record<string, number>;
    sources?: Array<{
      id: string; tier: string; name: string; label?: string; status: string;
      recordCount?: number; blockedCount?: number; lastAttemptAt?: string | null;
      lastSuccessAt?: string | null; message?: string; selectedThisRun?: boolean;
    }>;
  } | null;
  searchDefaults?: { needStart?: string; minimumStayDays?: number; rtoDays?: string[]; timezone?: string };
  groupSearch?: { targetBedrooms?: number; budgetPerPerson?: number; totalBudget?: number; searchArea?: string };
  stats: {
    active: number; markets: number; total?: number; needsVerification?: number; replaced?: number; googleCommutes?: number;
    activeFivePlus?: number; sfMarketFivePlus?: number; strictSfCityFivePlus?: number; exactSfFivePlus?: number;
  };
  marketOrder: string[];
  listings: Listing[];
  defaultPeople?: CfgPerson[]; // group profile
  defaultLiam?: CfgPerson; // liam (solo) profile
};
type Person = { id: number; name: string; company: string; address: string; arrival: string; car: boolean; bike: boolean };

const data = rawData as unknown as Data;
const GROUP_SEARCH = {
  targetBedrooms: data.groupSearch?.targetBedrooms || 5,
  budgetPerPerson: data.groupSearch?.budgetPerPerson || 2650,
  totalBudget: data.groupSearch?.totalBudget || 13250,
  searchArea: data.groupSearch?.searchArea || "San Francisco only",
};
const LIAM_DEFAULT_BUDGET = 3750;
const REMOTE_AGENT_ENABLED = import.meta.env.DEV || import.meta.env.VITE_ENABLE_REMOTE_AGENT === "true";
const REMOTE_SYNC_ENABLED = import.meta.env.DEV || import.meta.env.VITE_ENABLE_REMOTE_SYNC === "true";
const toPerson = (p: CfgPerson, id: number): Person => ({
  id, name: p.name || "Person " + id, company: p.company || "", address: p.address || "",
  arrival: p.arrival || "09:00", car: p.car ?? true, bike: p.bike ?? true,
});

// household.json seeds the dashboard's default people (the visitor's own edits, saved
// below, take precedence). Two profiles: Liam (solo, HackerRank) + Group (editable).
const groupDefault: Person[] =
  data.defaultPeople && data.defaultPeople.length ? data.defaultPeople.map((p, i) => toPerson(p, i + 1)) : FALLBACK_PEOPLE;
const liamDefault: Person = data.defaultLiam ? toPerson(data.defaultLiam, 0) : DEFAULT_LIAM;

const clamp = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, n));
const money = (n: number | null) => (n == null ? "no price" : "$" + n.toLocaleString());
const NEED_START_ISO = data.searchDefaults?.needStart || "2026-07-16";
const NEED_START = new Date(`${NEED_START_ISO}T00:00:00`);
const NEED_YEAR = NEED_START.getFullYear();
const DAY_MS = 86400000;

const compactTitle = (s: string) =>
  (s || "")
    .toLowerCase()
    .replace(/[$]\s*\d[\d,]*/g, "")
    .replace(/\b(apt|apartment|bedroom|bed|bathroom|bath)\b/g, (m) => ({ apt: "apartment", bedroom: "bed", bathroom: "bath" }[m] || m))
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
    .slice(0, 64);
const clusterKey = (l: Listing) => `${l.market}|${Math.round(((l.allIn ?? l.rent ?? 0) || 0) / 50)}|${compactTitle(l.title)}`;
const daysBetween = (a?: string, b?: string) => {
  if (!a || !b) return null;
  const da = Date.parse(a), db = Date.parse(b);
  if (Number.isNaN(da) || Number.isNaN(db)) return null;
  return Math.max(0, Math.floor((db - da) / DAY_MS));
};
const ago = (days: number | null, today = "today") => {
  if (days == null) return "";
  if (days === 0) return today;
  return `${days}d ago`;
};
const fmtDate = (d: Date) => d.toLocaleDateString(undefined, { month: "short", day: "numeric" });

const MONTHS: Record<string, number> = {
  jan: 0, january: 0, feb: 1, february: 1, mar: 2, march: 2, apr: 3, april: 3, may: 4,
  jun: 5, june: 5, jul: 6, july: 6, aug: 7, august: 7, sep: 8, sept: 8, september: 8,
  oct: 9, october: 9, nov: 10, november: 10, dec: 11, december: 11,
};
function parseMonthDay(month: string, day: string, year?: string) {
  const m = MONTHS[month.toLowerCase()];
  const d = parseInt(day, 10);
  if (m == null || Number.isNaN(d)) return null;
  return new Date(parseInt(year || String(NEED_YEAR), 10), m, d);
}
function termEndFromText(text: string): Date | null {
  const t = text || "";
  const long = new RegExp(`\\b(${Object.keys(MONTHS).join("|")})\\s+(\\d{1,2})(?:st|nd|rd|th)?(?:,?\\s*(20\\d{2}))?\\s*(?:-|–|—|to|through|until)\\s*(?:(${Object.keys(MONTHS).join("|")})\\s+)?(\\d{1,2})(?:st|nd|rd|th)?(?:,?\\s*(20\\d{2}))?`, "i");
  const m = t.match(long);
  if (m) return parseMonthDay(m[4] || m[1], m[5], m[6] || m[3]);
  const numeric = t.match(/\b(\d{1,2})\/(\d{1,2})\s*(?:-|–|—|to|through|until)\s*(\d{1,2})\/(\d{1,2})\b/i);
  if (numeric) return new Date(NEED_YEAR, parseInt(numeric[3], 10) - 1, parseInt(numeric[4], 10));
  return null;
}
function stayRangeDays(text: string): number | null {
  const t = text || "";
  const long = new RegExp(`\\b(${Object.keys(MONTHS).join("|")})\\s+(\\d{1,2})(?:st|nd|rd|th)?(?:,?\\s*(20\\d{2}))?\\s*(?:-|–|—|to|through|until)\\s*(?:(${Object.keys(MONTHS).join("|")})\\s+)?(\\d{1,2})(?:st|nd|rd|th)?(?:,?\\s*(20\\d{2}))?`, "i");
  const m = t.match(long);
  if (m) {
    const start = parseMonthDay(m[1], m[2], m[3]);
    const end = parseMonthDay(m[4] || m[1], m[5], m[6] || m[3]);
    if (start && end) return Math.max(1, Math.round((end.getTime() - start.getTime()) / DAY_MS));
  }
  const numeric = t.match(/\b(\d{1,2})\/(\d{1,2})\s*(?:-|–|—|to|through|until)\s*(\d{1,2})\/(\d{1,2})\b/i);
  if (numeric) {
    const start = new Date(NEED_YEAR, parseInt(numeric[1], 10) - 1, parseInt(numeric[2], 10));
    const end = new Date(NEED_YEAR, parseInt(numeric[3], 10) - 1, parseInt(numeric[4], 10));
    return Math.max(1, Math.round((end.getTime() - start.getTime()) / DAY_MS));
  }
  return null;
}
const titleMoney = (text: string) => {
  const m = (text || "").match(/\$\s*([\d,]+)/);
  return m ? parseInt(m[1].replace(/,/g, ""), 10) : null;
};
function honestRentLabel(l: Listing) {
  const text = `${l.title} ${l.notes || ""} ${l.why || ""}`;
  const price = l.allIn ?? l.rent;
  const explicit = titleMoney(l.title) ?? price;
  if (explicit != null && /\b(weekly|per week|a week|\/\s*wk|\/wk|\bwk\b)\b/i.test(text)) {
    return `${money(explicit)}/wk ≈ ${money(Math.round(explicit * 4.33))}/mo`;
  }
  if (explicit != null && /\b(nightly|per night|a night|\/\s*night|\/night|\/\s*nt|\/nt|daily|per day)\b/i.test(text)) {
    return `${money(explicit)}/nt ≈ ${money(Math.round(explicit * 30.44))}/mo`;
  }
  const days = stayRangeDays(l.title);
  if (explicit != null && days != null && days > 0 && days < 30) {
    return `${money(explicit)}/${days}d ≈ ${money(Math.round((explicit / days) * 30.44))}/mo`;
  }
  return money(price) + (price != null ? "/mo" : "");
}
const isScamRisk = (l: Listing) =>
  /\bscam[-\s]?risk\b/i.test(`${l.notes || ""} ${l.why || ""}`) ||
  (l.status === "Needs Verification" && /state-of-the-art|whatsapp|text only|hold the unit|no viewing/i.test(`${l.notes || ""} ${l.why || ""} ${l.title}`)) ||
  (/state-of-the-art/i.test(l.title) && /\b(weekly|\/\s*wk|\/wk)\b/i.test(l.title));
function commuteChip(l: Listing) {
  const source = (l.commuteSource || "").toLowerCase();
  const text = `${l.howToGetThere || ""} ${l.why || ""}`;
  if (source === "google" || /Google Maps/i.test(text)) return { label: "Google", tone: "#4f8060", bg: "#eef6ef" };
  if (source === "geo-estimate" || source === "geo") return { label: "geo est", tone: "#8a681f", bg: "#fbf1dd" };
  return { label: /\(est\)/i.test(text) ? "region est" : "region est", tone: "#8a8378", bg: "#f5f1e8" };
}
// Flexible / sublease term. The pipeline rarely populates l.lease, so callers pass the
// title too. Word-bounded, specific tokens so a normal "short walk"/"this month" title
// isn't mis-flagged (avoids bare "month"/"short").
const isFlex = (s: string) => /\b(sublet|subleas|short[\s-]?term|month[\s-]?to[\s-]?month|m2m|temporary|flexible)\b/i.test(s || "");
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
  if (m("san francisco", "san fran", "frisco", "soma", "mission bay", "mission district", "financial district", "nob hill", "hayes valley", "the castro", "sunset", "richmond district", "marina district", "potrero", "dogpatch", "embarcadero", "tenderloin") || /\bsf\b/.test(t)) return { w: 0.0, x: 0, c: "San Francisco", ok: true };
  return { w: 0.55, x: 8, c: "", ok: false };
}

function estimate(l: Listing, place: { w: number; x: number }, pref: string, hasCar = true): { t: number | null; mode: string } {
  const oc = l.officeCommutes;
  if (!oc) return { t: null, mode: "transit" };
  const sf = oc[SF_KEY], sc = oc[SC_KEY];
  if (!sf || !sc) return { t: null, mode: "transit" };
  const w = place.w, x = place.x || 0;
  const transit = Math.round(sf.transit + (sc.transit - sf.transit) * w) + x;
  const drive = Math.round(sf.drive + (sc.drive - sf.drive) * w) + Math.round(x * 0.7);
  if (pref === "transit" || !hasCar) return { t: transit, mode: "transit" }; // no car -> transit only
  if (pref === "drive") return { t: drive, mode: "drive" };
  return { t: Math.min(transit, drive), mode: drive < transit ? "drive" : "transit" };
}

function resolvedText(company: string, address: string): { text: string; color: string } {
  if (((company || "") + (address || "")).trim() === "") return { text: "Enter a company or address", color: "#b0a99c" };
  const g = geocode((company || "") + " " + (address || ""));
  if (g.ok) return { text: "✓ placed near " + g.c, color: "var(--accent)" };
  return { text: "≈ couldn't place — estimating mid-Peninsula", color: "#b07d1a" };
}

// ── Optimal-departure (live Google Routes via /api/commute) ──────────────────
const OFFICE_DAYS = [1, 3, 4]; // Mon, Wed, Thu (RTO). Computed in the browser (Pacific).
function nextOfficeArrivalISO(hhmm: string): string {
  const [h, m] = (hhmm || "09:00").split(":").map((n) => parseInt(n, 10));
  const now = new Date();
  for (let i = 0; i < 8; i++) {
    const c = new Date(now);
    c.setDate(now.getDate() + i);
    c.setHours(isNaN(h) ? 9 : h, isNaN(m) ? 0 : m, 0, 0);
    if (OFFICE_DAYS.includes(c.getDay()) && c.getTime() > now.getTime()) return c.toISOString();
  }
  return new Date(now.getTime() + 86400000).toISOString();
}
function originForListing(l: Listing): string {
  // Prefer the python-derived origin (identical to the one behind the cached card
  // numbers) so the live panel and the card can't disagree or mis-geocode. Fall back
  // to a local derivation only for legacy data that predates commuteOrigin.
  if (l.commuteOrigin && l.commuteOrigin.trim()) return l.commuteOrigin.trim();
  const sf = l.market === "SF" || /^SF /.test(l.market);
  const first = (s: string) => (s || "").split("/")[0].trim();
  const loc = [first(l.neighborhood), first(l.city)].filter(Boolean).join(", ") || first(l.city) || first(l.market);
  if (!loc) return "San Francisco Bay Area, CA";
  if (/,\s*ca\b/i.test(loc) || /california/i.test(loc)) return loc;
  return loc + (sf ? ", San Francisco, CA" : ", CA");
}
const destOf = (company: string, address: string) => [company, address].filter(Boolean).join(", ") || "San Francisco, CA";
const clockOf = (iso?: string) => (iso ? new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "—");
const railLeg = (legs: any[]) => (legs || []).find((x) => x?.rail);

const segPass = (l: Listing, seg: string, newest: string) => {
  if (seg === "All") return true;
  if (seg === "New today") return !!newest && l.firstSeen === newest;
  if (seg === "Subleases") return isFlex(`${l.lease} ${l.title}`);
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
const possibleFiveText = (l: Listing) =>
  /\b(5|five|6|six|7|seven|8|eight|9|nine|10|ten)\s*[-+]?\s*(bd|br|beds?|bedrooms?)\b/i.test(`${l.beds} ${l.title} ${l.notes || ""}`);
const huntPass = (l: Listing, mode: string) => {
  if (mode === "All inventory") return true;
  if (mode === "5+ whole homes") return !!l.isFivePlus && l.unitScope !== "room";
  if (mode === "Rooms in 5+ homes") return !!l.isFivePlus && l.unitScope === "room";
  if (mode === "Exact SF 5+") return !!l.isFivePlus && !!l.exactSf;
  if (mode === "Possible 5+") return !!l.isFivePlus || (l.bedsNum == null && possibleFiveText(l));
  return true;
};
const regionPass = (l: Listing, r: string) => {
  if (r === "All") return true;
  if (r === "SF") return /^SF /.test(l.market) || l.market === "SF";
  if (r === "Peninsula") return PENINSULA.includes(l.market);
  if (r === "South Bay") return SOUTH.includes(l.market);
  return true;
};
const matchQ = (l: Listing, q: string) =>
  !q.trim() || [l.title, l.market, l.city, l.neighborhood, l.lease, l.source, l.notes, l.why].join(" ").toLowerCase().includes(q.toLowerCase());

const SEG_NAMES = ["All", "New today", "Subleases", "Rooms", "Apartments", "To verify", "Expired"];
const SORT_OPTIONS = ["Best fit", "Board rank", "Cheapest", "Shortest commute", "No-car score", "Car score", "Newest"];
const BEDS_OPTIONS = ["Any", "Studio", "1+ bd", "2+ bd", "3+ bd", "4+ bd", "5+ bd", "6+ bd"];
const HUNT_OPTIONS = ["All inventory", "5+ whole homes", "Rooms in 5+ homes", "Exact SF 5+", "Possible 5+"];
const bedsForGroup = (n: number) => (n <= 1 ? "Any" : `${Math.min(n, 6)}+ bd`); // 1:1 people->bedrooms

// per-listing marks
const MARK_FILTERS = [
  { key: "active", label: "Active", tone: "#1c1a17" },
  { key: "promising", label: "★ Promising", tone: "var(--accent)" },
  { key: "checked", label: "✓ Checked out", tone: "#5a8f6a" },
  { key: "skip", label: "✕ Passed", tone: "#b4502f" },
  { key: "gone", label: "⊘ Archived", tone: "#9a9384" },
  { key: "all", label: "All", tone: "#8a8378" },
];
const COUNTED_MARKS = ["promising", "checked", "skip", "gone"];
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
  // Two search profiles: "liam" (solo, locked to HackerRank) and "group" (editable list).
  const [profile, setProfile] = useState<"liam" | "group">(saved.profile === "group" ? "group" : "liam");
  const [liamPerson, setLiamPerson] = useState<Person>(
    saved.liam ? { ...liamDefault, ...saved.liam, id: 0, name: "Liam", company: "HackerRank", address: LIAM_OFFICE } : liamDefault
  );
  const [people, setPeople] = useState<Person[]>(
    Array.isArray(saved.people) && saved.people.length
      ? saved.people.map((p: Person, i: number) => ({ ...p, id: p.id ?? i + 1, arrival: p.arrival || "09:00", car: p.car ?? true, bike: p.bike ?? true })) // backfill
      : groupDefault
  );
  const activePeople = useMemo(() => (profile === "liam" ? [liamPerson] : people), [profile, liamPerson, people]);
  // Per-profile region priorities (the configurable radar). 0..10 per axis.
  const [liamRegions, setLiamRegions] = useState<Record<string, number>>(saved.liamRegions ?? { ...DEFAULT_REGION_VALUES });
  const [groupRegions, setGroupRegions] = useState<Record<string, number>>(saved.groupRegions ?? { ...DEFAULT_REGION_VALUES });
  const activeRegions = profile === "liam" ? liamRegions : groupRegions;
  const [sfOpen, setSfOpen] = useState(false);
  const setRegionPref = (key: string, v: number) => {
    cfgTouched.current = true;
    (profile === "liam" ? setLiamRegions : setGroupRegions)((r) => ({ ...r, [key]: v }));
  };
  const [weights, setWeights] = useState<{ commute: number; price: number; flex: number }>(saved.weights ?? { commute: 60, price: 30, flex: 10 });
  const [q, setQ] = useState("");
  const [beds, setBeds] = useState<string>(
    saved.beds ?? (saved.profile === "group" ? bedsForGroup(GROUP_SEARCH.targetBedrooms) : "Any")
  );
  const [market, setMarket] = useState<string>(saved.market ?? "All areas");
  const [huntMode, setHuntMode] = useState<string>(saved.huntMode ?? (saved.profile === "group" ? "5+ whole homes" : "All inventory"));
  const [excludedSources, setExcludedSources] = useState<string[]>(Array.isArray(saved.excludedSources) ? saved.excludedSources : []);
  const [region, setRegion] = useState<string>(saved.region ?? (saved.profile === "group" ? "SF" : "All"));
  const [segment, setSegment] = useState<string>(saved.segment ?? "All");
  const [sort, setSort] = useState<string>(saved.sort ?? "Best fit");
  const [maxPrice, setMaxPrice] = useState<number>(saved.maxPrice ?? (saved.profile === "group" ? GROUP_SEARCH.totalBudget : LIAM_DEFAULT_BUDGET));
  const [maxTransit, setMaxTransit] = useState<number>(saved.maxTransit ?? 0);
  const [maxDrive, setMaxDrive] = useState<number>(saved.maxDrive ?? 0);
  const [budgetCustom, setBudgetCustom] = useState<boolean>(saved.budgetCustom ?? false);
  const [markFilter, setMarkFilter] = useState<string>(saved.markFilter ?? "active");
  const [marks, setMarks] = useState<Record<string, string>>(loadMarks);
  const [showNeedsReview, setShowNeedsReview] = useState<boolean>(saved.showNeedsReview ?? false);
  const [expandedClusters, setExpandedClusters] = useState<Record<string, boolean>>({});
  const [visibleLimit, setVisibleLimit] = useState(80);

  // Point search — a pinned place + radius; listings rank/filter by real distance.
  const [point, setPoint] = useState<Point | null>(saved.point ?? null);
  const [pointRadius, setPointRadius] = useState<number>(saved.pointRadius ?? 3);
  const [pointQ, setPointQ] = useState<string>("");
  const [pointBusy, setPointBusy] = useState(false);
  const [pointErr, setPointErr] = useState<string>("");
  const pointRequestGeneration = useRef(0);

  // Inspire Me — a diverse shortlist outside the current filter bubble.
  const [inspireOpen, setInspireOpen] = useState(false);
  const [inspireSeed, setInspireSeed] = useState(1);

  // Resizable sidebar — drag the divider; width persists (double-click resets).
  const ASIDE_MIN = 280, ASIDE_MAX = 680, ASIDE_DEFAULT = 344;
  const [asideW, setAsideW] = useState<number>(
    typeof saved.asideW === "number" ? clamp(saved.asideW, ASIDE_MIN, ASIDE_MAX) : ASIDE_DEFAULT
  );
  const startResize = (e: React.MouseEvent) => {
    e.preventDefault();
    const startX = e.clientX, startW = asideW;
    const onMove = (ev: MouseEvent) => setAsideW(clamp(startW + ev.clientX - startX, ASIDE_MIN, ASIDE_MAX));
    const onUp = () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  };

  const dense = DENSITY === "compact";
  const pad = dense ? "12px 15px" : "16px 17px";

  // Profile defaults come from the canonical household/search config. The group
  // stays at $2,650/person; Liam starts at the solo sweet-spot ceiling.
  const tenants = activePeople.length;
  const profileBudget = profile === "group" ? GROUP_SEARCH.budgetPerPerson * tenants : LIAM_DEFAULT_BUDGET;
  const budgetSliderMax = profile === "group" ? Math.max(16000, profileBudget + 3000) : 8000;
  const budget = budgetCustom ? Math.min(maxPrice, budgetSliderMax) : profileBudget;
  const budgetIsAny = budget >= budgetSliderMax;

  // persist last selections (browser-local)
  useEffect(() => {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify({ pref, profile, liam: liamPerson, people, liamRegions, groupRegions, weights, beds, market, huntMode, excludedSources, region, segment, sort, maxPrice, maxTransit, maxDrive, budgetCustom, markFilter, asideW, showNeedsReview, point, pointRadius }));
    } catch { /* storage unavailable — ignore */ }
  }, [pref, profile, liamPerson, people, liamRegions, groupRegions, weights, beds, market, huntMode, excludedSources, region, segment, sort, maxPrice, maxTransit, maxDrive, budgetCustom, markFilter, asideW, showNeedsReview, point, pointRadius]);

  // Sync the shared bits (Liam + Group profiles, region priorities) to Supabase so the
  // last-set config is one source of truth across devices. Debounced; skips the initial
  // mount/hydrate so we don't echo defaults back over a real saved config.
  // Push synced config (profiles + region radars) to Supabase, but ONLY after the user
  // actually edits something. cfgTouched stays false through the load-time hydrate, so we
  // never echo the just-fetched remote config straight back (which could clobber fresher
  // remote data in a two-device race). Set true by every synced-field setter below.
  const cfgTouched = useRef(false);
  useEffect(() => {
    if (!REMOTE_SYNC_ENABLED) return;
    if (!cfgTouched.current) return;
    const t = setTimeout(() => {
      saveConfig("profiles", { liam: liamPerson, group: people }).catch(() => {});
      saveConfig("regions", { liam: liamRegions, group: groupRegions }).catch(() => {});
    }, 700);
    return () => clearTimeout(t);
  }, [liamPerson, people, liamRegions, groupRegions]);

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
    if (!REMOTE_SYNC_ENABLED) return;
    let alive = true;
    fetchRemoteMarks()
      .then((remote) => {
        if (!alive) return;
        // Authoritative merge: remote is the source of truth. Keep only the marks the
        // user touched THIS session (not yet guaranteed round-tripped), then overlay all
        // remote marks. A local mark that is untouched AND absent from remote was cleared
        // on another device, so it's correctly dropped (the old additive merge kept it
        // forever). Runs only on a successful fetch; offline keeps local via .catch.
        setMarks((local) => {
          const out: Record<string, string> = {};
          for (const k in local) if (touchedKeys.current.has(k)) out[k] = local[k];
          for (const k in remote) if (!touchedKeys.current.has(k)) out[k] = remote[k];
          return out;
        });
      })
      .catch(() => { /* offline / unreachable — localStorage stays the source */ });
    return () => { alive = false; };
  }, []);

  // Pull the shared config (Liam + Group profiles, region priorities) from Supabase on
  // load — the single source of truth. Last-set wins over local defaults; offline -> local.
  useEffect(() => {
    if (!REMOTE_SYNC_ENABLED) return;
    let alive = true;
    fetchConfig()
      .then((cfg) => {
        if (!alive || !cfg) return;
        if (cfgTouched.current) return; // user already edited this session — don't overwrite
        const profiles = cfg.profiles as { liam?: Partial<Person>; group?: Partial<Person>[] } | undefined;
        if (profiles?.liam) setLiamPerson((p) => ({ ...p, ...profiles.liam, id: 0, name: "Liam", company: "HackerRank", address: LIAM_OFFICE }));
        if (Array.isArray(profiles?.group) && profiles.group.length)
          setPeople(profiles.group.map((p, i) => ({ id: p.id ?? i + 1, name: p.name || "Roommate " + (i + 1), company: p.company || "", address: p.address || "", arrival: p.arrival || "09:00", car: p.car ?? true, bike: p.bike ?? true })));
        const regions = cfg.regions as { liam?: Record<string, number>; group?: Record<string, number> } | undefined;
        if (regions?.liam) setLiamRegions((r) => ({ ...r, ...regions.liam }));
        if (regions?.group) setGroupRegions((r) => ({ ...r, ...regions.group }));
      })
      .catch(() => { /* offline — localStorage stays the source */ });
    return () => { alive = false; };
  }, []);

  // toggle a per-listing mark; clicking the active mark clears it. Optimistic local
  // update + background push to the durable store (fire-and-forget; offline is fine).
  const setMark = (key: string, val: string) => {
    touchedKeys.current.add(key);
    const clearing = marks[key] === val; // clicking the active mark clears it
    if (REMOTE_SYNC_ENABLED) {
      if (clearing) deleteRemoteMark(key).catch(() => {});
      else upsertRemoteMark(key, val).catch(() => {});
    }
    setMarks((m) => {
      const n = { ...m };
      if (clearing) delete n[key];
      else n[key] = val;
      return n;
    });
  };
  // copy the active profile so it can be pasted into household.json (drives that scraper)
  const copyScrapeConfig = () => {
    const cfg = profile === "liam"
      ? { profile: "liam", people: [{ name: "Liam", company: "HackerRank", address: LIAM_OFFICE, arrival: liamPerson.arrival, car: liamPerson.car, bike: liamPerson.bike }] }
      : { profile: "group", ...GROUP_SEARCH, people: people.map((p) => ({ name: p.name, company: p.company, address: p.address, arrival: p.arrival, car: p.car, bike: p.bike })) };
    try { navigator.clipboard.writeText(JSON.stringify(cfg, null, 2)); } catch { /* ignore */ }
  };
  const copyMarkCommand = async (status: "Rejected" | "Unavailable" | "Duplicate", key: string) => {
    const cmd = `python3 skills/bay-area-housing-hunt/scripts/housing_pipeline.py --mark "${status}=${key}"`;
    const copyViaTextarea = () => {
      const area = document.createElement("textarea");
      area.value = cmd;
      area.setAttribute("readonly", "true");
      area.style.position = "fixed";
      area.style.left = "-9999px";
      document.body.appendChild(area);
      area.select();
      let ok = false;
      try { ok = document.execCommand("copy"); } catch { ok = false; }
      document.body.removeChild(area);
      return ok;
    };
    if (copyViaTextarea()) return;
    try {
      await navigator.clipboard.writeText(cmd);
    } catch { /* clipboard unavailable */ }
  };
  const setLiam = (field: keyof Person, value: any) => { cfgTouched.current = true; setLiamPerson((p) => ({ ...p, [field]: value })); };
  const togglePersonFlag = (id: number, field: "car" | "bike") => {
    cfgTouched.current = true;
    setPeople((s) => s.map((p) => (p.id === id ? { ...p, [field]: !p[field] } : p)));
  };
  const markCounts = useMemo(() => {
    const c: Record<string, number> = { promising: 0, checked: 0, skip: 0, gone: 0 };
    for (const k in marks) if (c[marks[k]] != null) c[marks[k]]++;
    return c;
  }, [marks]);

  // On-demand: live optimal-departure plans per listing (Google Routes via /api/commute).
  // One request per person (transit/drive/bike), computed only when the user asks.
  const [plans, setPlans] = useState<Record<string, { loading: boolean; results?: any[]; error?: boolean }>>({});
  const planCommute = async (key: string, origin: string) => {
    setPlans((p) => ({ ...p, [key]: { loading: true } }));
    try {
      const results = await Promise.all(
        activePeople.map(async (person) => {
          const arrival = nextOfficeArrivalISO(person.arrival);
          const url = `/api/commute?origin=${encodeURIComponent(origin)}&dest=${encodeURIComponent(destOf(person.company, person.address))}&arrival=${encodeURIComponent(arrival)}`;
          try {
            const r = await fetch(url);
            return { person: person.name || "—", hasCar: person.car, hasBike: person.bike, arrival, ...(await r.json()) };
          } catch {
            return { person: person.name || "—", hasCar: person.car, hasBike: person.bike, error: true };
          }
        })
      );
      setPlans((p) => ({ ...p, [key]: { loading: false, results } }));
    } catch {
      setPlans((p) => ({ ...p, [key]: { loading: false, error: true } }));
    }
  };

  const setW = (k: "commute" | "price" | "flex", v: number) => setWeights((s) => ({ ...s, [k]: v }));
  const setPerson = (id: number, field: keyof Person, value: string) => {
    cfgTouched.current = true;
    setPeople((s) => s.map((p) => (p.id === id ? { ...p, [field]: value } : p)));
  };
  // Profile switch is a deliberate context change -> re-default the bedroom filter.
  // Group targets ~1 bedroom per person (5 people -> 5+); Liam starts with all
  // inventory visible and can narrow bedrooms explicitly.
  // Driven by user action (not an effect) so cross-device hydration never resets beds.
  const changeProfile = (k: "liam" | "group") => {
    if (k === profile) return;
    setProfile(k);
    setBeds(k === "group" ? bedsForGroup(GROUP_SEARCH.targetBedrooms) : "Any");
    setHuntMode(k === "group" ? "5+ whole homes" : "All inventory");
    setRegion(k === "group" ? "SF" : "All");
    setMarket("All areas");
    setMaxPrice(k === "group" ? GROUP_SEARCH.totalBudget : LIAM_DEFAULT_BUDGET);
    setBudgetCustom(false);
    clearPoint();
  };
  const removePerson = (id: number) => {
    if (people.length <= 1) return;
    cfgTouched.current = true;
    setPeople((s) => s.filter((p) => p.id !== id));
    setBeds(bedsForGroup(people.length - 1));
  };
  const addPerson = () => {
    cfgTouched.current = true;
    setPeople((s) => {
      const id = s.reduce((m, p) => Math.max(m, p.id), 0) + 1;
      return [...s, { id, name: "Roommate " + (s.length + 1), company: "", address: "", arrival: "09:00", car: true, bike: true }];
    });
    setBeds(bedsForGroup(people.length + 1));
  };

  const active = useMemo(() => data.listings.filter((l) => l.status === "Active"), []);
  const newest = useMemo(() => active.reduce((m, l) => (l.firstSeen > m ? l.firstSeen : m), ""), [active]);
  // Market centroids give the ~half of listings without exact coordinates an
  // approximate location, so point search never silently drops them.
  const centroids = useMemo(() => marketCentroids(data.listings as any), []);
  const sourceStats = useMemo(() => {
    const stats: Record<string, { active: number; fivePlus: number; needs: number; blocked: number; stale: number; browser: number }> = {};
    for (const l of data.listings) {
      const key = l.source || "Unknown";
      const s = stats[key] || (stats[key] = { active: 0, fivePlus: 0, needs: 0, blocked: 0, stale: 0, browser: 0 });
      if (l.status === "Active") {
        s.active++;
        if (l.isFivePlus) s.fivePlus++;
      }
      if (l.status === "Needs Verification") s.needs++;
      if (l.status === "Source Blocked") s.blocked++;
      if (l.status === "Stale") s.stale++;
      if (l.sourceTier === "browser") s.browser++;
    }
    return stats;
  }, []);
  const sourceList = useMemo(() => Object.keys(sourceStats).filter((s) => sourceStats[s].active > 0).sort(), [sourceStats]);
  const marketOptions = useMemo(() => ["All areas", ...(data.marketOrder || [])], []);
  const generatedDay = (data.generatedAt || new Date().toISOString()).slice(0, 10);

  // Score one listing against the current profile/weights/marks/pinned point.
  // Shared by the main list AND Inspire Me so every number agrees everywhere.
  const scoreListing = useMemo(() => {
    const sum = weights.commute + weights.price + weights.flex || 1;
    const wc = weights.commute / sum, wp = weights.price / sum, wf = weights.flex / sum;
    const roster = activePeople;
    return (l: Listing) => {
        const per = roster.map((person) => {
          const hasOffice = `${person.company || ""}${person.address || ""}`.trim() !== "";
          const g = geocode((person.company || "") + " " + (person.address || ""));
          const cm = hasOffice ? estimate(l, g, pref, person.car) : { t: null as number | null, mode: "transit" };
          const dest = hasOffice ? ([person.company, g.c].filter(Boolean).join(" · ") || "their office") : "no office set";
          return { name: person.name || "—", t: cm.t, mode: cm.mode, dest };
        });
        const times = per.map((x) => x.t).filter((x): x is number => x != null);
        const avg = times.length ? times.reduce((a, b) => a + b, 0) / times.length : null;
        const max = times.length ? Math.max(...times) : null;
        const cScore = avg == null ? 0 : clamp((100 * (85 - avg)) / 70, 0, 100);
        const price = l.allIn ?? l.rent;
        const pScore = price == null ? 50 : clamp((100 * (4000 - price)) / 3300, 0, 100);
        const fScore = isFlex(`${l.lease} ${l.title}`) ? 100 : 50;
        const segC = wc * cScore, segP = wp * pScore, segF = wf * fScore;
        const markState = marks[l.listingKey] || "";
        const markBoost = markState === "promising" ? 15 : markState === "checked" ? 5 : markState === "skip" ? -30 : markState === "gone" ? -100 : 0;
        // weight the fit by this profile's region priority (the configurable radar)
        const rBoost = regionBoost(activeRegions[listingAxisKey(l.market, l.city)] ?? 5);
        const fit = clamp(Math.round((segC + segP + segF) * rBoost + markBoost), 0, 100);
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

        const pricePerBedroom = price != null && l.bedsNum && l.bedsNum > 1 ? Math.round(price / l.bedsNum) : null;
        const sourceLabel = l.sourceTier === "browser" ? "Browser source" : l.sourceTier === "headless" ? "Headless source" : l.sourceTier === "api" ? "API source" : "Manual source";
        const locLabel = l.exactSf ? "Exact SF" : l.locationConfidence === "spillover" ? "Spillover" : l.sfMarket ? "SF bucket" : l.locationConfidence ? `Location: ${l.locationConfidence}` : "";
        const firstAgeDays = daysBetween(l.firstSeen, generatedDay);
        const lastAgeDays = daysBetween(l.lastSeen || l.firstSeen, generatedDay);
        const termEnd = termEndFromText(`${l.title} ${l.notes || ""} ${l.available || ""}`);
        const endsBeforeNeed = !!termEnd && termEnd < NEED_START;
        const commute = commuteChip(l);
        const dist = point ? listingDistanceMiles(l, point, centroids) : null;

        return {
          id: l.listingKey, title: l.title || "(untitled)", url: l.url || "#",
          sub: [l.neighborhood || l.city, l.market, l.source].filter(Boolean).join(" · "),
          isNew: l.status === "Active" && !!newest && l.firstSeen === newest,
          priceLabel: honestRentLabel(l),
          pricePerBedroom,
          leaseLabel: l.lease || "lease n/a",
          specLabel: specBits.join(" · "), hasSpec: specBits.length > 0,
          status: l.status, routes, routesTitle, mark: markState, origin: originForListing(l),
          sourceLabel, sourceHealth: l.sourceHealth || "", locLabel, locationConfidence: l.locationConfidence || "",
          exactSf: !!l.exactSf, isFivePlus: !!l.isFivePlus, unitScope: l.unitScope || "unknown",
          boardRank: l.overallRank ?? null, cityRank: l.cityRank ?? null, firstAgeDays, lastAgeDays,
          ageLabel: l.firstSeen ? `first seen ${ago(firstAgeDays)} · last seen ${ago(lastAgeDays)}` : "",
          stale: lastAgeDays != null && lastAgeDays > 2, markBoost,
          pipelineWhy: l.why || "", lastSeen: l.lastSeen || "", available: l.available || "", commuteSource: l.commuteSource || "static",
          scamRisk: isScamRisk(l), termEndLabel: endsBeforeNeed && termEnd ? `Ends ${fmtDate(termEnd)}` : "",
          commuteChip: commute, duplicateKey: clusterKey(l), duplicateCount: 1, duplicates: [] as any[],
          pipelineScore: l.score ?? 0, noCarScore: l.noCarScore ?? 0, carScore: l.carScore ?? 0,
          boardFitTier: l.fitTier || "",
          boardFitTitle: l.scoreBreakdown
            ? [
                `value ${l.scoreBreakdown.value ?? "?"}`,
                `flex ${l.scoreBreakdown.flexibility ?? "?"}${l.scoreBreakdown.flexibilityReason ? ` (${l.scoreBreakdown.flexibilityReason})` : ""}`,
                `commute ${l.scoreBreakdown.commuteNoCar ?? "?"}`,
                `quality ${l.scoreBreakdown.quality ?? "?"}`,
                `confidence ${l.scoreBreakdown.confidence ?? "?"}`,
                `nbhd ${l.scoreBreakdown.neighborhood ?? "?"}`,
                ...(l.scoreBreakdown.perPersonRent ? [`$${l.scoreBreakdown.perPersonRent}/person`] : []),
              ].join(" · ")
            : "",
          fit, segC, segP, segF,
          fitFg: tier === "hi" ? "var(--accent)" : tier === "mid" ? "#b07d1a" : "#9a9384",
          distLabel: dist ? fmtMiles(dist) : "",
          _avg: avg == null ? 1e9 : avg, _price: price == null ? 1e9 : price, _first: l.firstSeen || "", _score: fit,
          _board: l.overallRank ?? 1e9, _noCar: l.noCarScore ?? 0, _car: l.carScore ?? 0,
          _dist: dist ? dist.miles : 1e9,
        };
    };
  }, [activePeople, weights, pref, marks, activeRegions, newest, generatedDay, point, centroids]);

  const rows = useMemo(() => {
    const pool =
      segment === "To verify"
        ? data.listings.filter((l) => l.status === "Needs Verification")
        : segment === "Expired"
        ? data.listings.filter((l) => !["Active", "Needs Verification"].includes(l.status))
        : active;

    const list = pool
      .filter((l) => segPass(l, segment, newest))
      .filter((l) => bedsPass(l, beds))
      .filter((l) => huntPass(l, huntMode))
      .filter((l) => market === "All areas" || l.market === market)
      .filter((l) => !excludedSources.includes(l.source))
      .filter((l) => regionPass(l, region))
      .filter((l) => !maxTransit || (l.commuteMin != null && l.commuteMin <= maxTransit))
      .filter((l) => !maxDrive || (l.carCommuteMin != null && l.carCommuteMin <= maxDrive))
      .filter((l) => {
        const p = l.allIn ?? l.rent;
        return p == null || budgetIsAny || p <= budget;
      })
      .filter((l) => matchQ(l, q))
      .filter((l) => {
        if (showNeedsReview || segment !== "All") return true;
        const termEnd = termEndFromText(`${l.title} ${l.notes || ""} ${l.available || ""}`);
        return l.status !== "Needs Verification" && !isScamRisk(l) && !(termEnd && termEnd < NEED_START);
      })
      .filter((l) => {
        const mk = marks[l.listingKey];
        if (markFilter === "all") return true;
        if (markFilter === "active") return mk !== "skip" && mk !== "gone"; // hide passed + archived
        return mk === markFilter; // promising | checked | skip | gone
      })
      .map(scoreListing)
      // Point search: with a radius, keep listings inside it (centroid-located
      // ones included); "Any distance" keeps everything and just sorts/labels.
      .filter((r) => !point || pointRadius === 0 || r._dist <= pointRadius);

    const SB: Record<string, (a: typeof list[number], b: typeof list[number]) => number> = {
      "Closest first": (a, b) => a._dist - b._dist || b._score - a._score,
      "Best fit": (a, b) => b._score - a._score || a._avg - b._avg,
      "Board rank": (a, b) => a._board - b._board || b._score - a._score,
      Cheapest: (a, b) => a._price - b._price || b._score - a._score,
      "Shortest commute": (a, b) => a._avg - b._avg || b._score - a._score,
      "No-car score": (a, b) => b._noCar - a._noCar || b._score - a._score,
      "Car score": (a, b) => b._car - a._car || b._score - a._score,
      Newest: (a, b) => (b._first || "").localeCompare(a._first || "") || b._score - a._score,
    };
    list.sort(SB[sort] || SB["Best fit"]);
    const clusters = new Map<string, typeof list>();
    for (const row of list) {
      const bucket = clusters.get(row.duplicateKey);
      if (bucket) bucket.push(row);
      else clusters.set(row.duplicateKey, [row]);
    }
    const collapsed: typeof list = [];
    for (const row of list) {
      const bucket = clusters.get(row.duplicateKey)!;
      if (bucket[0] !== row) continue;
      collapsed.push({ ...row, duplicateCount: bucket.length, duplicates: bucket });
    }
    return collapsed;
  }, [active, newest, scoreListing, q, beds, huntMode, market, excludedSources, region, segment, sort, budget, budgetIsAny, maxTransit, maxDrive, marks, markFilter, showNeedsReview, point, pointRadius]);

  useEffect(() => setVisibleLimit(80), [q, beds, huntMode, market, excludedSources, region, segment, sort, budget, maxTransit, maxDrive, markFilter, showNeedsReview, point, pointRadius, profile]);
  const visibleRows = rows.slice(0, visibleLimit);

  // Inspire Me pool: everything Active that fits the profile's identity-level
  // constraints (beds + budget), deliberately IGNORING the narrowing filters
  // (area, source, commute caps, text search) — surfacing outside the bubble is
  // the point. pickInspiration drops marked + scam-risk rows itself.
  const inspirePicks = useMemo(() => {
    if (!inspireOpen) return [];
    const pool = active
      .filter((l) => bedsPass(l, beds))
      .filter((l) => {
        const p = l.allIn ?? l.rent;
        return p == null || budgetIsAny || p <= budget;
      })
      .map(scoreListing)
      .filter((r) => !r.termEndLabel); // don't pitch stays that end before the need date
    return pickInspiration(pool, inspireSeed);
  }, [inspireOpen, inspireSeed, active, beds, budget, budgetIsAny, scoreListing]);

  // ── Point search actions ────────────────────────────────────────────────────
  const pinPoint = async (query: string, radius?: number) => {
    const qq = (query || "").trim();
    if (!qq) return;
    const generation = ++pointRequestGeneration.current;
    setPointBusy(true);
    setPointErr("");
    const p = await resolvePoint(qq);
    if (generation !== pointRequestGeneration.current) return;
    setPointBusy(false);
    if (!p) {
      setPointErr(`Couldn't place "${qq}" — try a city, Caltrain stop, or full address.`);
      return;
    }
    setPoint(p);
    if (radius != null) setPointRadius(clamp(radius, 0, 15));
    setSort("Closest first");
  };
  const clearPoint = () => {
    pointRequestGeneration.current += 1;
    setPointBusy(false);
    setPoint(null);
    setPointQ("");
    setPointErr("");
    setSort((s) => (s === "Closest first" ? "Best fit" : s));
  };

  // ── Agent: one message → dashboard state changes (see src/agent.ts) ─────────
  const resetAllFilters = () => {
    setQ(""); setBeds(profile === "group" ? bedsForGroup(GROUP_SEARCH.targetBedrooms) : "Any");
    setMarket("All areas"); setHuntMode(profile === "group" ? "5+ whole homes" : "All inventory"); setExcludedSources([]);
    setRegion(profile === "group" ? "SF" : "All"); setSegment("All"); setSort("Best fit");
    setMaxPrice(profile === "group" ? GROUP_SEARCH.totalBudget : LIAM_DEFAULT_BUDGET); setBudgetCustom(false); setMaxTransit(0); setMaxDrive(0);
    setMarkFilter("active"); setShowNeedsReview(false);
    clearPoint(); setSort("Best fit");
  };
  const runCommand = (text: string): { reply: string } | null => {
    const parsed = parseCommand(text, marketOptions);
    if (!parsed) return null;
    const notes: string[] = [];
    // A profile supplies defaults; explicit filters in the same command must
    // always win regardless of the parser's action order.
    const profileAction = parsed.actions.find((action) => action.kind === "profile");
    if (profileAction?.kind === "profile") changeProfile(profileAction.value);
    for (const a of parsed.actions) {
      if (a.kind === "profile") continue;
      switch (a.kind) {
        case "budget": setMaxPrice(a.value); setBudgetCustom(true); break;
        case "beds": setBeds(a.value); break;
        // An area command is a new location scope — it replaces a conflicting pin,
        // and market/region are mutually exclusive controls so one resets the other.
        case "market": setMarket(a.value); setRegion("All"); if (point) { clearPoint(); notes.push("(unpinned the point)"); } break;
        case "region": setRegion(a.value); setMarket("All areas"); if (point) { clearPoint(); notes.push("(unpinned the point)"); } break;
        case "segment": setSegment(a.value); break;
        case "sort":
          if (a.value === "Closest first" && !point) notes.push("(pin a point first to sort by distance)");
          else setSort(a.value);
          break;
        case "markFilter": setMarkFilter(a.value); break;
        case "maxTransit": setMaxTransit(clamp(a.value, 0, 140)); break;
        case "maxDrive": setMaxDrive(clamp(a.value, 0, 120)); break;
        case "huntMode": setHuntMode(a.value); break;
        case "point": setPointQ(a.query); pinPoint(a.query, a.radius); break;
        case "clearPoint": clearPoint(); break;
        case "inspire": setInspireOpen(true); setInspireSeed((s) => s + 1); break;
        case "showNeedsReview": setShowNeedsReview(a.value); break;
        case "reset": resetAllFilters(); break;
      }
    }
    return { reply: "Done: " + parsed.said.join(" · ") + (notes.length ? " " + notes.join(" ") : "") + "." };
  };

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

  // car / bike tickers for a person — gate which modes the optimal-departure recommends
  const tickerRow = (p: Person, onToggle: (f: "car" | "bike") => void) => (
    <div style={{ display: "flex", gap: 6 }}>
      {(["car", "bike"] as const).map((f) => {
        const on = p[f];
        return (
          <button key={f} onClick={() => onToggle(f)} title={`${on ? "Has" : "No"} ${f}`} style={{ flex: 1, cursor: "pointer", padding: "5px 6px", borderRadius: 8, fontSize: 11, fontWeight: 600, border: `1px solid ${on ? "var(--accent)" : "#e0dacd"}`, background: on ? "color-mix(in srgb, var(--accent) 10%, #fff)" : "#fff", color: on ? "var(--accent)" : "#9a9384" }}>
            {on ? "✓ " : ""}{f === "car" ? "🚗 Car" : "🚲 Bike"}
          </button>
        );
      })}
    </div>
  );

  const counts = useMemo(() => {
    const needs = data.listings.filter((l) => l.status === "Needs Verification").length;
    const expired = data.listings.filter((l) => !["Active", "Needs Verification"].includes(l.status)).length;
    return { needs, expired };
  }, []);

  const viewLabel = segment === "All" ? "All listings" : segment;
  const pipelineStamp = data.pipelineRunAt || data.runHealth?.finishedAt || "";
  const updated = pipelineStamp
    ? new Date(pipelineStamp).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })
    : "–";
  const freshnessHours = pipelineStamp ? Math.max(0, (Date.now() - Date.parse(pipelineStamp)) / 3600000) : null;
  const overallHealth = freshnessHours != null && freshnessHours > 24
    ? "stale"
    : data.runHealth?.overall || "unknown";
  const healthTone = overallHealth === "healthy" ? "#4f8060" : overallHealth === "needs_browser" ? "#b07d1a" : "#b4502f";
  const tierHealth = ["web", "rss", "apis", "ai_browser"].map((tier) => {
    const sources = (data.runHealth?.sources || []).filter((source) => source.tier === tier);
    const selected = sources.filter((source) => source.selectedThisRun !== false);
    const bad = selected.filter((source) => ["blocked", "missing", "malformed", "degraded", "empty"].includes(source.status)).length;
    const pending = selected.filter((source) => source.status === "pending").length;
    const notRun = sources.filter((source) => source.selectedThisRun === false || ["not_run", "not_selected", "skipped"].includes(source.status)).length;
    const ok = selected.filter((source) => ["ok", "captured"].includes(source.status)).length;
    return { tier, label: tier === "ai_browser" ? "Browser" : tier === "apis" ? "APIs" : tier === "rss" ? "Alerts/RSS" : "Headless", sources, selected, bad, pending, notRun, ok };
  }).filter((item) => item.sources.length > 0);

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
            <p style={{ margin: "6px 0 0", fontSize: 13, color: "#6f6a61" }}>
              Scraped listings, ranked by who has to commute · pipeline {updated}
              {freshnessHours != null ? ` · ${freshnessHours < 1 ? "under 1h old" : `${Math.floor(freshnessHours)}h old`}` : ""}
            </p>
            <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
              <span title={`Run health: ${overallHealth.replace(/_/g, " ")}`} style={{ fontSize: 10.5, fontWeight: 800, letterSpacing: "0.04em", textTransform: "uppercase", padding: "3px 7px", borderRadius: 6, background: `${healthTone}18`, color: healthTone }}>
                {overallHealth.replace(/_/g, " ")}
              </span>
              {tierHealth.map((item) => {
                const tone = item.bad ? "#b4502f" : item.pending || item.notRun ? "#b07d1a" : "#4f8060";
                const details = item.sources.map((source) => `${source.name}${source.label ? ` (${source.label})` : ""}: ${source.selectedThisRun === false ? `not selected this run; last result ${source.status}` : source.status}${source.message ? ` — ${source.message}` : ""}`).join("\n");
                return (
                  <span key={item.tier} title={details} style={{ fontSize: 10.5, fontWeight: 700, padding: "3px 7px", borderRadius: 6, background: `${tone}12`, color: tone, border: `1px solid ${tone}35` }}>
                    {item.label} {item.ok}/{item.selected.length}{item.bad ? ` · ${item.bad} issue${item.bad === 1 ? "" : "s"}` : item.pending ? ` · ${item.pending} pending` : item.notRun ? ` · ${item.notRun} not run` : ""}
                  </span>
                );
              })}
            </div>
          </div>
        </div>
        <div style={{ display: "flex", gap: 22 }}>
          <Stat value={data.stats.active} label="Active" />
          <Stat value={data.stats.activeFivePlus ?? 0} label="5+ Beds" />
          <Stat value={data.stats.markets} label="Markets" />
        </div>
      </header>

      <div className="hh-grid" style={{ display: "grid", gridTemplateColumns: `${asideW}px 6px minmax(0,1fr)`, flex: 1, alignItems: "start" }}>
        {/* SIDEBAR */}
        <aside className="hh-aside" style={{ position: "sticky", top: 0, height: "100vh", overflowY: "auto", background: "#fffdf8", borderRight: "1px solid #e6e1d6", padding: "20px 20px 40px" }}>
          {/* profile toggle: Liam (solo) vs Group */}
          <div style={{ display: "flex", background: "#efeadf", borderRadius: 11, padding: 4, marginBottom: 12 }}>
            {([["liam", "Liam"], ["group", "Group"]] as const).map(([k, lbl]) => {
              const on = profile === k;
              return (
                <button key={k} onClick={() => changeProfile(k)} style={{ flex: 1, border: "none", cursor: "pointer", padding: "9px 10px", borderRadius: 8, fontSize: 13.5, fontWeight: 600, fontFamily: "'Space Grotesk',sans-serif", background: on ? "#fffdf8" : "transparent", color: on ? "#1c1a17" : "#8a8378", boxShadow: on ? "0 1px 3px rgba(28,26,23,0.12)" : "none" }}>{lbl}</button>
              );
            })}
          </div>
          <div style={{ fontSize: 11.5, color: "#6f6a61", margin: "-4px 2px 12px", lineHeight: 1.4 }}>
            {profile === "group"
              ? `${GROUP_SEARCH.searchArea} · ${GROUP_SEARCH.targetBedrooms}+ bedrooms · $${GROUP_SEARCH.totalBudget.toLocaleString()} total`
              : `Flexible rooms/subleases included · up to $${LIAM_DEFAULT_BUDGET.toLocaleString()} all-in`}
          </div>

          <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8, marginBottom: 4 }}>
            <div style={sectionLabel}>Who's commuting</div>
            {profile === "group" && (
              <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 11, fontWeight: 600, color: "#b0a99c" }}>
                {people.length} {people.length === 1 ? "person" : "people"}
              </div>
            )}
          </div>
          <div style={{ fontSize: 12.5, color: "#6f6a61", marginBottom: 10 }}>
            {profile === "liam"
              ? "Your commute to HackerRank (Santa Clara) — finding a place for you."
              : people.length > 1
              ? `Ranked by everyone's commute · targeting ~${Math.min(people.length, 6)} bedrooms.`
              : "Add the roommates sharing the place."}
          </div>

          {profile === "liam" ? (
            <div style={{ border: "1.5px solid var(--accent)", borderRadius: 12, padding: "11px 12px", background: "color-mix(in srgb, var(--accent) 6%, #fffdf8)", marginBottom: 8 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
                <div style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--accent)" }} />
                <span style={{ fontSize: 14, fontWeight: 700 }}>Liam</span>
                <span style={{ fontSize: 11, color: "#8a8378", marginLeft: "auto", fontWeight: 600 }}>HackerRank · Santa Clara</span>
              </div>
              <div style={{ fontSize: 11.5, color: "#6f6a61", marginBottom: 8 }}>{LIAM_OFFICE}</div>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
                <span style={{ fontSize: 11, color: "#8a8378", fontWeight: 600 }}>Arrive by</span>
                <input type="time" value={liamPerson.arrival} onChange={(e) => setLiam("arrival", e.target.value)} style={{ border: "1px solid #e0dacd", background: "#fdfbf6", borderRadius: 8, padding: "4px 7px", fontSize: 12, fontWeight: 600, fontFamily: "'JetBrains Mono',monospace", outline: "none" }} />
                <span style={{ fontSize: 10.5, color: "#b0a99c" }}>Mon/Wed/Thu</span>
              </div>
              {tickerRow(liamPerson, (f) => setLiam(f, !liamPerson[f]))}
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 9, marginBottom: 8 }}>
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
                      <input value={p.address} onChange={(e) => setPerson(p.id, "address", e.target.value)} placeholder="Work address or city (e.g. San Francisco)" style={{ ...fieldStyle, borderRadius: 8, padding: "7px 9px", fontSize: 12 }} />
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <span style={{ fontSize: 11, color: "#8a8378", fontWeight: 600 }}>Arrive by</span>
                        <input type="time" value={p.arrival} onChange={(e) => setPerson(p.id, "arrival", e.target.value)} style={{ border: "1px solid #e0dacd", background: "#fdfbf6", borderRadius: 8, padding: "4px 7px", fontSize: 12, fontWeight: 600, color: "#1c1a17", outline: "none", fontFamily: "'JetBrains Mono',monospace" }} />
                        <span style={{ fontSize: 10.5, color: "#b0a99c" }}>Mon/Wed/Thu</span>
                      </div>
                      {tickerRow(p, (f) => togglePersonFlag(p.id, f))}
                      <div style={{ fontSize: 11, fontWeight: 600, color: rt.color }}>{rt.text}</div>
                    </div>
                  </div>
                );
              })}
              <button onClick={addPerson} style={{ border: "1.5px dashed #d4cdbf", background: "transparent", cursor: "pointer", padding: 10, borderRadius: 11, fontSize: 13, fontWeight: 600, color: "#6f6a61" }}>
                + Add a roommate
              </button>
            </div>
          )}
          <button onClick={copyScrapeConfig} title="Copy this profile as JSON to paste into scripts/household.json — that's what its scraper searches for" style={{ border: "none", background: "transparent", cursor: "pointer", padding: "2px 2px 10px", fontSize: 11.5, fontWeight: 600, color: "var(--accent)", textAlign: "left" }}>
            ⧉ Copy {profile === "liam" ? "Liam" : "group"} as scrape config
          </button>

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

          {/* region radar — main (non-SF regions) + a dedicated SF-neighborhoods radar */}
          <div style={{ ...sectionLabel, marginBottom: 5 }}>Region priorities</div>
          <div style={{ fontSize: 12, color: "#6f6a61", marginBottom: 6 }}>
            Tap the rings to set how much you want each area. It reweights the {profile === "liam" ? "Liam" : "group"} ranking.
          </div>
          <div style={{ marginBottom: 12 }}>
            <RadarChart axes={MAIN_AXES} values={activeRegions} onChange={setRegionPref} color="var(--accent)" size={330} />
          </div>
          <button onClick={() => setSfOpen((o) => !o)} style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between", border: "1px solid #e0dacd", background: "#fdfbf6", borderRadius: 10, padding: "9px 12px", fontSize: 12.5, fontWeight: 700, color: "#1c1a17", cursor: "pointer", marginBottom: 10 }}>
            <span>SF neighborhoods</span>
            <span style={{ color: "#8a8378", fontWeight: 600 }}>{sfOpen ? "▾ hide" : "▸ set"}</span>
          </button>
          {sfOpen && (
            <div style={{ marginBottom: 24 }}>
              <RadarChart axes={SF_AXES} values={activeRegions} onChange={setRegionPref} color="var(--accent)" size={300} />
            </div>
          )}

          {/* filters */}
          <div style={{ ...sectionLabel, marginBottom: 12 }}>Narrow it down</div>
          <div style={{ display: "flex", gap: 6, marginBottom: 11, flexWrap: "wrap" }}>
            {["All", "SF", "Peninsula", "South Bay"].map((name) => (
              <button key={name} onClick={() => setRegion(name)} style={{ ...chip(region === name, false), padding: "6px 13px", fontSize: 12.5 }}>{name}</button>
            ))}
          </div>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search title, neighborhood…" style={{ ...fieldStyle, padding: "10px 12px", fontSize: 13.5, marginBottom: 10 }} />

          {/* Point search — pin any place, rank homes by distance to it */}
          <div style={{ border: point ? "1.5px solid var(--accent)" : "1px solid #e6e1d6", borderRadius: 12, padding: "10px 11px", background: point ? "color-mix(in srgb, var(--accent) 5%, #fffdf8)" : "#fdfbf6", marginBottom: 12 }}>
            <div style={{ ...sectionLabel, marginBottom: 7 }}>📍 Near a point</div>
            {!point && (
              <form onSubmit={(e) => { e.preventDefault(); pinPoint(pointQ); }} style={{ display: "flex", gap: 6 }}>
                <input
                  value={pointQ}
                  onChange={(e) => { setPointQ(e.target.value); if (pointErr) setPointErr(""); }}
                  placeholder="Caltrain stop, address, “the office”…"
                  style={{ ...fieldStyle, borderRadius: 8, padding: "7px 9px", fontSize: 12.5, flex: 1, minWidth: 0 }}
                />
                <button type="submit" disabled={pointBusy} style={{ border: "none", background: "var(--accent)", color: "#fffdf8", borderRadius: 8, padding: "7px 12px", fontSize: 12, fontWeight: 700, cursor: "pointer", opacity: pointBusy ? 0.6 : 1 }}>
                  {pointBusy ? "…" : "Pin"}
                </button>
              </form>
            )}
            {pointErr && <div style={{ fontSize: 11, color: "#b4502f", fontWeight: 600, marginTop: 6 }}>{pointErr}</div>}
            {point && (
              <>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: 12.5, fontWeight: 700, color: "var(--accent)", flex: 1, minWidth: 0 }}>{point.label}</span>
                  <button onClick={clearPoint} title="Clear the pin" style={{ border: "none", background: "transparent", cursor: "pointer", color: "#b0a99c", fontSize: 16, lineHeight: 1, padding: 0 }}>×</button>
                </div>
                <div style={{ fontSize: 10.5, color: "#8a8378", marginTop: 2 }}>{point.source === "google" ? "Google geocode" : "known place"} · distances are straight-line</div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", margin: "8px 0 3px" }}>
                  <span style={{ fontSize: 12.5, fontWeight: 600 }}>Within</span>
                  <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 12, fontWeight: 700, color: "var(--accent)" }}>{pointRadius === 0 ? "Any distance" : `${pointRadius} mi`}</span>
                </div>
                <input type="range" min={0} max={10} step={0.5} value={pointRadius} onChange={(e) => setPointRadius(+e.target.value)} style={{ width: "100%" }} />
              </>
            )}
          </div>
          <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
            <select value={beds} onChange={(e) => setBeds(e.target.value)} style={selectStyle}>
              {BEDS_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
            <select value={market} onChange={(e) => setMarket(e.target.value)} style={selectStyle}>
              {marketOptions.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          </div>
          <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 6 }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>5+ hunting</span>
            <span style={{ fontSize: 11, color: "#8a8378", fontWeight: 600 }}>{data.stats.activeFivePlus ?? 0} known 5+</span>
          </div>
          <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
            {HUNT_OPTIONS.map((opt) => (
              <button key={opt} onClick={() => setHuntMode(opt)} style={{ ...chip(huntMode === opt, false), padding: "6px 11px", fontSize: 12 }}>
                {opt}
              </button>
            ))}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 9, marginBottom: 12 }}>
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 3 }}>
                <span style={{ fontSize: 13, fontWeight: 600 }}>Max no-car commute</span>
                <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 12, fontWeight: 700, color: maxTransit ? "var(--accent)" : "#8a8378" }}>{maxTransit ? `${maxTransit}m` : "Any"}</span>
              </div>
              <input type="range" min={0} max={140} step={5} value={maxTransit} onChange={(e) => setMaxTransit(+e.target.value)} style={{ width: "100%" }} />
            </div>
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 3 }}>
                <span style={{ fontSize: 13, fontWeight: 600 }}>Max drive commute</span>
                <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 12, fontWeight: 700, color: maxDrive ? "var(--accent)" : "#8a8378" }}>{maxDrive ? `${maxDrive}m` : "Any"}</span>
              </div>
              <input type="range" min={0} max={120} step={5} value={maxDrive} onChange={(e) => setMaxDrive(+e.target.value)} style={{ width: "100%" }} />
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 6 }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>Sources</span>
            <span style={{ fontSize: 11, color: "#8a8378", fontWeight: 600 }}>{sourceList.length - excludedSources.length}/{sourceList.length} on</span>
          </div>
          <div style={{ display: "flex", gap: 6, marginBottom: 10, flexWrap: "wrap" }}>
            <button onClick={() => setExcludedSources([])} style={{ ...chip(excludedSources.length === 0, false), padding: "6px 11px", fontSize: 12 }}>All</button>
            {sourceList.map((s) => {
              const on = !excludedSources.includes(s);
              const stats = sourceStats[s];
              return (
                <button
                  key={s}
                  onClick={() => setExcludedSources((ex) => (on ? [...ex, s] : ex.filter((x) => x !== s)))}
                  title={`${stats.active} active · ${stats.fivePlus} known 5+ · ${stats.needs} needs verification · ${stats.blocked} blocked · ${stats.stale} stale`}
                  style={{ ...chip(on, false), padding: "6px 11px", fontSize: 12 }}
                >
                  {on ? "✓ " : ""}{s.startsWith("Facebook") ? "Facebook" : s} {stats.active}{stats.fivePlus ? `/${stats.fivePlus} 5+` : ""}
                </button>
              );
            })}
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>Budget — max all-in</span>
            <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 12, fontWeight: 700, color: budgetCustom ? "var(--accent)" : "#6f6a61" }}>{budgetIsAny ? "Any" : "$" + budget.toLocaleString()}</span>
          </div>
          <input type="range" min={500} max={budgetSliderMax} step={100} value={Math.min(budget, budgetSliderMax)} onChange={(e) => { setMaxPrice(+e.target.value); setBudgetCustom(true); }} style={{ width: "100%" }} />
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8, marginTop: 5 }}>
            <span style={{ fontSize: 11, color: "#8a8378" }}>
              Default <strong style={{ color: "#6f6a61", fontWeight: 700 }}>{profile === "group" ? `$${GROUP_SEARCH.budgetPerPerson.toLocaleString()} × ${tenants}` : "solo sweet spot"}</strong>{profile === "group" ? ` = $${profileBudget.toLocaleString()}` : ` = $${LIAM_DEFAULT_BUDGET.toLocaleString()}`}
            </span>
            {budgetCustom && (
              <button onClick={() => setBudgetCustom(false)} style={{ border: "none", background: "transparent", cursor: "pointer", fontSize: 11, fontWeight: 600, color: "var(--accent)", padding: 0, whiteSpace: "nowrap" }}>↺ reset</button>
            )}
          </div>
        </aside>

        {/* RESIZE HANDLE — drag to set sidebar width, double-click to reset */}
        <div
          className="hh-resizer"
          onMouseDown={startResize}
          onDoubleClick={() => setAsideW(ASIDE_DEFAULT)}
          title="Drag to resize · double-click to reset"
          style={{ position: "sticky", top: 0, height: "100vh", cursor: "col-resize", display: "flex", alignItems: "center", justifyContent: "center", background: "transparent", zIndex: 5 }}
        >
          <div className="hh-resizer-grip" style={{ width: 2, height: 40, borderRadius: 2, background: "#d8d2c5" }} />
        </div>

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
              <button
                onClick={() => { setInspireOpen((o) => !o); if (!inspireOpen) setInspireSeed((s) => s + 1); }}
                title="A five-angle shortlist of strong listings you haven't triaged — ignores your narrowing filters on purpose"
                style={{ cursor: "pointer", padding: "7px 14px", borderRadius: 999, fontSize: 13, fontWeight: 700, border: "1px solid var(--accent)", background: inspireOpen ? "var(--accent)" : "color-mix(in srgb, var(--accent) 8%, #fff)", color: inspireOpen ? "#fffdf8" : "var(--accent)" }}
              >
                ✨ Inspire me
              </button>
              <button
                onClick={() => setShowNeedsReview((v) => !v)}
                title={`Include Needs Verification and listings whose term ends before ${fmtDate(NEED_START)}`}
                style={markChip(showNeedsReview, "#b07d1a")}
              >
                {showNeedsReview ? "Showing review-needed" : "Hide review-needed"}
              </button>
              <span style={{ fontSize: 12, color: "#8a8378", fontWeight: 600 }}>Sort</span>
              <select value={sort} onChange={(e) => setSort(e.target.value)} style={{ border: "1px solid #e0dacd", background: "#fffdf8", borderRadius: 9, padding: "7px 10px", fontSize: 13, fontWeight: 600, color: "#1c1a17", cursor: "pointer", outline: "none" }}>
                {(point ? [...SORT_OPTIONS, "Closest first"] : SORT_OPTIONS).map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, marginBottom: 14, flexWrap: "wrap" }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
              <span style={{ fontFamily: "'Space Grotesk',sans-serif", fontSize: 15, fontWeight: 600 }}>{viewLabel}</span>
              <span style={{ fontSize: 13, color: "#8a8378" }}>
                showing {visibleRows.length} of {rows.length} homes · {point ? `${pointRadius === 0 ? "any distance" : `within ${pointRadius} mi`} of ${point.label}` : "ranked by best fit"}
              </span>
            </div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {MARK_FILTERS.map((mf) => (
                <button key={mf.key} onClick={() => setMarkFilter(mf.key)} style={markChip(markFilter === mf.key, mf.tone)}>
                  {mf.label}{COUNTED_MARKS.includes(mf.key) ? ` ${markCounts[mf.key] || 0}` : ""}
                </button>
              ))}
            </div>
          </div>

          {/* Inspire Me — five angles on what the current filters are hiding */}
          {inspireOpen && (
            <section style={{ border: "1.5px solid var(--accent)", borderRadius: 15, background: "color-mix(in srgb, var(--accent) 5%, #fffdf8)", padding: "15px 17px", marginBottom: 16 }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 4, flexWrap: "wrap" }}>
                <span style={{ fontFamily: "'Space Grotesk',sans-serif", fontSize: 15, fontWeight: 700, color: "var(--accent)" }}>✨ Inspire me</span>
                <span style={{ fontSize: 12, color: "#6f6a61" }}>five angles on strong listings you haven't triaged — area/source/commute filters ignored on purpose</span>
                <span style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
                  <button onClick={() => setInspireSeed((s) => s + 1)} style={{ cursor: "pointer", border: "1px solid var(--accent)", background: "#fffdf8", color: "var(--accent)", borderRadius: 8, padding: "4px 11px", fontSize: 12, fontWeight: 700 }}>↻ Another round</button>
                  <button onClick={() => setInspireOpen(false)} style={{ cursor: "pointer", border: "1px solid #e0dacd", background: "#fffdf8", color: "#8a8378", borderRadius: 8, padding: "4px 11px", fontSize: 12, fontWeight: 700 }}>× Close</button>
                </span>
              </div>
              {inspirePicks.length === 0 ? (
                <div style={{ fontSize: 12.5, color: "#8a8378", padding: "10px 0 4px" }}>
                  Nothing left to pitch — everything strong within budget/beds is already marked. Widen beds or budget, or check ★ Promising.
                </div>
              ) : (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(250px, 1fr))", gap: 10, marginTop: 8 }}>
                  {inspirePicks.map((p) => (
                    <div key={p.row.id} style={{ background: "#fffdf8", border: "1px solid #e6e1d6", borderRadius: 12, padding: "11px 12px", display: "flex", flexDirection: "column", gap: 6 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <span style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--accent)", background: "color-mix(in srgb, var(--accent) 12%, #fff)", padding: "2px 7px", borderRadius: 5 }}>{p.angle}</span>
                        <span style={{ marginLeft: "auto", fontFamily: "'Space Grotesk',sans-serif", fontSize: 16, fontWeight: 700, color: p.row.fit >= 70 ? "var(--accent)" : "#b07d1a" }}>{p.row.fit}<span style={{ fontSize: 9, color: "#b0a99c", fontWeight: 700 }}> FIT</span></span>
                      </div>
                      <a href={p.row.url} target="_blank" rel="noreferrer" style={{ fontSize: 13.5, fontWeight: 650, color: "#1c1a17", textDecoration: "none", lineHeight: 1.3 }}>{p.row.title}</a>
                      <div style={{ fontSize: 11.5, color: "#8a8378" }}>{p.row.sub}</div>
                      <div style={{ fontSize: 12, color: "#4a5a6d", lineHeight: 1.4 }}>{p.reason}</div>
                      <div style={{ display: "flex", gap: 5, marginTop: "auto", flexWrap: "wrap" }}>
                        <a href={p.row.url} target="_blank" rel="noreferrer" style={{ ...markBtn(false, "var(--accent)"), textDecoration: "none" }}>Open</a>
                        <button onClick={() => setMark(p.row.id, "promising")} style={markBtn(false, "var(--accent)")}>★ Promising</button>
                        <button onClick={() => setMark(p.row.id, "skip")} style={markBtn(false, "#b4502f")}>✕ Not for me</button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}

          {rows.length === 0 ? (
            <div style={{ textAlign: "center", color: "#8a8378", padding: "54px 20px", border: "1px dashed #d8d1c3", borderRadius: 15, background: "#fffdf8" }}>
              No homes match {huntMode !== "All inventory" ? huntMode : "these filters"}. Try widening beds, budget, source, or area.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {visibleRows.map((r, i) => (
                <article className="hh-listing-card" key={r.id} style={{ display: "grid", gridTemplateColumns: "34px 1fr auto", gap: 14, alignItems: "start", background: r.mark === "checked" ? "#fbf9f3" : "#fffdf8", border: r.mark === "promising" ? "1.5px solid var(--accent)" : r.mark === "gone" ? "1px dashed #cbc4b6" : "1px solid #e6e1d6", borderRadius: 15, padding: pad, boxShadow: "0 1px 2px rgba(28,26,23,0.03)", opacity: r.mark === "skip" || r.mark === "gone" ? 0.6 : r.stale ? 0.72 : 1 }}>
                  <div style={{ fontFamily: "'Space Grotesk',sans-serif", fontSize: 15, fontWeight: 700, color: "#b8b1a2", textAlign: "center", fontVariantNumeric: "tabular-nums", paddingTop: 2 }}>{i + 1}</div>

                  <div style={{ minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                      <a href={r.url} target="_blank" rel="noreferrer" style={{ fontSize: 15, fontWeight: 650, color: "#1c1a17", textDecoration: "none", lineHeight: 1.3 }}>{r.title}</a>
                      {r.isNew && <span style={{ fontSize: 9.5, fontWeight: 800, letterSpacing: "0.06em", color: "var(--accent)", background: "color-mix(in srgb, var(--accent) 14%, #fff)", padding: "2px 6px", borderRadius: 5 }}>NEW</span>}
                      {r.status !== "Active" && <span style={{ fontSize: 9.5, fontWeight: 800, letterSpacing: "0.06em", color: "#b4502f", background: "#f8ece6", padding: "2px 6px", borderRadius: 5 }}>{r.status.toUpperCase()}</span>}
                      {r.duplicateCount > 1 && (
                        <button onClick={() => setExpandedClusters((s) => ({ ...s, [r.duplicateKey]: !s[r.duplicateKey] }))} style={{ border: "1px solid #d8d1c3", background: "#f5f1e8", color: "#6f6a61", cursor: "pointer", fontSize: 10.5, fontWeight: 800, padding: "2px 7px", borderRadius: 6 }}>
                          ×{r.duplicateCount} posts
                        </button>
                      )}
                    </div>
                    <div style={{ fontSize: 12.5, color: "#8a8378", marginTop: 3 }}>{r.sub}</div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 7 }}>
                      {r.distLabel && <span title={point ? `Straight-line distance to ${point.label}` : ""} style={{ fontSize: 11, fontWeight: 800, padding: "3px 7px", borderRadius: 6, background: "color-mix(in srgb, var(--accent) 12%, #fff)", color: "var(--accent)" }}>📍 {r.distLabel}</span>}
                      {r.boardRank && <span style={{ fontSize: 11, fontWeight: 700, padding: "3px 7px", borderRadius: 6, background: "#ece8df", color: "#5a554c" }}>Board #{r.boardRank}</span>}
                      {r.boardFitTier && (
                        <span title={r.boardFitTitle} style={{ fontSize: 11, fontWeight: 800, padding: "3px 7px", borderRadius: 6,
                          background: r.boardFitTier === "Great" ? "#eef6ef" : r.boardFitTier === "Good" ? "color-mix(in srgb, var(--accent) 12%, #fff)" : r.boardFitTier === "Fair" ? "#faf3e3" : "#f0ece3",
                          color: r.boardFitTier === "Great" ? "#4f8060" : r.boardFitTier === "Good" ? "var(--accent)" : r.boardFitTier === "Fair" ? "#b07d1a" : "#9a9384" }}>
                          Fit: {r.boardFitTier}{r.pipelineScore ? ` · ${r.pipelineScore}` : ""}
                        </span>
                      )}
                      {r.cityRank && <span style={{ fontSize: 11, fontWeight: 700, padding: "3px 7px", borderRadius: 6, background: "#ece8df", color: "#5a554c" }}>Area #{r.cityRank}</span>}
                      {r.isFivePlus && <span style={{ fontSize: 11, fontWeight: 800, padding: "3px 7px", borderRadius: 6, background: "color-mix(in srgb, var(--accent) 12%, #fff)", color: "var(--accent)" }}>5+ {r.unitScope === "room" ? "room lane" : "home lane"}</span>}
                      {r.scamRisk && <span style={{ fontSize: 11, fontWeight: 800, padding: "3px 7px", borderRadius: 6, background: "#f8ece6", color: "#b4502f" }}>Scam risk</span>}
                      {r.termEndLabel && <span style={{ fontSize: 11, fontWeight: 800, padding: "3px 7px", borderRadius: 6, background: "#f8ece6", color: "#b4502f" }}>{r.termEndLabel}</span>}
                      {r.ageLabel && <span style={{ fontSize: 11, fontWeight: 700, padding: "3px 7px", borderRadius: 6, background: r.stale ? "#f8ece6" : "#eef6ef", color: r.stale ? "#b4502f" : "#4f8060" }}>{r.ageLabel}</span>}
                      {r.locLabel && <span title={r.locationConfidence} style={{ fontSize: 11, fontWeight: 700, padding: "3px 7px", borderRadius: 6, background: r.locationConfidence === "spillover" ? "#f8ece6" : "#f5f1e8", color: r.locationConfidence === "spillover" ? "#b4502f" : "#6f6a61" }}>{r.locLabel}</span>}
                      <span title={r.sourceHealth} style={{ fontSize: 11, fontWeight: 700, padding: "3px 7px", borderRadius: 6, background: r.sourceLabel === "Browser source" ? "#edf3fb" : "#f5f1e8", color: r.sourceLabel === "Browser source" ? "var(--accent)" : "#6f6a61" }}>{r.sourceLabel}</span>
                      <span style={{ fontSize: 11, fontWeight: 700, padding: "3px 7px", borderRadius: 6, background: r.commuteChip.bg, color: r.commuteChip.tone }}>{r.commuteChip.label}</span>
                    </div>
                    {r.duplicateCount > 1 && expandedClusters[r.duplicateKey] && (
                      <div style={{ display: "flex", flexDirection: "column", gap: 3, marginTop: 7, padding: "7px 9px", borderRadius: 8, background: "#f5f1e8", border: "1px solid #ece8df" }}>
                        {r.duplicates.map((d) => (
                          <a key={d.id} href={d.url} target="_blank" rel="noreferrer" style={{ fontSize: 11.5, fontWeight: 650, color: d.id === r.id ? "#6f6a61" : "var(--accent)", textDecoration: "none" }}>
                            {d.id === r.id ? "Shown" : "Also posted"} · {d.sub} · {d.priceLabel}
                          </a>
                        ))}
                      </div>
                    )}

                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 10 }}>
                      <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 12, fontWeight: 600, padding: "4px 9px", borderRadius: 7, background: "color-mix(in srgb, var(--accent) 11%, #fff)", color: "var(--accent)" }}>{r.priceLabel}</span>
                      {r.pricePerBedroom && <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 12, fontWeight: 600, padding: "4px 9px", borderRadius: 7, background: "#f5f1e8", color: "#6f6a61" }}>${r.pricePerBedroom.toLocaleString()}/bd</span>}
                      <span style={{ fontSize: 12, fontWeight: 600, padding: "4px 9px", borderRadius: 7, background: "#efece6", color: "#5a554c" }}>{r.leaseLabel}</span>
                      {r.hasSpec && <span style={{ fontSize: 12, fontWeight: 600, padding: "4px 9px", borderRadius: 7, background: "#efece6", color: "#5a554c" }}>{r.specLabel}</span>}
                      <span style={{ fontSize: 12, fontWeight: 600, padding: "4px 9px", borderRadius: 7, background: r.available ? "#efece6" : "#f8ece6", color: r.available ? "#5a554c" : "#b4502f" }}>{r.available ? `Avail ${r.available}` : "availability missing"}</span>
                    </div>
                    {r.pipelineWhy && (
                      <div style={{ fontSize: 12.5, color: "#6f6a61", marginTop: 8, lineHeight: 1.35 }}>
                        {r.pipelineWhy}
                      </div>
                    )}

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

                    {/* optimal departure (live Google Routes) */}
                    <div style={{ marginTop: 10 }}>
                      {!plans[r.id] ? (
                        <button onClick={() => planCommute(r.id, r.origin)} style={{ border: "1px solid #cdd9ea", background: "color-mix(in srgb, var(--accent) 6%, #fff)", color: "var(--accent)", cursor: "pointer", padding: "5px 11px", borderRadius: 8, fontSize: 11.5, fontWeight: 700 }}>
                          ⏱ Optimal departure
                        </button>
                      ) : plans[r.id].loading ? (
                        <div style={{ fontSize: 11.5, color: "#8a8378" }}>Planning routes…</div>
                      ) : (
                        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                          {(plans[r.id].results || []).map((pr: any, k: number) => {
                            // only recommend drive/bike if the person ticked having one
                            const opts = [pr.transit, pr.hasCar !== false ? pr.drive : null, pr.hasBike !== false ? pr.bike : null].filter((o: any) => o && o.ok);
                            if (!opts.length)
                              return <div key={k} style={{ fontSize: 11.5, color: "#b07d1a" }}>{pr.person}: no route found</div>;
                            const best = opts.reduce((a: any, b: any) => (new Date(b.leaveBy) > new Date(a.leaveBy) ? b : a), opts[0]);
                            const rl = pr.transit?.ok ? railLeg(pr.transit.legs) : null;
                            const icon: Record<string, string> = { transit: "🚆", drive: "🚗", bike: "🚲" };
                            return (
                              <div key={k} style={{ borderTop: "1px solid #f0ece3", paddingTop: 6 }}>
                                <div style={{ fontSize: 11.5, marginBottom: 3 }}>
                                  <span style={{ fontWeight: 700, color: "#1c1a17" }}>{pr.person}</span>
                                  <span style={{ color: "#b0a99c", fontWeight: 600 }}> · arrive {clockOf(pr.arrival)}</span>
                                  <span style={{ marginLeft: 6, color: "var(--accent)", fontWeight: 700, fontFamily: "'JetBrains Mono',monospace" }}>
                                    {icon[best.mode]} leave {clockOf(best.leaveBy)}
                                  </span>
                                </div>
                                <div style={{ display: "flex", flexWrap: "wrap", gap: "1px 12px", fontSize: 11 }}>
                                  {opts.map((o: any) => (
                                    <span key={o.mode} style={{ fontFamily: "'JetBrains Mono',monospace", fontWeight: o === best ? 700 : 500, color: o === best ? "var(--accent)" : "#8a8378" }}>
                                      {icon[o.mode]} {clockOf(o.leaveBy)} ({o.durationMin}m)
                                    </span>
                                  ))}
                                </div>
                                {rl && (
                                  <div style={{ fontSize: 10.5, color: "#8a8378", marginTop: 2 }}>
                                    🚆 {rl.line} · {rl.from}→{rl.to} · {rl.stops} stops · dep {clockOf(rl.dep)}
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>

                    {/* mark this listing */}
                    <div style={{ display: "flex", gap: 6, marginTop: 11, flexWrap: "wrap" }}>
                      <a href={r.url} target="_blank" rel="noreferrer" style={{ ...markBtn(false, "var(--accent)"), textDecoration: "none" }}>Open</a>
                      <button onClick={() => setMark(r.id, "checked")} style={markBtn(r.mark === "checked", "#5a8f6a")}>✓ Checked out</button>
                      <button onClick={() => setMark(r.id, "promising")} style={markBtn(r.mark === "promising", "var(--accent)")}>★ Promising</button>
                      <button onClick={() => setMark(r.id, "skip")} style={markBtn(r.mark === "skip", "#b4502f")}>✕ Not for me</button>
                      <button onClick={() => setMark(r.id, "gone")} title="No longer available — archive it" style={markBtn(r.mark === "gone", "#9a9384")}>⊘ Unavailable</button>
                      <button onClick={() => copyMarkCommand("Rejected", r.id)} title="Copy housing_pipeline.py mark command" style={markBtn(false, "#b4502f")}>Copy reject cmd</button>
                      <button onClick={() => copyMarkCommand("Unavailable", r.id)} title="Copy housing_pipeline.py mark command" style={markBtn(false, "#9a9384")}>Copy unavailable cmd</button>
                      <button onClick={() => copyMarkCommand("Duplicate", r.id)} title="Copy housing_pipeline.py mark command" style={markBtn(false, "#8a8378")}>Copy duplicate cmd</button>
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
                    {r.markBoost ? <div style={{ fontSize: 10, color: r.markBoost > 0 ? "var(--accent)" : "#b4502f", lineHeight: 1.3, textAlign: "right" }}>mark {r.markBoost > 0 ? "+" : ""}{r.markBoost}</div> : null}
                  </div>
                </article>
              ))}
              {visibleRows.length < rows.length && (
                <button onClick={() => setVisibleLimit((limit) => limit + 80)} style={{ justifySelf: "center", alignSelf: "center", border: "1px solid var(--accent)", background: "#fffdf8", color: "var(--accent)", borderRadius: 10, padding: "10px 18px", fontSize: 13, fontWeight: 800, cursor: "pointer" }}>
                  Show 80 more · {rows.length - visibleRows.length} remaining
                </button>
              )}
            </div>
          )}
        </main>
      </div>

      {/* Agent — one chat box that drives every control above and queues repo work */}
      {REMOTE_AGENT_ENABLED && <AgentPanel runCommand={runCommand} />}
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
