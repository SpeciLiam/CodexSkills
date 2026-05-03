import { useMemo, useState } from "react";
import { ArrowUpRight, Check, ClipboardCheck, Copy, Minus, X } from "lucide-react";
import { analyzeConnectionNote } from "../lib/outreach";
import type { EngineerSignal, OutreachLane, RecruiterSignal } from "../lib/types";

export type OutreachRowData = {
  key: string;
  lane: OutreachLane;
  company: string;
  role: string;
  postingKey: string;
  fitScore: number;
  status: string;
  contactName: string;
  profile: string;
  position: string;
  approval: string;
  outcome: string;
  route: string;
  connectionNote: string;
  lastChecked: string;
  notes: string;
  states: string[];
  recruiterSignal?: RecruiterSignal;
  engineerSignal?: EngineerSignal;
};

type SortMode = "priority" | "fit" | "recent" | "seniority";
type FilterId = "alumni" | "team" | "senior" | "fit9" | "owns" | "recruiterType";

const SENIORITY_RANK: Record<string, number> = {
  unknown: 0,
  junior: 1,
  mid: 2,
  senior: 3,
  staff: 4,
  principal: 5,
  manager: 6,
  director: 7,
  vp: 8,
};

export function OutreachModal({
  lane,
  rows,
  onClose,
  onSkip,
}: {
  lane: OutreachLane;
  rows: OutreachRowData[];
  onClose: () => void;
  onSkip?: (row: OutreachRowData) => void;
}) {
  const [sortMode, setSortMode] = useState<SortMode>("priority");
  const [filters, setFilters] = useState<Set<FilterId>>(() => new Set());
  const filteredRows = useMemo(() => applyOutreachFilters(rows, lane, filters, sortMode), [rows, lane, filters, sortMode]);
  const labels = lane === "recruiter"
    ? { eyebrow: "Recruiter batch", title: "Recruiter Work Queue", empty: "No labeled recruiter rows ready.", command: "python3 skills/linkedin-outreach/scripts/build_outreach_targets.py --contact-type recruiter --limit 20" }
    : { eyebrow: "Engineer batch", title: "Engineer Work Queue", empty: "No labeled engineer rows ready.", command: "python3 skills/linkedin-outreach/scripts/build_outreach_targets.py --contact-type engineer --limit 20" };

  const toggleFilter = (filter: FilterId) => {
    setFilters((current) => {
      const next = new Set(current);
      if (next.has(filter)) next.delete(filter);
      else next.add(filter);
      return next;
    });
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="outreach-modal batch-modal" role="dialog" aria-modal="true" aria-label={`${labels.title} review`} onMouseDown={(event) => event.stopPropagation()}>
        <header>
          <div>
            <p className="eyebrow">{labels.eyebrow}</p>
            <h2>{labels.title}</h2>
            <p>{filteredRows.length} shown of {rows.length} active rows.</p>
          </div>
          <button onClick={onClose} type="button" aria-label="Close"><X size={18} /></button>
        </header>
        <div className="outreach-toolbar">
          <label>
            Sort
            <select value={sortMode} onChange={(event) => setSortMode(event.target.value as SortMode)}>
              <option value="priority">Priority</option>
              <option value="fit">Fit desc</option>
              <option value="recent">Recently labeled</option>
              <option value="seniority">Seniority</option>
            </select>
          </label>
          <div className="outreach-filter-chips" aria-label={`${lane} filters`}>
            <FilterButton active={filters.has("alumni")} onClick={() => toggleFilter("alumni")}>Alumni only</FilterButton>
            {lane === "engineer" ? (
              <>
                <FilterButton active={filters.has("team")} onClick={() => toggleFilter("team")}>Team exact/adjacent</FilterButton>
                <FilterButton active={filters.has("senior")} onClick={() => toggleFilter("senior")}>Senior+ only</FilterButton>
              </>
            ) : (
              <>
                <FilterButton active={filters.has("owns")} onClick={() => toggleFilter("owns")}>Owns role only</FilterButton>
                <FilterButton active={filters.has("recruiterType")} onClick={() => toggleFilter("recruiterType")}>In-house / technical</FilterButton>
              </>
            )}
            <FilterButton active={filters.has("fit9")} onClick={() => toggleFilter("fit9")}>Fit &gt;= 9</FilterButton>
          </div>
        </div>
        <div className="modal-list batch-modal-list">
          {filteredRows.map((row, index) => (
            <OutreachRow row={row} displayIndex={index + 1} onSkip={onSkip} key={row.key} />
          ))}
          {!filteredRows.length && <OutreachEmptyState message={labels.empty} command={labels.command} />}
        </div>
      </section>
    </div>
  );
}

function FilterButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: string }) {
  return <button className={active ? "active" : ""} type="button" onClick={onClick}>{children}</button>;
}

export function OutreachRow({
  row,
  displayIndex,
  onSkip,
}: {
  row: OutreachRowData;
  displayIndex?: number;
  onSkip?: (row: OutreachRowData) => void;
}) {
  const [approved, setApproved] = useState(false);
  const flags = analyzeConnectionNote(row.connectionNote, {
    contactName: row.contactName,
    lane: row.lane,
    postingContext: { company: row.company, role: row.role, notes: row.notes, position: row.position },
  });
  const canApprove = isLabeledNotReached(row);
  const approveText = `Approve ${row.lane} outreach: ${row.company} - ${row.role} - ${row.contactName || "contact"}`;
  const researchNotes = meaningfulResearchNotes(row.notes);

  const approve = () => {
    void navigator.clipboard.writeText(approveText);
    setApproved(true);
    window.setTimeout(() => setApproved(false), 2400);
  };

  return (
    <article className={`batch-row active-role-row outreach-shared-row indexed lane-${row.lane} ${approved ? "copied" : ""}`}>
      {displayIndex && <span className="batch-index">{displayIndex}</span>}
      <div className="active-role-main">
        <strong>{row.company}</strong>
        <p>{row.role}</p>
        <small className="batch-contact">
          <span>{row.contactName || `Needs ${row.lane} label`}</span>
          {row.position && <em>{row.position}</em>}
        </small>
        <SignalStrip lane={row.lane} recruiterSignal={row.recruiterSignal} engineerSignal={row.engineerSignal} />
        {row.connectionNote && (
          <div className="note-quality">
            {flags.map((flag) => <span className={flag.passed ? "pass" : "fail"} key={flag.id}>{flag.label}</span>)}
          </div>
        )}
        <BatchDetails note={row.connectionNote} notes={researchNotes} />
      </div>
      <WorkStatePills states={row.states} />
      <b>{row.fitScore || "-"}</b>
      <div className="outreach-row-actions">
        {canApprove ? (
          <button className="approve-inline" type="button" onClick={approve} aria-label={approveText}>
            {approved ? <ClipboardCheck size={16} /> : <Check size={16} />}
          </button>
        ) : <span className="action-slot" />}
        {row.profile ? <a href={row.profile} target="_blank" rel="noreferrer" aria-label={`${row.contactName || row.company} LinkedIn`}><ArrowUpRight size={17} /></a> : <span className="action-slot" />}
        {onSkip ? (
          <button className="batch-ignore" type="button" onClick={() => onSkip(row)} aria-label={`Skip ${row.contactName || row.company}; find a new ${row.lane}`}>
            <X size={16} />
          </button>
        ) : <span className="action-slot" />}
      </div>
    </article>
  );
}

export function BatchDetails({ note, notes }: { note: string; notes: string }) {
  if (!note && !notes) return null;
  return (
    <dl className="batch-details">
      {note && (
        <div className="batch-detail-block note">
          <dt>Connection note</dt>
          <dd>{note}</dd>
        </div>
      )}
      {notes && (
        <div className="batch-detail-block research">
          <dt>Research notes</dt>
          <dd>{notes}</dd>
        </div>
      )}
    </dl>
  );
}

export function OutreachEmptyState({ message, command }: { message: string; command: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    void navigator.clipboard.writeText(command);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };
  return (
    <div className="outreach-empty-state">
      <p>{message}</p>
      <code>{command}</code>
      <button type="button" onClick={copy}>{copied ? <ClipboardCheck size={16} /> : <Copy size={16} />}</button>
    </div>
  );
}

function WorkStatePills({ states }: { states: string[] }) {
  return (
    <div className="state-pills">
      {states.map((state) => <span className={stateTone(state)} key={state}>{state}</span>)}
    </div>
  );
}

function SignalStrip({
  lane,
  recruiterSignal,
  engineerSignal,
}: {
  lane: OutreachLane;
  recruiterSignal?: RecruiterSignal;
  engineerSignal?: EngineerSignal;
}) {
  const signal = lane === "recruiter" ? recruiterSignal : engineerSignal;
  if (!signal) return null;
  return (
    <div className="signal-strip">
      <span className={`signal-chip seniority-${signal.seniority}`}>{seniorityLabel(signal.seniority)}</span>
      {signal.alumniMatch && <span className="signal-chip alumni">UGA alum</span>}
      {lane === "engineer" && engineerSignal && (
        <span className={`signal-chip team-${engineerSignal.teamMatch}`}>Team {engineerSignal.teamMatch}</span>
      )}
      {lane === "recruiter" && recruiterSignal && (
        <>
          <span className={`signal-chip recruiter-${recruiterSignal.recruiterType}`}>{recruiterSignal.recruiterType.replace("_", "-")}</span>
          {recruiterSignal.ownsRole === true && <span className="signal-chip owns-role"><Check size={12} /> owns role</span>}
          {recruiterSignal.ownsRole === null && <span className="signal-chip owns-unknown"><Minus size={12} /> owns?</span>}
        </>
      )}
      {signal.whyThisPerson && <span className="signal-chip why">{signal.whyThisPerson}</span>}
    </div>
  );
}

function seniorityLabel(seniority: string) {
  if (seniority === "unknown") return "Seniority ?";
  return seniority;
}

function isLabeledNotReached(row: OutreachRowData) {
  return Boolean(row.contactName || row.profile) && row.outcome.toLowerCase() === "not reached out" && row.approval.toLowerCase() !== "approved";
}

function meaningfulResearchNotes(notes: string) {
  const value = notes.trim();
  if (!value) return "";
  if (/^active application needs \w+ outreach\.?$/i.test(value)) return "";
  return value;
}

function applyOutreachFilters(rows: OutreachRowData[], lane: OutreachLane, filters: Set<FilterId>, sortMode: SortMode) {
  return rows
    .filter((row) => {
      const signal = lane === "recruiter" ? row.recruiterSignal : row.engineerSignal;
      if (filters.has("alumni") && !signal?.alumniMatch) return false;
      if (filters.has("fit9") && row.fitScore < 9) return false;
      if (lane === "engineer") {
        if (filters.has("team") && !["exact", "adjacent"].includes(row.engineerSignal?.teamMatch || "")) return false;
        if (filters.has("senior") && SENIORITY_RANK[row.engineerSignal?.seniority || "unknown"] < SENIORITY_RANK.senior) return false;
      } else {
        if (filters.has("owns") && row.recruiterSignal?.ownsRole !== true) return false;
        if (filters.has("recruiterType") && !["in_house", "technical"].includes(row.recruiterSignal?.recruiterType || "")) return false;
      }
      return true;
    })
    .sort((a, b) => sortValue(b, sortMode, lane) - sortValue(a, sortMode, lane) || a.company.localeCompare(b.company));
}

function sortValue(row: OutreachRowData, sortMode: SortMode, lane: OutreachLane) {
  if (sortMode === "fit") return row.fitScore;
  if (sortMode === "recent") return Date.parse(row.lastChecked || "") || 0;
  if (sortMode === "seniority") {
    if (lane === "recruiter") {
      const recruiterType = row.recruiterSignal?.recruiterType;
      return (recruiterType === "talent" ? 100 : recruiterType === "technical" ? 90 : 0) + SENIORITY_RANK[row.recruiterSignal?.seniority || "unknown"];
    }
    return (["manager", "director", "vp"].includes(row.engineerSignal?.seniority || "") ? 100 : 0) + SENIORITY_RANK[row.engineerSignal?.seniority || "unknown"];
  }
  const approved = row.approval.toLowerCase() === "approved" ? 30 : 0;
  const labeled = row.contactName || row.profile ? 10 : 0;
  return row.fitScore * 100 + approved + labeled;
}

function stateTone(state: string) {
  if (state.startsWith("Approved")) return "approved";
  if (state.startsWith("Labeled")) return "labeled";
  return "research";
}
