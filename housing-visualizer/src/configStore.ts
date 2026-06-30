/* Durable, cross-device store for the dashboard's CONFIG (profiles + region prefs).
   Backed by Supabase Postgres (project "SplitCheck") via its REST API — no SDK.
   localStorage stays the instant + offline layer in App.tsx; this syncs in the
   background so config survives a cache-clear and shows up on every device.

   The anon key is public by design (RLS-gated). The hh_config table allows anon CRUD,
   so this is a personal, non-secret store — fine for housing prefs, not for secrets.
   Mirrors marksStore.ts (same URL + anon key + headers + error-throw style). */

const SB_URL = "https://kyqebsowglvzvncordtq.supabase.co";
const SB_ANON =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imt5cWVic293Z2x2enZuY29yZHRxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgyNzY5MDksImV4cCI6MjA5Mzg1MjkwOX0.Hd8A9H2ytvbLZM1LbIMpJZ8sgTFYdEb8DYW4YbD7q0I";
const REST = `${SB_URL}/rest/v1/hh_config`;
const headers: Record<string, string> = {
  apikey: SB_ANON,
  Authorization: `Bearer ${SB_ANON}`,
  "Content-Type": "application/json",
};

export async function fetchConfig(): Promise<Record<string, unknown>> {
  const r = await fetch(`${REST}?select=key,value`, { headers });
  if (!r.ok) throw new Error("fetchConfig " + r.status);
  const rows: { key: string; value: unknown }[] = await r.json();
  const out: Record<string, unknown> = {};
  for (const row of rows) out[row.key] = row.value;
  return out;
}

export async function saveConfig(key: string, value: unknown): Promise<void> {
  const r = await fetch(REST, {
    method: "POST",
    headers: { ...headers, Prefer: "resolution=merge-duplicates,return=minimal" },
    body: JSON.stringify({ key, value, updated_at: new Date().toISOString() }),
  });
  if (!r.ok) throw new Error("saveConfig " + r.status);
}
