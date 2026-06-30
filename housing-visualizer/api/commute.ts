/* Vercel serverless function: optimal departure for a home -> office commute.
   Holds the Google Maps key SERVER-SIDE (never bundled). Calls the Google Routes
   API for transit (real Caltrain schedule, so Express/Limited/Local are honored),
   driving, and biking, and returns each mode's "leave by" + the key transit legs.

   GET /api/commute?origin=<addr>&dest=<addr>&arrival=<RFC3339>
   The client computes `arrival` (next Mon/Wed/Thu at the person's time, Pacific). */

const KEY = process.env.GOOGLE_MAPS_API_KEY || "";
const ROUTES = "https://routes.googleapis.com/directions/v2:computeRoutes";

const secs = (d: any): number => (typeof d === "string" ? parseInt(d.replace(/[^\d]/g, ""), 10) || 0 : 0);
const isoMinus = (iso: string, seconds: number) => new Date(new Date(iso).getTime() - seconds * 1000).toISOString();

async function callRoutes(body: any, fieldMask: string): Promise<any> {
  const r = await fetch(ROUTES, {
    method: "POST",
    headers: { "X-Goog-Api-Key": KEY, "Content-Type": "application/json", "X-Goog-FieldMask": fieldMask },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`routes ${r.status}: ${(await r.text()).slice(0, 180)}`);
  return r.json();
}

function parseTransit(j: any, arrivalISO: string) {
  const route = j?.routes?.[0];
  if (!route) return { ok: false, reason: "no transit route" };
  const steps: any[] = (route.legs || []).flatMap((l: any) => l.steps || []);
  let preWalk = 0;
  let seenTransit = false;
  const legs: any[] = [];
  let firstDep: string | null = null;
  let lastArr: string | null = null;
  let postWalk = 0;
  for (const s of steps) {
    if (s.travelMode === "TRANSIT" && s.transitDetails) {
      seenTransit = true;
      postWalk = 0;
      const td = s.transitDetails;
      const dep = td.stopDetails?.departureTime, arr = td.stopDetails?.arrivalTime;
      if (!firstDep) firstDep = dep || null;
      if (arr) lastArr = arr;
      legs.push({
        line: td.transitLine?.name || td.transitLine?.nameShort || "transit",
        vehicle: td.transitLine?.vehicle?.type || "",
        from: td.stopDetails?.departureStop?.name || "",
        to: td.stopDetails?.arrivalStop?.name || "",
        dep, arr, stops: td.stopCount ?? null,
        rail: (td.transitLine?.vehicle?.type || "").includes("RAIL"),
      });
    } else {
      const w = secs(s.staticDuration);
      if (!seenTransit) preWalk += w;
      else postWalk += w;
    }
  }
  const total = secs(route.duration);
  // leave home = first scheduled boarding minus the walk to it; fall back to arrival - total
  const leaveBy = firstDep ? isoMinus(firstDep, preWalk) : isoMinus(arrivalISO, total);
  const arriveAt = lastArr ? new Date(new Date(lastArr).getTime() + postWalk * 1000).toISOString() : arrivalISO;
  return { ok: true, mode: "transit", leaveBy, arriveAt, durationMin: Math.round(total / 60), legs };
}

function parseSimple(j: any, arrivalISO: string, mode: string) {
  const route = j?.routes?.[0];
  if (!route) return { ok: false, reason: `no ${mode} route` };
  const total = secs(route.duration);
  return { ok: true, mode, leaveBy: isoMinus(arrivalISO, total), arriveAt: arrivalISO, durationMin: Math.round(total / 60), legs: [] };
}

export default async function handler(req: any, res: any) {
  if (!KEY) return res.status(503).json({ error: "GOOGLE_MAPS_API_KEY not configured" });
  const { origin, dest, arrival } = req.query || {};
  if (!origin || !dest || !arrival) return res.status(400).json({ error: "origin, dest, arrival required" });
  const base = { origin: { address: String(origin) }, destination: { address: String(dest) } };
  try {
    const [transit, drive, bike] = await Promise.all([
      callRoutes(
        { ...base, travelMode: "TRANSIT", arrivalTime: String(arrival), transitPreferences: { routingPreference: "LESS_WALKING" } },
        "routes.duration,routes.legs.steps.travelMode,routes.legs.steps.staticDuration,routes.legs.steps.transitDetails.transitLine.name,routes.legs.steps.transitDetails.transitLine.nameShort,routes.legs.steps.transitDetails.transitLine.vehicle.type,routes.legs.steps.transitDetails.stopCount,routes.legs.steps.transitDetails.stopDetails.departureTime,routes.legs.steps.transitDetails.stopDetails.arrivalTime,routes.legs.steps.transitDetails.stopDetails.departureStop.name,routes.legs.steps.transitDetails.stopDetails.arrivalStop.name"
      ).then((j) => parseTransit(j, String(arrival))).catch((e) => ({ ok: false, reason: String(e.message || e) })),
      // Routes DRIVE does NOT accept arrivalTime; for a traffic-aware estimate it needs a
      // future departureTime. Depart ~1h before the target arrival so the duration reflects
      // rush-hour traffic, then leaveBy = arrival - duration (parseSimple). Plain DRIVE
      // (free-flow) only as a last-resort fallback.
      (async () => {
        try {
          const j = await callRoutes(
            { ...base, travelMode: "DRIVE", departureTime: isoMinus(String(arrival), 3600), routingPreference: "TRAFFIC_AWARE" },
            "routes.duration"
          );
          return parseSimple(j, String(arrival), "drive");
        } catch {
          try {
            return parseSimple(await callRoutes({ ...base, travelMode: "DRIVE" }, "routes.duration"), String(arrival), "drive");
          } catch (e: any) {
            return { ok: false, reason: String(e?.message || e) };
          }
        }
      })(),
      callRoutes({ ...base, travelMode: "BICYCLE" }, "routes.duration")
        .then((j) => parseSimple(j, String(arrival), "bike")).catch((e) => ({ ok: false, reason: String(e.message || e) })),
    ]);
    res.setHeader("Cache-Control", "s-maxage=900, stale-while-revalidate=3600");
    return res.status(200).json({ arrival, transit, drive, bike });
  } catch (e: any) {
    return res.status(500).json({ error: String(e?.message || e) });
  }
}
