/* Vercel serverless function: geocode an arbitrary place/address for point
   search. Holds the Google Maps key SERVER-SIDE (same env var as /api/commute).
   Biased to the Bay Area so "Main St" resolves to the local one.

   GET /api/geocode?q=<text>  →  { ok, lat, lng, label } | { ok: false, reason } */

declare const process: { env: Record<string, string | undefined> };

const KEY = process.env.GOOGLE_MAPS_API_KEY || "";
const ENABLED = process.env.HOUSING_ENABLE_GOOGLE_PROXY === "true";
const GEOCODE = "https://maps.googleapis.com/maps/api/geocode/json";
// SW / NE corners of the hunt area (Santa Cruz mountains → North Bay edge).
const BOUNDS = "36.9,-122.7|38.1,-121.6";

export default async function handler(req: any, res: any) {
  if (!ENABLED) return res.status(503).json({ ok: false, reason: "Google proxy disabled until private/authenticated deployment is configured" });
  if (!KEY) return res.status(503).json({ ok: false, reason: "GOOGLE_MAPS_API_KEY not configured" });
  const q = String((req.query || {}).q || "").trim();
  if (!q) return res.status(400).json({ ok: false, reason: "q required" });
  if (q.length > 200) return res.status(400).json({ ok: false, reason: "q too long" });
  try {
    const url = `${GEOCODE}?address=${encodeURIComponent(q)}&bounds=${encodeURIComponent(BOUNDS)}&components=country:US&key=${KEY}`;
    const r = await fetch(url);
    if (!r.ok) throw new Error(`geocode ${r.status}`);
    const j: any = await r.json();
    const hit = j?.results?.[0];
    const loc = hit?.geometry?.location;
    if (!hit || typeof loc?.lat !== "number" || typeof loc?.lng !== "number") {
      return res.status(200).json({ ok: false, reason: j?.status || "no match" });
    }
    // Addresses don't move — cache aggressively at the edge.
    res.setHeader("Cache-Control", "s-maxage=604800, stale-while-revalidate=2592000");
    return res.status(200).json({
      ok: true,
      lat: loc.lat,
      lng: loc.lng,
      label: hit.formatted_address || q,
    });
  } catch (e: any) {
    return res.status(500).json({ ok: false, reason: String(e?.message || e) });
  }
}
