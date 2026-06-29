/* Durable, cross-device store for per-listing marks (checked / promising / skip).
   Backed by Supabase Postgres (project "SplitCheck") via its REST API — no SDK.
   localStorage stays the instant + offline layer in App.tsx; this syncs in the
   background so marks survive a cache-clear and show up on every device.

   The anon key is public by design (RLS-gated). The hh_marks table allows anon CRUD,
   so this is a personal, non-secret store — fine for housing tags, not for secrets. */

const SB_URL = "https://kyqebsowglvzvncordtq.supabase.co";
const SB_ANON =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imt5cWVic293Z2x2enZuY29yZHRxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgyNzY5MDksImV4cCI6MjA5Mzg1MjkwOX0.Hd8A9H2ytvbLZM1LbIMpJZ8sgTFYdEb8DYW4YbD7q0I";
const REST = `${SB_URL}/rest/v1/hh_marks`;
const headers: Record<string, string> = {
  apikey: SB_ANON,
  Authorization: `Bearer ${SB_ANON}`,
  "Content-Type": "application/json",
};

export async function fetchRemoteMarks(): Promise<Record<string, string>> {
  const r = await fetch(`${REST}?select=listing_key,mark`, { headers });
  if (!r.ok) throw new Error("fetchRemoteMarks " + r.status);
  const rows: { listing_key: string; mark: string }[] = await r.json();
  const out: Record<string, string> = {};
  for (const row of rows) if (row.mark) out[row.listing_key] = row.mark;
  return out;
}

export async function upsertRemoteMark(listingKey: string, mark: string): Promise<void> {
  const r = await fetch(REST, {
    method: "POST",
    headers: { ...headers, Prefer: "resolution=merge-duplicates,return=minimal" },
    body: JSON.stringify({ listing_key: listingKey, mark, updated_at: new Date().toISOString() }),
  });
  if (!r.ok) throw new Error("upsertRemoteMark " + r.status);
}

export async function deleteRemoteMark(listingKey: string): Promise<void> {
  const r = await fetch(`${REST}?listing_key=eq.${encodeURIComponent(listingKey)}`, { method: "DELETE", headers });
  if (!r.ok) throw new Error("deleteRemoteMark " + r.status);
}
