/* Agent panel — one chat-style point of contact for the whole hunt.
   Two lanes, one box:
     • Dashboard commands parse locally (src/agent.ts) and apply instantly —
       filters, sort, point search, Inspire Me, profiles.
     • Everything else (new sources, pipeline changes, data fixes) queues into
       the durable inbox (agentStore.ts). Repo-side runs answer with
       scripts/agent_inbox.py, and the replies appear right here.
   Prefix a message with "request:" to force the queue lane. */

import { useEffect, useRef, useState, type CSSProperties } from "react";
import { listAgentRequests, submitAgentRequest, closeAgentRequest, type AgentRequest } from "./agentStore";

type Msg = { who: "you" | "agent"; text: string };
const CHAT_KEY = "hh-agent-chat-v1";
const loadChat = (): Msg[] => {
  try { return JSON.parse(localStorage.getItem(CHAT_KEY) || "[]"); } catch { return []; }
};

const SUGGESTIONS = [
  "2bd under $3k near Sunnyvale Caltrain",
  "inspire me",
  "cheapest rooms in SF",
  "within 1.5 miles of the office",
  "request: add a new listing source",
];

export default function AgentPanel({ runCommand }: { runCommand: (text: string) => { reply: string } | null }) {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [msgs, setMsgs] = useState<Msg[]>(loadChat);
  const [requests, setRequests] = useState<AgentRequest[]>([]);
  const [busy, setBusy] = useState(false);
  const logRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    try { localStorage.setItem(CHAT_KEY, JSON.stringify(msgs.slice(-40))); } catch { /* ignore */ }
    // Keep the newest exchange in view.
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [msgs, open]);

  const refreshRequests = () => {
    listAgentRequests().then(setRequests).catch(() => {});
  };
  useEffect(() => { if (open) refreshRequests(); }, [open]);
  // Light background check so the "answered" badge appears without opening the panel.
  useEffect(() => {
    refreshRequests();
    const id = setInterval(refreshRequests, 120000);
    return () => clearInterval(id);
  }, []);

  const say = (who: Msg["who"], text: string) => setMsgs((m) => [...m, { who, text }]);

  const queueRequest = async (text: string) => {
    setBusy(true);
    try {
      await submitAgentRequest(text);
      say("agent", "Queued for the repo agent — it picks requests up on its next run and the answer will appear here.");
      refreshRequests();
    } catch {
      say("agent", "Couldn't reach the inbox (offline?). Try again in a bit.");
    } finally {
      setBusy(false);
    }
  };

  const send = async (raw: string) => {
    const text = raw.trim();
    if (!text || busy) return;
    setInput("");
    say("you", text);
    const forced = text.match(/^(?:request|todo|ask)\s*:\s*(.+)$/i);
    if (forced) return queueRequest(forced[1]);
    const res = runCommand(text);
    if (res) return say("agent", res.reply);
    return queueRequest(text);
  };

  const dismiss = async (req: AgentRequest) => {
    setRequests((r) => r.filter((x) => x.key !== req.key));
    try { await closeAgentRequest(req); } catch { /* re-appears on next refresh; fine */ }
  };

  const answered = requests.filter((r) => r.status === "answered").length;

  const fab: CSSProperties = {
    position: "fixed", right: 22, bottom: 22, zIndex: 60, cursor: "pointer",
    display: "flex", alignItems: "center", gap: 8, padding: "12px 18px", borderRadius: 999,
    border: "none", background: "var(--accent)", color: "#fffdf8", fontSize: 14, fontWeight: 700,
    fontFamily: "'Space Grotesk',sans-serif", boxShadow: "0 4px 18px rgba(36,94,168,0.35)",
  };
  const bubble = (who: Msg["who"]): CSSProperties => ({
    maxWidth: "85%", alignSelf: who === "you" ? "flex-end" : "flex-start",
    background: who === "you" ? "var(--accent)" : "#f0ece3",
    color: who === "you" ? "#fffdf8" : "#1c1a17",
    padding: "8px 12px", borderRadius: 12, fontSize: 12.5, lineHeight: 1.45, whiteSpace: "pre-wrap",
  });

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} style={fab} title="Ask the agent — filters, point search, inspiration, or queue a request for the pipeline">
        ✦ Agent{answered ? <span style={{ background: "#fffdf8", color: "var(--accent)", borderRadius: 999, fontSize: 11, fontWeight: 800, padding: "1px 7px" }}>{answered}</span> : null}
      </button>
    );
  }

  return (
    <div style={{ position: "fixed", right: 22, bottom: 22, zIndex: 60, width: 390, maxWidth: "calc(100vw - 30px)", maxHeight: "min(640px, calc(100vh - 40px))", display: "flex", flexDirection: "column", background: "#fffdf8", border: "1px solid #e0dacd", borderRadius: 16, boxShadow: "0 8px 40px rgba(28,26,23,0.22)", overflow: "hidden" }}>
      {/* header */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "13px 16px", background: "var(--accent)", color: "#fffdf8" }}>
        <div style={{ fontFamily: "'Space Grotesk',sans-serif", fontSize: 15, fontWeight: 700 }}>✦ Housing Agent</div>
        <div style={{ fontSize: 11, opacity: 0.85 }}>filters · point search · inspire · pipeline requests</div>
        <button onClick={() => setOpen(false)} style={{ marginLeft: "auto", border: "none", background: "transparent", color: "#fffdf8", cursor: "pointer", fontSize: 18, lineHeight: 1 }}>×</button>
      </div>

      {/* requests inbox */}
      {requests.length > 0 && (
        <div style={{ padding: "10px 14px", borderBottom: "1px solid #ece8df", background: "#fbf9f3", maxHeight: 170, overflowY: "auto" }}>
          <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: "0.07em", color: "#8a8378", fontWeight: 700, marginBottom: 6 }}>
            Pipeline requests
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {requests.map((r) => (
              <div key={r.key} style={{ border: `1px solid ${r.status === "answered" ? "var(--accent)" : "#e6e1d6"}`, borderRadius: 10, padding: "7px 10px", background: "#fffdf8" }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                  <span style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.05em", color: r.status === "answered" ? "var(--accent)" : "#b07d1a" }}>
                    {r.status === "answered" ? "ANSWERED" : "QUEUED"}
                  </span>
                  <span style={{ fontSize: 12, fontWeight: 600, color: "#1c1a17", flex: 1, minWidth: 0 }}>{r.text}</span>
                  <button onClick={() => dismiss(r)} title="Dismiss" style={{ border: "none", background: "transparent", cursor: "pointer", color: "#b0a99c", fontSize: 14, lineHeight: 1, padding: 0 }}>×</button>
                </div>
                {r.reply && <div style={{ fontSize: 11.5, color: "#4a5a6d", marginTop: 4, lineHeight: 1.4, whiteSpace: "pre-wrap" }}>{r.reply}</div>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* chat log */}
      <div ref={logRef} style={{ flex: 1, overflowY: "auto", padding: "12px 14px", display: "flex", flexDirection: "column", gap: 8, minHeight: 140 }}>
        {msgs.length === 0 && (
          <div style={{ fontSize: 12.5, color: "#6f6a61", lineHeight: 1.5 }}>
            Tell me what you want in one line — I set the filters, pin a point, or pull an inspiration shortlist.
            Anything I can't do in the browser (new sources, data fixes) I queue for the repo agent, and its answer lands back here.
          </div>
        )}
        {msgs.map((m, i) => <div key={i} style={bubble(m.who)}>{m.text}</div>)}
      </div>

      {/* suggestions */}
      <div style={{ display: "flex", gap: 6, padding: "0 14px 10px", flexWrap: "wrap" }}>
        {SUGGESTIONS.map((s) => (
          <button key={s} onClick={() => send(s)} style={{ cursor: "pointer", border: "1px solid #e0dacd", background: "#fdfbf6", color: "#6f6a61", borderRadius: 999, padding: "4px 10px", fontSize: 11, fontWeight: 600 }}>
            {s}
          </button>
        ))}
      </div>

      {/* input */}
      <form
        onSubmit={(e) => { e.preventDefault(); send(input); }}
        style={{ display: "flex", gap: 8, padding: "10px 14px 14px", borderTop: "1px solid #ece8df" }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder='e.g. "2bd in Mountain View under $3k" or "request: …"'
          style={{ flex: 1, border: "1px solid #e0dacd", background: "#fdfbf6", borderRadius: 10, padding: "9px 12px", fontSize: 13, outline: "none", color: "#1c1a17" }}
        />
        <button type="submit" disabled={busy} style={{ border: "none", background: "var(--accent)", color: "#fffdf8", borderRadius: 10, padding: "9px 16px", fontSize: 13, fontWeight: 700, cursor: "pointer", opacity: busy ? 0.6 : 1 }}>
          {busy ? "…" : "Send"}
        </button>
      </form>
    </div>
  );
}
