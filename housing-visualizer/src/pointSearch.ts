/* Point search — resolve any typed place to coordinates and measure listings
   against it. Two resolution layers:
     1. LOCAL_PLACES: instant, offline table of the anchors people actually type
        (Caltrain stations, cities, SF neighborhoods, the two seed offices).
     2. /api/geocode: the Vercel function (server-side Google key) for arbitrary
        street addresses. Local dev without the key still gets layer 1.
   Distance is straight-line haversine in miles — honest for "what's near this
   point", cheaper than routing, and clearly labeled as approximate when the
   listing only has a market-centroid location. */

export type Point = { lat: number; lng: number; label: string; source: "local" | "google" };

const R_MILES = 3958.8;
export function haversineMiles(aLat: number, aLng: number, bLat: number, bLng: number): number {
  const rad = Math.PI / 180;
  const dLat = (bLat - aLat) * rad;
  const dLng = (bLng - aLng) * rad;
  const s = Math.sin(dLat / 2) ** 2 + Math.cos(aLat * rad) * Math.cos(bLat * rad) * Math.sin(dLng / 2) ** 2;
  return 2 * R_MILES * Math.asin(Math.min(1, Math.sqrt(s)));
}

/* Anchors keyed by every alias someone might type. Coordinates are station
   platforms / neighborhood centers — plenty for a miles-scale radius. */
type LocalPlace = { lat: number; lng: number; label: string; aliases: string[] };
export const LOCAL_PLACES: LocalPlace[] = [
  // Caltrain stations (north → south)
  { lat: 37.7766, lng: -122.3954, label: "SF Caltrain (4th & King)", aliases: ["sf caltrain", "4th and king", "4th & king", "san francisco caltrain", "caltrain sf"] },
  { lat: 37.7576, lng: -122.3924, label: "22nd Street Caltrain", aliases: ["22nd street caltrain", "22nd st caltrain"] },
  { lat: 37.6003, lng: -122.3868, label: "Millbrae Caltrain", aliases: ["millbrae caltrain", "millbrae station"] },
  { lat: 37.5797, lng: -122.3453, label: "Burlingame Caltrain", aliases: ["burlingame caltrain", "burlingame station"] },
  { lat: 37.568, lng: -122.3239, label: "San Mateo Caltrain", aliases: ["san mateo caltrain", "san mateo station"] },
  { lat: 37.5378, lng: -122.2972, label: "Hillsdale Caltrain", aliases: ["hillsdale caltrain", "hillsdale station"] },
  { lat: 37.5208, lng: -122.2758, label: "Belmont Caltrain", aliases: ["belmont caltrain", "belmont station"] },
  { lat: 37.5072, lng: -122.26, label: "San Carlos Caltrain", aliases: ["san carlos caltrain", "san carlos station"] },
  { lat: 37.4859, lng: -122.2317, label: "Redwood City Caltrain", aliases: ["redwood city caltrain", "redwood city station"] },
  { lat: 37.4544, lng: -122.1824, label: "Menlo Park Caltrain", aliases: ["menlo park caltrain", "menlo park station"] },
  { lat: 37.4434, lng: -122.165, label: "Palo Alto Caltrain", aliases: ["palo alto caltrain", "palo alto station"] },
  { lat: 37.4292, lng: -122.1421, label: "California Ave Caltrain", aliases: ["california ave caltrain", "cal ave caltrain"] },
  { lat: 37.407, lng: -122.1072, label: "San Antonio Caltrain", aliases: ["san antonio caltrain"] },
  { lat: 37.3944, lng: -122.0762, label: "Mountain View Caltrain", aliases: ["mountain view caltrain", "mountain view station", "mtv caltrain"] },
  { lat: 37.3784, lng: -122.0308, label: "Sunnyvale Caltrain", aliases: ["sunnyvale caltrain", "sunnyvale station"] },
  { lat: 37.3705, lng: -121.9967, label: "Lawrence Caltrain", aliases: ["lawrence caltrain", "lawrence station"] },
  { lat: 37.3532, lng: -121.9363, label: "Santa Clara Caltrain", aliases: ["santa clara caltrain", "santa clara station"] },
  { lat: 37.3297, lng: -121.9026, label: "San Jose Diridon", aliases: ["diridon", "san jose diridon", "san jose caltrain"] },
  // Offices
  { lat: 37.3892, lng: -121.9774, label: "HackerRank (Santa Clara office)", aliases: ["hackerrank", "office", "work", "mission college blvd", "the office", "liam's office"] },
  { lat: 37.79, lng: -122.3903, label: "Google (San Francisco)", aliases: ["google sf", "google san francisco", "345 spear"] },
  // Cities
  { lat: 37.7749, lng: -122.4194, label: "San Francisco", aliases: ["san francisco", "sf", "the city"] },
  { lat: 37.6879, lng: -122.4702, label: "Daly City", aliases: ["daly city"] },
  { lat: 37.6547, lng: -122.4077, label: "South San Francisco", aliases: ["south san francisco", "south sf", "ssf"] },
  { lat: 37.6305, lng: -122.4111, label: "San Bruno", aliases: ["san bruno"] },
  { lat: 37.6003, lng: -122.3868, label: "Millbrae", aliases: ["millbrae"] },
  { lat: 37.5841, lng: -122.3661, label: "Burlingame", aliases: ["burlingame"] },
  { lat: 37.563, lng: -122.3255, label: "San Mateo", aliases: ["san mateo"] },
  { lat: 37.5202, lng: -122.2758, label: "Belmont", aliases: ["belmont"] },
  { lat: 37.5072, lng: -122.2605, label: "San Carlos", aliases: ["san carlos"] },
  { lat: 37.4852, lng: -122.2364, label: "Redwood City", aliases: ["redwood city", "rwc"] },
  { lat: 37.4529, lng: -122.1817, label: "Menlo Park", aliases: ["menlo park"] },
  { lat: 37.4419, lng: -122.143, label: "Palo Alto", aliases: ["palo alto"] },
  { lat: 37.4688, lng: -122.1411, label: "East Palo Alto", aliases: ["east palo alto", "epa"] },
  { lat: 37.3852, lng: -122.1141, label: "Los Altos", aliases: ["los altos"] },
  { lat: 37.3861, lng: -122.0839, label: "Mountain View", aliases: ["mountain view", "mtv"] },
  { lat: 37.3688, lng: -122.0363, label: "Sunnyvale", aliases: ["sunnyvale"] },
  { lat: 37.323, lng: -122.0322, label: "Cupertino", aliases: ["cupertino"] },
  { lat: 37.3541, lng: -121.9552, label: "Santa Clara", aliases: ["santa clara"] },
  { lat: 37.4323, lng: -121.8996, label: "Milpitas", aliases: ["milpitas"] },
  { lat: 37.3382, lng: -121.8863, label: "San Jose", aliases: ["san jose", "downtown san jose"] },
  { lat: 37.3897, lng: -121.8952, label: "North San Jose", aliases: ["north san jose"] },
  { lat: 37.2872, lng: -121.95, label: "Campbell", aliases: ["campbell"] },
  { lat: 37.8044, lng: -122.2712, label: "Oakland", aliases: ["oakland"] },
  { lat: 37.8715, lng: -122.273, label: "Berkeley", aliases: ["berkeley"] },
  // SF neighborhoods
  { lat: 37.7785, lng: -122.4056, label: "SoMa", aliases: ["soma", "south of market"] },
  { lat: 37.7706, lng: -122.3893, label: "Mission Bay", aliases: ["mission bay"] },
  { lat: 37.7599, lng: -122.4148, label: "Mission District", aliases: ["mission district", "the mission", "mission"] },
  { lat: 37.7759, lng: -122.4245, label: "Hayes Valley", aliases: ["hayes valley"] },
  { lat: 37.7609, lng: -122.435, label: "Castro", aliases: ["castro", "the castro"] },
  { lat: 37.7586, lng: -122.3884, label: "Dogpatch", aliases: ["dogpatch"] },
  { lat: 37.7578, lng: -122.4002, label: "Potrero Hill", aliases: ["potrero", "potrero hill"] },
  { lat: 37.753, lng: -122.486, label: "Sunset", aliases: ["sunset", "outer sunset", "inner sunset"] },
  { lat: 37.7799, lng: -122.4649, label: "Richmond District", aliases: ["richmond district", "the richmond"] },
  { lat: 37.8021, lng: -122.4369, label: "Marina", aliases: ["marina", "marina district"] },
  { lat: 37.806, lng: -122.4103, label: "North Beach", aliases: ["north beach"] },
  { lat: 37.793, lng: -122.4161, label: "Nob Hill", aliases: ["nob hill"] },
  { lat: 37.7502, lng: -122.4337, label: "Noe Valley", aliases: ["noe valley"] },
  { lat: 37.7946, lng: -122.3999, label: "Financial District", aliases: ["financial district", "fidi"] },
  { lat: 37.7955, lng: -122.3937, label: "Embarcadero", aliases: ["embarcadero"] },
];

/* Exact-alias or contained-alias match, longest alias wins so "mountain view
   caltrain" beats "mountain view". */
export function resolveLocal(q: string): Point | null {
  const t = (q || "").toLowerCase().replace(/[^a-z0-9&' ]+/g, " ").replace(/\s+/g, " ").trim();
  if (!t) return null;
  let best: { p: LocalPlace; len: number } | null = null;
  for (const p of LOCAL_PLACES) {
    for (const a of p.aliases) {
      const hit = t === a || t.includes(a);
      if (hit && (!best || a.length > best.len)) best = { p, len: a.length };
    }
  }
  return best ? { lat: best.p.lat, lng: best.p.lng, label: best.p.label, source: "local" } : null;
}

/* Full resolution: local table first (free, instant), then the geocode API for
   real addresses. Returns null only when both fail. */
export async function resolvePoint(q: string): Promise<Point | null> {
  const local = resolveLocal(q);
  // A query with digits is probably a street address — prefer the real geocoder,
  // keep local as the fallback. A plain place name resolves locally, instantly.
  const looksLikeAddress = /\d/.test(q);
  if (local && !looksLikeAddress) return local;
  try {
    const r = await fetch(`/api/geocode?q=${encodeURIComponent(q)}`);
    if (r.ok) {
      const j = await r.json();
      if (j && j.ok && typeof j.lat === "number" && typeof j.lng === "number") {
        return { lat: j.lat, lng: j.lng, label: j.label || q, source: "google" };
      }
    }
  } catch {
    /* offline / no key — local fallback below */
  }
  return local;
}

/* Market centroids from the listings that DO carry exact coordinates, so the
   ~half without them still get an approximate distance instead of vanishing
   from a point search. */
export function marketCentroids(listings: { market: string; lat?: number | null; lng?: number | null }[]): Record<string, { lat: number; lng: number }> {
  const acc: Record<string, { lat: number; lng: number; n: number }> = {};
  for (const l of listings) {
    if (l.lat == null || l.lng == null || !l.market) continue;
    const a = acc[l.market] || (acc[l.market] = { lat: 0, lng: 0, n: 0 });
    a.lat += l.lat;
    a.lng += l.lng;
    a.n++;
  }
  const out: Record<string, { lat: number; lng: number }> = {};
  for (const m in acc) if (acc[m].n >= 3) out[m] = { lat: acc[m].lat / acc[m].n, lng: acc[m].lng / acc[m].n };
  return out;
}

export function listingDistanceMiles(
  l: { lat?: number | null; lng?: number | null; market: string },
  point: Point,
  centroids: Record<string, { lat: number; lng: number }>
): { miles: number; exact: boolean } | null {
  if (l.lat != null && l.lng != null) return { miles: haversineMiles(l.lat, l.lng, point.lat, point.lng), exact: true };
  const c = centroids[l.market];
  if (c) return { miles: haversineMiles(c.lat, c.lng, point.lat, point.lng), exact: false };
  return null;
}

export const fmtMiles = (d: { miles: number; exact: boolean }) =>
  `${d.exact ? "" : "~"}${d.miles < 10 ? d.miles.toFixed(1) : Math.round(d.miles)} mi${d.exact ? "" : " (area)"}`;
