/* Durable request inbox between the dashboard and the repo-side agent
   (Claude/Codex runs of skills/bay-area-housing-hunt). Rides the existing
   hh_config table (anon CRUD, same pattern as configStore.ts) under an
   `agent_req:` key prefix — no new infrastructure.

   Lifecycle: dashboard submits {status:"open"} → a repo session answers with
   scripts/agent_inbox.py (status:"answered" + reply) → the user reads it here
   and dismisses (status:"closed"). */

const SB_URL = "https://kyqebsowglvzvncordtq.supabase.co";
const SB_ANON =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imt5cWVic293Z2x2enZuY29yZHRxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgyNzY5MDksImV4cCI6MjA5Mzg1MjkwOX0.Hd8A9H2ytvbLZM1LbIMpJZ8sgTFYdEb8DYW4YbD7q0I";
const REST = `${SB_URL}/rest/v1/hh_config`;
const headers: Record<string, string> = {
  apikey: SB_ANON,
  Authorization: `Bearer ${SB_ANON}`,
  "Content-Type": "application/json",
};

export type AgentRequest = {
  key: string;
  text: string;
  status: "open" | "answered" | "closed";
  reply?: string;
  created: string;
  answeredAt?: string;
};

export async function listAgentRequests(): Promise<AgentRequest[]> {
  const r = await fetch(`${REST}?key=like.agent_req:*&select=key,value&order=key.desc&limit=50`, { headers });
  if (!r.ok) throw new Error("listAgentRequests " + r.status);
  const rows: { key: string; value: any }[] = await r.json();
  return rows
    .map((row) => ({ key: row.key, ...(row.value || {}) }))
    .filter((x) => x.text && x.status !== "closed") as AgentRequest[];
}

export async function submitAgentRequest(text: string): Promise<AgentRequest> {
  const created = new Date().toISOString();
  // Sortable key: newest-first with the key.desc order above.
  const key = `agent_req:${created.replace(/[-:.TZ]/g, "").slice(0, 14)}-${Math.random().toString(36).slice(2, 6)}`;
  const value = { text, status: "open", created };
  const r = await fetch(REST, {
    method: "POST",
    headers: { ...headers, Prefer: "resolution=merge-duplicates,return=minimal" },
    body: JSON.stringify({ key, value, updated_at: created }),
  });
  if (!r.ok) throw new Error("submitAgentRequest " + r.status);
  return { key, ...value } as AgentRequest;
}

export async function closeAgentRequest(req: AgentRequest): Promise<void> {
  const value = { text: req.text, status: "closed", reply: req.reply, created: req.created, answeredAt: req.answeredAt };
  const r = await fetch(REST, {
    method: "POST",
    headers: { ...headers, Prefer: "resolution=merge-duplicates,return=minimal" },
    body: JSON.stringify({ key: req.key, value, updated_at: new Date().toISOString() }),
  });
  if (!r.ok) throw new Error("closeAgentRequest " + r.status);
}
