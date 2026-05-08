import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Activity,
  ArrowUpRight,
  BriefcaseBusiness,
  CalendarDays,
  ExternalLink,
  Filter,
  Info,
  Link as LinkIcon,
  MailCheck,
  Network,
  Radar,
  Route,
  Search,
  Send,
  Sparkles,
  Target,
  TerminalSquare,
  Users,
  X,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  Pie,
  PieChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar as RadarShape,
  RadarChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import rawData from "./data/tracker-data.json";
import rawPipelineMetrics from "./data/pipeline-metrics.json";
import { OutreachModal as SharedOutreachModal, OutreachRow as SharedOutreachRow, type OutreachRowData } from "./components/Outreach";
import { hostFromUrl, percent, readableDate } from "./lib/format";
import type { Application, EngineerBatch, JobIntake, OutreachRoleBucket, PipelineMetrics, Prospect, RecruiterBatch, TrackerData } from "./lib/types";

const data = rawData as TrackerData;
const pipelineMetrics = rawPipelineMetrics as PipelineMetrics;

const COLORS = ["#55d6be", "#f7b267", "#f25f5c", "#70a1ff", "#b388ff", "#f4d35e", "#8dd7cf", "#ff8fab"];
const STATUS_TONE: Record<string, string> = {
  Applied: "good",
  Interviewing: "hot",
  "Online Assessment": "hot",
  Rejected: "bad",
  "Resume Tailored": "cool",
  Offer: "hot",
};

const MANUAL_STATUS = "Manual Apply Needed";
const NOT_APPLIED_FILTER = "Not Applied";
const BATCH_IGNORE_STORAGE_KEY = "application-visualizer-ignored-batch-contacts";
const OUTREACH_TABLE_PREVIEW_LIMIT = 10;

const NAV_ITEMS = [
  { id: "overview", label: "Overview" },
  { id: "actions", label: "Actions" },
  { id: "trends", label: "Trends" },
  { id: "intake", label: "Intake" },
  { id: "outreach", label: "Outreach" },
  { id: "browser", label: "Browser" },
  { id: "pipeline", label: "Pipeline" },
] as const;

type TabId = (typeof NAV_ITEMS)[number]["id"];

const INFO_COPY = {
  actions: "A practical action board. Roles are grouped by what to do next: apply, follow up, prepare for interviews or assessments, monitor, or deprioritize closed/rejected roles. Cards are sorted by fit score so the strongest opportunities stay visible.",
  velocity: "Shows how the pipeline grew over time. The filled curve is cumulative tracked roles, while the line highlights applications submitted on each date.",
  dailyApplications: "Tracks how many applications were submitted each day, then pairs it with recruiter and engineer reach-outs logged in tracker notes.",
  status: "Breaks the tracker into current outcomes such as tailored, applied, interviewing, assessment, rejected, or offer.",
  fit: "Counts roles by fit score, making it easy to see whether the pipeline is concentrated around high-fit opportunities.",
  source: "Compares where roles are coming from, so you can see which channels are feeding the most opportunities.",
  role: "Plots visible applications by fit score and status. It is useful for spotting high-fit roles that are still only tailored or need action.",
  radar: "Summarizes campaign health across applied rate, high-fit share, reach-out coverage, recruiter coverage, and active share.",
  stageSnake: "Maps each role to the deepest observed process stage using status plus tracker notes, then shows where applications are still alive or rejected.",
  recruiters: "Lists applications with a known recruiter or LinkedIn path, sorted toward stronger fit so outreach targets are easy to open.",
  intake: "Shows fresh LinkedIn and Greenhouse jobs discovered by the hourly intake listener before they become tailored application rows.",
  gaps: "Highlights high-fit reach-out rows that still need more prospects or ready email addresses.",
  pipeline: "Shows recent intake and application health from outcomes, the SQLite mirror, and capture cache, then keeps the skill runbook close by.",
} as const;

const PIPELINE_MODES = [
  {
    name: "Job Intake Listener",
    command: "Codex Automation: .agents/automations/hourly-job-intake.md",
    description: "Schedule this hourly in Codex Automations for fresh LinkedIn and Greenhouse jobs. Codex captures browser results, then uses job-intake to dedupe and queue the strongest early-career roles.",
  },
  {
    name: "Full Pipeline",
    command: "python3 skills/recruiting-pipeline/scripts/build_daily_recruiting_plan.py",
    description: "Ask Codex to start here for a recruiting session. It sequences status refresh, resume/apply work, LinkedIn outreach, prospecting, prep, and dashboard refresh.",
  },
  {
    name: "LinkedIn Only",
    command: "python3 skills/recruiting-pipeline/scripts/build_daily_recruiting_plan.py --mode linkedin",
    description: "Ask Codex to run this when you only want outbound networking. It keeps recruiter and engineer lanes separate.",
  },
  {
    name: "Resume Tailor",
    command: "python3 skills/recruiting-pipeline/scripts/build_daily_recruiting_plan.py --mode resume",
    description: "Ask Codex to run this when you have a new job link or pasted posting and want resume plus follow-through.",
  },
  {
    name: "Finish Applications",
    command: "python3 skills/finish-applications/scripts/build_application_queue.py --limit 10",
    description: "Ask Codex to run this when tailored resumes are ready and you want the unapplied rows submitted with minimal interruption.",
  },
  {
    name: "Recruiter Lane",
    command: "python3 skills/recruiting-pipeline/scripts/build_daily_recruiting_plan.py --mode recruiter",
    description: "Ask Codex for recruiter-only outreach. It focuses on talent, university, and technical recruiter contacts.",
  },
  {
    name: "Recruiter Batch",
    command: "python3 skills/linkedin-outreach/scripts/build_outreach_targets.py --contact-type recruiter --limit 20",
    description: "Ask Codex to prepare recruiter outreach through the generalized LinkedIn lane workflow.",
  },
  {
    name: "Engineer Lane",
    command: "python3 skills/recruiting-pipeline/scripts/build_daily_recruiting_plan.py --mode engineer",
    description: "Ask Codex for engineer-only outreach. It focuses on UGA alumni, team-aligned engineers, or credible peer contacts.",
  },
  {
    name: "Dashboard Refresh",
    command: "python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py && cd application-visualizer && npm run build",
    description: "Ask Codex to rebuild the dashboard after tracker, outreach, or prospect changes.",
  },
  {
    name: "Notion Mirror",
    command: "python3 skills/notion-application-sync/scripts/sync_applications_to_notion.py --dry-run",
    description: "Ask Codex to run this only when you want the optional Notion mirror checked or synced.",
  },
];

const OPTIMAL_COMMAND_FLOW = [
  {
    step: "1",
    name: "Plan the day",
    command: "python3 skills/recruiting-pipeline/scripts/build_daily_recruiting_plan.py",
    note: "Start here. This ranks the work before opening Gmail, LinkedIn, or tailoring another resume.",
  },
  {
    step: "2",
    name: "Refresh application status",
    command: "python3 skills/gmail-application-refresh/scripts/build_refresh_targets.py --limit 20",
    note: "Check active rows for confirmations, rejections, OAs, and interviews before more outreach.",
  },
  {
    step: "3",
    name: "Tailor new roles",
    command: "python3 skills/recruiting-pipeline/scripts/build_daily_recruiting_plan.py --mode resume",
    note: "Use this lane when adding a new role or tailoring a resume before application submission.",
  },
  {
    step: "4",
    name: "Finish applications",
    command: "python3 skills/finish-applications/scripts/build_application_queue.py --limit 10",
    note: "Ask Codex to work through high-fit tailored rows that are still unapplied, submit when possible, and ask only for blockers.",
  },
  {
    step: "5",
    name: "Batch recruiter outreach",
    command: "python3 skills/linkedin-outreach/scripts/build_outreach_targets.py --contact-type recruiter --limit 20",
    note: "Use this before a send pass. Codex labels recruiter rows, drafts exact notes, and can send the approved batch after one action-time confirmation.",
  },
  {
    step: "6",
    name: "Send recruiter batch",
    command: "Use linkedin-outreach: show Approved + Not reached out recruiter rows, confirm once, then Connect with note",
    note: "The approval is batch-level, not per recruiter. After confirmation, Codex keeps going until the approved queue is done, you stop it, or LinkedIn/browser state blocks progress.",
  },
  {
    step: "7",
    name: "Engineer outreach lane",
    command: "python3 skills/linkedin-outreach/scripts/build_outreach_targets.py --contact-type engineer --limit 20",
    note: "Ask Codex to run this as a separate lane. It finds one engineer, UGA alum, or relevant employee per role.",
  },
  {
    step: "8",
    name: "Fill prospect gaps",
    command: "python3 skills/company-prospecting/scripts/build_company_prospect_targets.py --limit 20",
    note: "Use this when LinkedIn lanes need deeper company-level people or Apollo-ready email candidates.",
  },
  {
    step: "9",
    name: "Prep hot opportunities",
    command: "python3 skills/recruiting-pipeline/scripts/build_daily_recruiting_plan.py --mode prep",
    note: "Pull interviews and online assessments to the top so prep work does not get buried under new applications.",
  },
  {
    step: "10",
    name: "Rebuild dashboard",
    command: "python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py && cd application-visualizer && npm run build",
    note: "Run after tracker or outreach edits so the website reflects the latest markdown data.",
  },
  {
    step: "11",
    name: "Optional Notion mirror",
    command: "python3 skills/notion-application-sync/scripts/sync_applications_to_notion.py --dry-run",
    note: "Keep this outside the fast path. Use the 12-hour automation or run it manually after checking the dry run.",
  },
];

const PARALLEL_WORKSTREAMS = [
  {
    name: "1. Snapshot",
    text: "Refresh data once so every lane works from the same tracker state.",
    command: "python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py",
  },
  {
    name: "2. Recruiter workstream",
    text: "One Codex run owns recruiter/talent contacts and records only recruiter fields.",
    command: "python3 skills/linkedin-outreach/scripts/build_outreach_targets.py --contact-type recruiter --format json",
  },
  {
    name: "3. Engineer workstream",
    text: "A second Codex run owns engineer/alumni/peer contacts and records only engineer fields.",
    command: "python3 skills/linkedin-outreach/scripts/build_outreach_targets.py --contact-type engineer --format json",
  },
  {
    name: "4. Merge safely",
    text: "Both lanes write through the outreach updater, then Codex refreshes the dashboard.",
    command: "python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py && cd application-visualizer && npm run build",
  },
];

const SKILL_CARDS = [
  {
    name: "recruiting-pipeline",
    role: "Orchestrator",
    text: "Chooses the next best recruiting moves and supports focused modes for LinkedIn, resume tailoring, prospecting, prep, status, and dashboard work.",
  },
  {
    name: "resume-tailor",
    role: "Role intake",
    text: "Creates a company-specific one-page resume, renders the PDF, updates the markdown tracker, and decides fit score plus Reach Out defaults.",
  },
  {
    name: "finish-applications",
    role: "Application submitter",
    text: "Builds a ready-unapplied queue, submits applications with tailored resume PDFs, asks only for blocking form answers, and records confirmed submissions.",
  },
  {
    name: "linkedin-outreach",
    role: "Networking",
    text: "Builds lane-aware outreach queues, drafts connection notes, and records each successful invite back into the tracker.",
  },
  {
    name: "linkedin-outreach-batch",
    role: "Compatibility",
    text: "Thin wrapper kept for existing batch markdown manifests while linkedin-outreach owns the generalized lane workflow.",
  },
  {
    name: "company-prospecting",
    role: "People search",
    text: "Maintains deeper company prospect lists and flags missing recruiter or engineer lanes before Apollo email lookup.",
  },
  {
    name: "gmail-application-refresh",
    role: "Status sync",
    text: "Reviews application emails and updates statuses for confirmations, rejections, interviews, and online assessments when confidence is high.",
  },
  {
    name: "application-visualizer-refresh",
    role: "Data build",
    text: "Turns markdown tracker data into the normalized JSON cache this website uses for charts, filters, outreach gaps, and action views.",
  },
  {
    name: "notion-application-sync",
    role: "Optional mirror",
    text: "Matches the generated website data cache into Notion on demand or every 12 hours, while keeping markdown and JSON as the fast source of truth.",
  },
];

function tabFromHash(hash: string): TabId {
  const candidate = hash.replace("#", "");
  return NAV_ITEMS.some((item) => item.id === candidate) ? (candidate as TabId) : "overview";
}

function App() {
  const [activeTab, setActiveTab] = useState<TabId>(() => tabFromHash(window.location.hash));
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("All");
  const [minFit, setMinFit] = useState(0);
  const [openOutreachLane, setOpenOutreachLane] = useState<"recruiter" | "engineer" | null>(null);
  const [openBatchLane, setOpenBatchLane] = useState<"recruiter" | "engineer" | null>(null);
  const [selectedOutreach, setSelectedOutreach] = useState<{ app: Application; lane: "recruiter" | "engineer" } | null>(null);
  const [selectedReachedOutRole, setSelectedReachedOutRole] = useState<{ lane: "recruiter" | "engineer"; group: OutreachRoleBucket } | null>(null);
  const [openReachedOutLane, setOpenReachedOutLane] = useState<"recruiter" | "engineer" | null>(null);
  const [copiedResumePath, setCopiedResumePath] = useState("");
  const [ignoredBatchContacts, setIgnoredBatchContacts] = useState<Set<string>>(() => readIgnoredBatchContacts());

  useEffect(() => {
    const syncHash = () => setActiveTab(tabFromHash(window.location.hash));
    window.addEventListener("hashchange", syncHash);
    return () => window.removeEventListener("hashchange", syncHash);
  }, []);

  useEffect(() => {
    window.localStorage.setItem(BATCH_IGNORE_STORAGE_KEY, JSON.stringify([...ignoredBatchContacts]));
  }, [ignoredBatchContacts]);

  const ignoreBatchContact = (key: string) => {
    setIgnoredBatchContacts((current) => {
      const next = new Set(current);
      next.add(key);
      return next;
    });
  };

  const selectTab = (tab: TabId) => {
    setActiveTab(tab);
    window.history.replaceState(null, "", `#${tab}`);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const statuses = useMemo(() => ["All", NOT_APPLIED_FILTER, ...data.stats.statusCounts.map((item) => item.name)], []);
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return data.applications.filter((app) => {
      const matchesText =
        !needle ||
        [app.company, app.role, app.location, app.source, app.recruiterContact, app.engineerContact, app.notes].some((value) =>
          value.toLowerCase().includes(needle),
        );
      const matchesStatus =
        status === "All" ||
        (
          status === NOT_APPLIED_FILTER
            ? !app.applied && app.status !== "Archived" && app.status !== "Rejected"
            : app.status === status
        );
      return matchesText && matchesStatus && app.fitScore >= minFit;
    });
  }, [query, status, minFit]);

  const filteredStats = useMemo(() => summarize(filtered), [filtered]);
  const recruiterApps = useMemo(
    () =>
      filtered
        .filter((app) => app.reachOut || app.recruiterContact || app.recruiterProfile)
        .sort((a, b) => outreachPriority(b, "recruiter") - outreachPriority(a, "recruiter")),
    [filtered],
  );
  const engineerApps = useMemo(
    () =>
      filtered
        .filter((app) => app.reachOut || app.engineerContact || app.engineerProfile)
        .sort((a, b) => outreachPriority(b, "engineer") - outreachPriority(a, "engineer")),
    [filtered],
  );
  const recruiterBatch = useMemo(
    () =>
      (data.recruiterBatch || [])
        .filter((row) => row.outcome.toLowerCase() !== "sent")
        .sort((a, b) => batchPriority(b) - batchPriority(a)),
    [],
  );
  const engineerBatch = useMemo(
    () =>
      (data.engineerBatch || [])
        .filter((row) => row.outcome.toLowerCase() !== "sent")
        .sort((a, b) => engineerBatchPriority(b) - engineerBatchPriority(a)),
    [],
  );
  const reachedOutRoleGroups = useMemo(
    () => ({
      recruiter: data.outreachBuckets?.recruiter.sentRoles || buildReachedOutRoleGroups(data.recruiterBatch || [], "recruiter"),
      engineer: data.outreachBuckets?.engineer.sentRoles || buildReachedOutRoleGroups(data.engineerBatch || [], "engineer"),
    }),
    [],
  );
  const activeRoleGroups = useMemo(
    () => ({
      recruiter: data.outreachBuckets?.recruiter.activeRoles || buildActiveRoleGroups(recruiterBatch, "recruiter", ignoredBatchContacts),
      engineer: data.outreachBuckets?.engineer.activeRoles || buildActiveRoleGroups(engineerBatch, "engineer", ignoredBatchContacts),
    }),
    [recruiterBatch, engineerBatch, ignoredBatchContacts],
  );
  const visibleRecruiterWork = filterIgnoredRoleBuckets(activeRoleGroups.recruiter, ignoredBatchContacts, "recruiter");
  const visibleEngineerWork = filterIgnoredRoleBuckets(activeRoleGroups.engineer, ignoredBatchContacts, "engineer");
  const jobIntake = useMemo(
    () =>
      (data.jobIntake || [])
        .slice()
        .sort((a, b) => b.fitScore - a.fitScore || b.discoveredAt.localeCompare(a.discoveredAt) || a.company.localeCompare(b.company)),
    [],
  );
  const queuedIntake = jobIntake.filter((job) => ["Queued", "New"].includes(job.status)).slice(0, 24);

  const radarData = useMemo(
    () => [
      { axis: "Applied", value: data.stats.kpis.applyRate },
      { axis: "High Fit", value: (data.stats.kpis.highFit / Math.max(data.stats.kpis.total, 1)) * 100 },
      { axis: "Reach Out", value: (data.stats.kpis.reachOut / Math.max(data.stats.kpis.total, 1)) * 100 },
      { axis: "Recruiters", value: (data.stats.kpis.recruiterRows / Math.max(data.stats.kpis.total, 1)) * 100 },
      { axis: "Active", value: (data.stats.kpis.active / Math.max(data.stats.kpis.total, 1)) * 100 },
    ],
    [],
  );
  const dailyApplicationPulse = useMemo(() => buildDailyApplicationPulse(data.stats.timeline, data.applications), []);
  const stageSnake = useMemo(() => buildStageSnake(filtered), [filtered]);
  const successDonut = useMemo(
    () => [
      { name: "Submitted", value: pipelineMetrics.submitSuccessRate.submitted },
      { name: "Manual", value: pipelineMetrics.submitSuccessRate.manual },
      { name: "Archived", value: pipelineMetrics.submitSuccessRate.archived },
    ],
    [],
  );
  const showDataControls = activeTab !== "pipeline";
  const filterBar = (
    <section className="filters">
      <div className="searchbox">
        <Search size={18} />
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search companies, roles, recruiters, notes..." />
        {query && <button onClick={() => setQuery("")} aria-label="Clear search"><X size={16} /></button>}
      </div>
      <label>
        <Filter size={16} />
        <select value={status} onChange={(event) => setStatus(event.target.value)}>
          {statuses.map((item) => <option key={item}>{item}</option>)}
        </select>
      </label>
      <label className="range">
        Fit {minFit}+
        <input type="range" min="0" max="10" value={minFit} onChange={(event) => setMinFit(Number(event.target.value))} />
      </label>
    </section>
  );
  const metricStrip = (
    <section className="metric-strip">
      <MiniMetric label="Visible roles" value={filtered.length} />
      <MiniMetric label="Visible applied" value={filteredStats.applied} />
      <MiniMetric label="Avg fit" value={filteredStats.avgFit.toFixed(1)} />
      <MiniMetric label="Recruiter work" value={visibleRecruiterWork.length} />
      <MiniMetric label="Engineer work" value={visibleEngineerWork.length} />
    </section>
  );

  return (
    <main>
      <nav className="sticky-nav" aria-label="Dashboard sections">
        <button className="brand-chip" type="button" onClick={() => selectTab("overview")}><Sparkles size={16} /> Tracker</button>
        <div role="tablist" aria-label="Dashboard tabs">
          {NAV_ITEMS.map((item) => (
            <button
              aria-selected={activeTab === item.id}
              className={activeTab === item.id ? "active" : ""}
              key={item.id}
              onClick={() => selectTab(item.id)}
              role="tab"
              type="button"
            >
              {item.label}
            </button>
          ))}
        </div>
        <label className="mobile-jump">
          <span>Jump to</span>
          <select
            value={activeTab}
            onChange={(event) => {
              selectTab(event.target.value as TabId);
            }}
          >
            {NAV_ITEMS.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
          </select>
        </label>
        <span>{filtered.length} visible</span>
      </nav>

      {showDataControls && activeTab !== "overview" && filterBar}
      {showDataControls && activeTab !== "overview" && metricStrip}

      {activeTab === "overview" && (
        <div className="tab-panel">
          <section id="overview" className="topbar section-anchor">
            <div>
              <p className="eyebrow"><Sparkles size={16} /> Application intelligence</p>
              <h1>Tracker Command Center</h1>
            </div>
            <div className="sync-pill">
              <Activity size={16} />
              <span>Data refreshed {new Date(data.generatedAt).toLocaleString()}</span>
            </div>
          </section>

          <section className="hero-grid">
            <div className="mission-control">
              <div className="mission-copy">
                <p className="eyebrow"><Radar size={16} /> Live campaign map</p>
                <h2>{data.stats.kpis.total} roles, {data.stats.kpis.active} still alive, {data.stats.kpis.highFit} high-fit shots.</h2>
                <p>
                  A visual layer over applications, recruiter paths, fit scores, sources, timing, and outreach gaps.
                </p>
              </div>
              <div className="constellation-preview" aria-hidden="true">
                <Constellation apps={filtered.slice(0, 70)} />
              </div>
            </div>
            <div className="kpi-grid">
              <Kpi icon={<BriefcaseBusiness />} label="Applied" value={data.stats.kpis.applied} sub={percent(data.stats.kpis.applyRate)} />
              <Kpi icon={<Target />} label="Interview/OA" value={data.stats.kpis.interviewing + data.stats.kpis.assessments} sub="warm leads" />
              <Kpi icon={<Send />} label="Recruiter work" value={data.stats.kpis.recruiterWork || visibleRecruiterWork.length} sub="not reached out" />
              <Kpi icon={<MailCheck />} label="Engineer work" value={data.stats.kpis.engineerWork || visibleEngineerWork.length} sub="not reached out" />
              <Kpi icon={<Radar />} label="Fresh jobs" value={data.stats.kpis.intakeQueued || queuedIntake.length} sub="queued intake" />
            </div>
          </section>

          {filterBar}
          {metricStrip}
        </div>
      )}

      {activeTab === "actions" && (
        <section id="actions" className="dashboard-grid tab-panel section-anchor">
          <Panel title="Action Matrix" icon={<Target />} info={INFO_COPY.actions} wide>
            <ActionMatrix apps={filtered} />
          </Panel>
        </section>
      )}

      {activeTab === "trends" && (
        <section id="trends" className="dashboard-grid tab-panel section-anchor">
          <Panel title="Daily Application Pulse" icon={<CalendarDays />} info={INFO_COPY.dailyApplications} wide>
            <div className="daily-pulse">
              <ResponsiveContainer width="100%" height={330}>
                <ComposedChart data={dailyApplicationPulse.points}>
                  <CartesianGrid stroke="rgba(255,255,255,.08)" vertical={false} />
                  <XAxis dataKey="date" tickFormatter={readableDate} tick={{ fill: "#94a3b8", fontSize: 12 }} />
                  <YAxis tick={{ fill: "#94a3b8", fontSize: 12 }} />
                  <Tooltip content={<ChartTooltip />} />
                  <Bar dataKey="applications" name="Applications" fill="#55d6be" radius={[8, 8, 0, 0]} />
                  <Line type="monotone" dataKey="pace" name="3-day pace" stroke="#f7b267" strokeWidth={3} dot={{ r: 4 }} />
                </ComposedChart>
              </ResponsiveContainer>
              <div className="pulse-metrics" aria-label="Daily application summary">
                <MiniMetric label="Submitted" value={dailyApplicationPulse.total} />
                <MiniMetric label="Peak day" value={`${dailyApplicationPulse.peakCount} on ${readableDate(dailyApplicationPulse.peakDate)}`} />
                <MiniMetric label="Avg active day" value={dailyApplicationPulse.average.toFixed(1)} />
                <MiniMetric label="Latest day" value={`${dailyApplicationPulse.latestCount} on ${readableDate(dailyApplicationPulse.latestDate)}`} />
              </div>
              <div className="reachout-pulse">
                <div className="reachout-heading">
                  <span>Reach-out rhythm</span>
                  <strong>{dailyApplicationPulse.trackedRecruiterTotal} recruiter / {dailyApplicationPulse.trackedEngineerTotal} engineer</strong>
                </div>
                <ResponsiveContainer width="100%" height={210}>
                  <ComposedChart data={dailyApplicationPulse.points}>
                    <CartesianGrid stroke="rgba(255,255,255,.08)" vertical={false} />
                    <XAxis dataKey="date" tickFormatter={readableDate} tick={{ fill: "#94a3b8", fontSize: 12 }} />
                    <YAxis tick={{ fill: "#94a3b8", fontSize: 12 }} />
                    <Tooltip content={<ChartTooltip />} />
                    <Bar dataKey="recruiterReachOuts" name="Recruiter reach-outs" fill="#70a1ff" radius={[8, 8, 0, 0]} />
                    <Bar dataKey="engineerReachOuts" name="Engineer reach-outs" fill="#b388ff" radius={[8, 8, 0, 0]} />
                    <Bar dataKey="otherReachOuts" name="Unclassified reach-outs" fill="#8dd7cf" radius={[8, 8, 0, 0]} />
                    <Line type="monotone" dataKey="totalReachOuts" name="Total reach-outs" stroke="#f4d35e" strokeWidth={2} dot={{ r: 3 }} />
                  </ComposedChart>
                </ResponsiveContainer>
                <div className="pulse-metrics" aria-label="Daily outreach summary">
                  <MiniMetric label="Tracked lanes" value={dailyApplicationPulse.trackedReachOutTotal} />
                  <MiniMetric label="Logged sends" value={dailyApplicationPulse.reachOutTotal} />
                  <MiniMetric label="Peak send day" value={`${dailyApplicationPulse.reachOutPeakCount} on ${readableDate(dailyApplicationPulse.reachOutPeakDate)}`} />
                  <MiniMetric label="Avg send day" value={dailyApplicationPulse.reachOutAverage.toFixed(1)} />
                </div>
              </div>
            </div>
          </Panel>

          <Panel title="Application Stage Snake" icon={<Route />} info={INFO_COPY.stageSnake} wide>
            <ApplicationStageSnake stages={stageSnake.stages} total={stageSnake.total} />
          </Panel>

          <Panel title="Application Velocity" icon={<Activity />} info={INFO_COPY.velocity}>
            <ResponsiveContainer width="100%" height={290}>
              <AreaChart data={data.stats.timeline}>
                <defs>
                  <linearGradient id="areaGlow" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="5%" stopColor="#55d6be" stopOpacity={0.85} />
                    <stop offset="95%" stopColor="#55d6be" stopOpacity={0.05} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="rgba(255,255,255,.08)" vertical={false} />
                <XAxis dataKey="date" tickFormatter={readableDate} tick={{ fill: "#94a3b8", fontSize: 12 }} />
                <YAxis tick={{ fill: "#94a3b8", fontSize: 12 }} />
                <Tooltip content={<ChartTooltip />} />
                <Area type="monotone" dataKey="cumulative" stroke="#55d6be" fill="url(#areaGlow)" strokeWidth={3} />
                <Line type="monotone" dataKey="applied" stroke="#f7b267" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </Panel>

          <Panel title="Status Gravity" icon={<Network />} info={INFO_COPY.status}>
            <ResponsiveContainer width="100%" height={290}>
              <PieChart>
                <Pie data={data.stats.statusCounts} dataKey="value" nameKey="name" innerRadius={60} outerRadius={108} paddingAngle={3}>
                  {data.stats.statusCounts.map((_, index) => <Cell key={index} fill={COLORS[index % COLORS.length]} />)}
                </Pie>
                <Tooltip content={<ChartTooltip />} />
              </PieChart>
            </ResponsiveContainer>
            <LegendDots items={data.stats.statusCounts.slice(0, 6)} />
          </Panel>

          <Panel title="Fit Score Heat" icon={<Target />} info={INFO_COPY.fit}>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={data.stats.fitCounts}>
                <CartesianGrid stroke="rgba(255,255,255,.08)" vertical={false} />
                <XAxis dataKey="score" tick={{ fill: "#94a3b8" }} />
                <YAxis tick={{ fill: "#94a3b8" }} />
                <Tooltip content={<ChartTooltip />} />
                <Bar dataKey="count" radius={[8, 8, 0, 0]}>
                  {data.stats.fitCounts.map((_, index) => <Cell key={index} fill={COLORS[index % COLORS.length]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Panel>

          <Panel title="Sources x Outcomes" icon={<LinkIcon />} info={INFO_COPY.source} wide>
            <ResponsiveContainer width="100%" height={320}>
              <ComposedChart data={data.stats.sourceCounts.slice(0, 10)}>
                <CartesianGrid stroke="rgba(255,255,255,.08)" vertical={false} />
                <XAxis dataKey="name" tick={{ fill: "#94a3b8", fontSize: 12 }} />
                <YAxis tick={{ fill: "#94a3b8", fontSize: 12 }} />
                <Tooltip content={<ChartTooltip />} />
                <Bar dataKey="value" fill="#70a1ff" radius={[8, 8, 0, 0]} />
                <Line type="monotone" dataKey="value" stroke="#f4d35e" strokeWidth={3} dot={{ r: 4 }} />
              </ComposedChart>
            </ResponsiveContainer>
          </Panel>

          <Panel title="Role Field" icon={<BriefcaseBusiness />} info={INFO_COPY.role}>
            <ResponsiveContainer width="100%" height={320}>
              <ScatterChart>
                <CartesianGrid stroke="rgba(255,255,255,.08)" />
                <XAxis type="number" dataKey="fitScore" name="Fit" domain={[0, 10]} tick={{ fill: "#94a3b8" }} />
                <YAxis type="category" dataKey="status" name="Status" tick={{ fill: "#94a3b8", fontSize: 11 }} width={110} />
                <Tooltip cursor={{ strokeDasharray: "3 3" }} content={<AppTooltip />} />
                <Scatter data={filtered.slice(0, 120)} fill="#55d6be" />
              </ScatterChart>
            </ResponsiveContainer>
          </Panel>

          <Panel title="Campaign Radar" icon={<Radar />} info={INFO_COPY.radar}>
            <ResponsiveContainer width="100%" height={280}>
              <RadarChart data={radarData}>
                <PolarGrid stroke="rgba(255,255,255,.14)" />
                <PolarAngleAxis dataKey="axis" tick={{ fill: "#dbeafe", fontSize: 12 }} />
                <PolarRadiusAxis angle={90} domain={[0, 100]} tick={false} axisLine={false} />
                <RadarShape dataKey="value" stroke="#f7b267" fill="#f7b267" fillOpacity={0.35} strokeWidth={3} />
                <Tooltip content={<ChartTooltip />} />
              </RadarChart>
            </ResponsiveContainer>
          </Panel>
        </section>
      )}

      {activeTab === "intake" && (
        <section id="intake" className="dashboard-grid tab-panel section-anchor">
          <Panel title="Job Intake" icon={<Radar />} info={INFO_COPY.intake} wide>
            <div className="intake-summary">
              <MiniMetric label="Discovered" value={data.stats.kpis.intakeJobs || jobIntake.length} />
              <MiniMetric label="Queued" value={data.stats.kpis.intakeQueued || 0} />
              <MiniMetric label="New" value={data.stats.kpis.intakeNew || 0} />
              <MiniMetric label="Manual" value={data.stats.kpis.intakeManual || 0} />
            </div>
            <div className="role-table-wrap intake-table-wrap">
              <table className="role-table intake-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Role</th>
                    <th>Source</th>
                    <th>Status</th>
                    <th>Fit</th>
                    <th>Open</th>
                  </tr>
                </thead>
                <tbody>
                  {queuedIntake.map((job, index) => (
                    <IntakeRow job={job} index={index + 1} key={`${job.source}-${job.postingKey}-${job.jobUrl}`} />
                  ))}
                  {!queuedIntake.length && (
                    <tr>
                      <td colSpan={6}>No fresh queued intake jobs yet.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </Panel>
        </section>
      )}

      {activeTab === "outreach" && (
        <section id="outreach" className="split tab-panel section-anchor">
        <Panel title="Outreach Flight Deck" icon={<Users />} info={INFO_COPY.recruiters} wide>
          <section className="batch-section" aria-label="Need to reach out batches">
            <div className="batch-section-heading">
              <div>
                <span>Need to reach out</span>
                <h4>Batch Review</h4>
              </div>
              <p>Fact-check labeled LinkedIn contacts before approval. Engineer is separate from recruiter.</p>
            </div>
            <div className="lane-role-grid">
              <ActiveLaneRolesTable lane="recruiter" groups={visibleRecruiterWork} onOpenLane={setOpenBatchLane} />
              <ActiveLaneRolesTable lane="engineer" groups={visibleEngineerWork} onOpenLane={setOpenBatchLane} />
            </div>
          </section>
          <div className="lane-role-grid reached-out-grid">
            <ReachedOutRolesTable
              lane="recruiter"
              groups={reachedOutRoleGroups.recruiter}
              onOpenLane={setOpenReachedOutLane}
              onOpenRole={(group) => setSelectedReachedOutRole({ lane: "recruiter", group })}
            />
            <ReachedOutRolesTable
              lane="engineer"
              groups={reachedOutRoleGroups.engineer}
              onOpenLane={setOpenReachedOutLane}
              onOpenRole={(group) => setSelectedReachedOutRole({ lane: "engineer", group })}
            />
          </div>
        </Panel>
        <Panel title="Outreach Gaps" icon={<MailCheck />} info={INFO_COPY.gaps}>
          <div className="gap-list">
            {data.stats.outreachGaps.slice(0, 14).map((gap) => (
              <a className="gap-row" key={`${gap.company}-${gap.role}-${gap.jobLink}`} href={gap.jobLink || undefined} target="_blank" rel="noreferrer">
                <span>
                  <strong>{gap.company}</strong>
                  <small>{gap.role}</small>
                </span>
                <b>{gap.fitScore}</b>
                <em>{gap.prospectCount}/3</em>
              </a>
            ))}
          </div>
        </Panel>
        </section>
      )}

      {openOutreachLane && (
        <OutreachModal
          lane={openOutreachLane}
          apps={openOutreachLane === "recruiter" ? recruiterApps : engineerApps}
          onClose={() => setOpenOutreachLane(null)}
          onInspect={(app) => setSelectedOutreach({ app, lane: openOutreachLane })}
        />
      )}

      {openBatchLane === "engineer" && (
        <ActiveRoleQueueModal
          lane="engineer"
          groups={visibleEngineerWork}
          onClose={() => setOpenBatchLane(null)}
        />
      )}

      {openBatchLane === "recruiter" && (
        <ActiveRoleQueueModal
          lane="recruiter"
          groups={visibleRecruiterWork}
          onClose={() => setOpenBatchLane(null)}
        />
      )}

      {openReachedOutLane && (
        <ReachedOutLaneModal
          lane={openReachedOutLane}
          groups={openReachedOutLane === "recruiter" ? reachedOutRoleGroups.recruiter : reachedOutRoleGroups.engineer}
          onClose={() => setOpenReachedOutLane(null)}
        />
      )}

      {selectedReachedOutRole && (
        <ReachedOutRoleModal
          lane={selectedReachedOutRole.lane}
          group={selectedReachedOutRole.group}
          onClose={() => setSelectedReachedOutRole(null)}
        />
      )}

      {selectedOutreach && (
        <OutreachDetailModal
          app={selectedOutreach.app}
          lane={selectedOutreach.lane}
          prospects={data.prospects}
          onClose={() => setSelectedOutreach(null)}
        />
      )}

      {activeTab === "browser" && (
        <section id="browser" className="table-section tab-panel section-anchor">
        <div className="section-heading">
          <h2>Application Browser</h2>
          <p>{filtered.length} visible rows</p>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Company</th>
                <th>Role</th>
                <th>Resume</th>
                <th>Status</th>
                <th>Fit</th>
                <th>Recruiter</th>
                <th>Engineer</th>
                <th>Links</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((app) => (
                <tr key={`${app.company}-${app.role}-${app.postingKey}`}>
                  <td><strong>{app.company}</strong><small>{app.source}</small></td>
                  <td>{app.role}<small>{app.location}</small></td>
                  <td>
                    <ResumeReference
                      app={app}
                      copiedPath={copiedResumePath}
                      onCopy={(path) => {
                        void navigator.clipboard.writeText(path);
                        setCopiedResumePath(path);
                        window.setTimeout(() => setCopiedResumePath(""), 1600);
                      }}
                    />
                  </td>
                  <td><StatusBadge app={app} /></td>
                  <td><b>{app.fitScore || "-"}</b></td>
                  <td>{app.recruiterContact || "Open"}<small>{app.recruiterProfile && hostFromUrl(app.recruiterProfile)}</small></td>
                  <td>{app.engineerContact || "Open"}<small>{app.engineerProfile && hostFromUrl(app.engineerProfile)}</small></td>
                  <td>
                    <div className="link-pack">
                      {app.jobLink && <a href={app.jobLink} target="_blank" rel="noreferrer" aria-label="Job"><ExternalLink size={16} /></a>}
                      {app.recruiterProfile && <a href={app.recruiterProfile} target="_blank" rel="noreferrer" aria-label="Recruiter"><Users size={16} /></a>}
                      {app.engineerProfile && <a href={app.engineerProfile} target="_blank" rel="noreferrer" aria-label="Engineer"><Users size={16} /></a>}
                      {app.resumePdf && <a href={repoLink(app.resumePdf)} target="_blank" rel="noreferrer" aria-label="Resume"><BriefcaseBusiness size={16} /></a>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mobile-browser-list">
          {filtered.map((app) => (
            <article className="mobile-app-card" key={`mobile-${app.company}-${app.role}-${app.postingKey}`}>
              <header>
                <div>
                  <h3>{app.company}</h3>
                  <p>{app.role}</p>
                </div>
                <b>{app.fitScore || "-"}</b>
              </header>
              <div className="mobile-app-meta">
                <StatusBadge app={app} />
                <small>{app.location || app.source}</small>
              </div>
              <div className="mobile-contact-grid">
                <span><b>Recruiter</b>{app.recruiterContact || "Open"}</span>
                <span><b>Engineer</b>{app.engineerContact || "Open"}</span>
              </div>
              <ResumeReference
                app={app}
                copiedPath={copiedResumePath}
                onCopy={(path) => {
                  void navigator.clipboard.writeText(path);
                  setCopiedResumePath(path);
                  window.setTimeout(() => setCopiedResumePath(""), 1600);
                }}
              />
              <div className="link-pack">
                {app.jobLink && <a href={app.jobLink} target="_blank" rel="noreferrer" aria-label="Job"><ExternalLink size={16} /></a>}
                {app.recruiterProfile && <a href={app.recruiterProfile} target="_blank" rel="noreferrer" aria-label="Recruiter"><Users size={16} /></a>}
                {app.engineerProfile && <a href={app.engineerProfile} target="_blank" rel="noreferrer" aria-label="Engineer"><Users size={16} /></a>}
              </div>
            </article>
          ))}
        </div>
        </section>
      )}

      {activeTab === "pipeline" && (
        <section id="pipeline" className="pipeline-section tab-panel section-anchor">
        <div className="section-heading">
          <div>
            <p className="eyebrow"><TerminalSquare size={16} /> Codex skills</p>
            <h2>Codex Skill Runbook</h2>
          </div>
          <InfoBubble text={INFO_COPY.pipeline} />
        </div>

        <div className="pipeline-hero">
          <div>
            <h3>Pipeline health for the last {pipelineMetrics.windowDays} days.</h3>
            <p>
              Outcomes come from the append-only log, queue depth comes from the read-only SQLite mirror, and intake freshness comes from the capture cache.
            </p>
          </div>
          <div className="pipeline-flow" aria-label="Recommended recruiting flow">
            <span>Ready {pipelineMetrics.queueDepth.readyToApply}</span>
            <span>Tailored {pipelineMetrics.queueDepth.resumeTailored}</span>
            <span>Manual {pipelineMetrics.queueDepth.manualApplyNeeded}</span>
            <span>Intake {pipelineMetrics.queueDepth.intakeUnprocessed}</span>
          </div>
        </div>

        <div className="pipeline-metrics-grid">
          <article className="chart-card wide">
            <div className="card-heading">
              <h3>Applications Per Day</h3>
              <span>{readableDate(pipelineMetrics.generatedAt)}</span>
            </div>
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart data={pipelineMetrics.applicationsPerDay}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,.12)" />
                <XAxis dataKey="date" tickFormatter={readableDate} />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="manual" stackId="a" fill="#f7b267" />
                <Bar dataKey="archived" stackId="a" fill="#f25f5c" />
                <Line type="monotone" dataKey="submitted" stroke="#55d6be" strokeWidth={3} />
              </ComposedChart>
            </ResponsiveContainer>
          </article>

          <article className="chart-card">
            <div className="card-heading">
              <h3>Outcome Mix</h3>
              <span>{Math.round(pipelineMetrics.submitSuccessRate.submitted * 100)}% submitted</span>
            </div>
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie data={successDonut} dataKey="value" nameKey="name" innerRadius={58} outerRadius={92} paddingAngle={4}>
                  {successDonut.map((entry, index) => <Cell key={entry.name} fill={COLORS[index]} />)}
                </Pie>
                <Tooltip formatter={(value: number) => `${Math.round(value * 100)}%`} />
              </PieChart>
            </ResponsiveContainer>
          </article>

          <article className="chart-card">
            <div className="card-heading">
              <h3>Confidence By Source</h3>
              <span>{pipelineMetrics.avgConfidenceBySource.length} sources</span>
            </div>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={pipelineMetrics.avgConfidenceBySource}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,.12)" />
                <XAxis dataKey="source" />
                <YAxis domain={[0, 100]} />
                <Tooltip />
                <Bar dataKey="avgScore" fill="#70a1ff" />
              </BarChart>
            </ResponsiveContainer>
          </article>

          <article className="chart-card">
            <div className="card-heading">
              <h3>Top Blockers</h3>
              <span>{pipelineMetrics.topBlockers.length || 0} tracked</span>
            </div>
            <div className="blocker-table">
              {(pipelineMetrics.topBlockers.length ? pipelineMetrics.topBlockers : [{ reason: "No manual blockers logged", count: 0 }]).map((blocker) => (
                <div key={blocker.reason}>
                  <span>{blocker.reason}</span>
                  <b>{blocker.count}</b>
                </div>
              ))}
            </div>
          </article>

          <article className="chart-card">
            <div className="card-heading">
              <h3>Intake Health</h3>
              <span>{Math.round(pipelineMetrics.intakeHealth.linkedinCacheHitRate * 100)}% cache hit</span>
            </div>
            <div className="health-list">
              <HealthRow label="LinkedIn" timestamp={pipelineMetrics.intakeHealth.linkedinLastRun} count={pipelineMetrics.intakeHealth.linkedinCapturedToday} />
              <HealthRow label="Greenhouse" timestamp={pipelineMetrics.intakeHealth.greenhouseLastRun} count={pipelineMetrics.intakeHealth.greenhouseCapturedToday} />
            </div>
          </article>
        </div>

        <div className="command-flow">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow"><Activity size={16} /> Ask Codex to run these</p>
              <h2>Run Order</h2>
            </div>
          </div>
          <div className="command-steps">
            {OPTIMAL_COMMAND_FLOW.map((item) => (
              <article className="command-step" key={item.step}>
                <span>{item.step}</span>
                <div>
                  <h3>{item.name}</h3>
                  <p>{item.note}</p>
                  <code>{item.command}</code>
                </div>
              </article>
            ))}
          </div>
        </div>

        <div className="parallel-flow">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow"><Users size={16} /> Parallel Codex workstreams</p>
              <h2>Fast LinkedIn Pass</h2>
            </div>
          </div>
          <div className="parallel-grid">
            {PARALLEL_WORKSTREAMS.map((item) => (
              <article className="parallel-card" key={item.name}>
                <h3>{item.name}</h3>
                <p>{item.text}</p>
                <code>{item.command}</code>
              </article>
            ))}
          </div>
        </div>

        <div className="mode-grid">
          {PIPELINE_MODES.map((mode) => (
            <article className="mode-card" key={mode.name}>
              <h3>{mode.name}</h3>
              <p>{mode.description}</p>
              <code>{mode.command}</code>
            </article>
          ))}
        </div>

        <div className="skill-grid">
          {SKILL_CARDS.map((skill) => (
            <article className="skill-card" key={skill.name}>
              <span>{skill.role}</span>
              <h3>{skill.name}</h3>
              <p>{skill.text}</p>
            </article>
          ))}
        </div>
        </section>
      )}
    </main>
  );
}

function Kpi({ icon, label, value, sub }: { icon: ReactNode; label: string; value: number; sub: string }) {
  return (
    <div className="kpi-card">
      <span>{icon}</span>
      <b>{value}</b>
      <p>{label}</p>
      <small>{sub}</small>
    </div>
  );
}

function HealthRow({ label, timestamp, count }: { label: string; timestamp: string; count: number }) {
  const ageHours = timestamp ? (Date.now() - new Date(timestamp).getTime()) / 36e5 : Infinity;
  const tone = ageHours <= 2 ? "good" : ageHours <= 8 ? "warn" : "bad";
  return (
    <div className="health-row">
      <span className={`health-dot ${tone}`} />
      <strong>{label}</strong>
      <span>{timestamp ? readableDate(timestamp) : "No run"}</span>
      <b>{count} today</b>
    </div>
  );
}

function MiniMetric({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <span>{label}</span>
      <b>{value}</b>
    </div>
  );
}

function ResumeReference({
  app,
  copiedPath,
  onCopy,
}: {
  app: Application;
  copiedPath: string;
  onCopy: (path: string) => void;
}) {
  if (!app.resumePdf && !app.resumeFolder) {
    return <span className="resume-ref missing">No tailored resume</span>;
  }
  const primaryPath = app.resumePdf || app.resumeFolder;
  return (
    <div className="resume-ref">
      {app.resumePdf ? (
        <button type="button" onClick={() => onCopy(app.resumePdf)}>
          <BriefcaseBusiness size={15} />
          {copiedPath === app.resumePdf ? "Copied" : "Copy PDF path"}
        </button>
      ) : (
        <span>No PDF</span>
      )}
      <small>
        {app.resumeFolder && <button type="button" onClick={() => onCopy(app.resumeFolder)}>Copy folder</button>}
        {app.resumePdf && <a href={repoLink(app.resumePdf)} target="_blank" rel="noreferrer">GitHub PDF</a>}
        {primaryPath && resumeName(primaryPath)}
      </small>
    </div>
  );
}

function OutreachLane({
  lane,
  title,
  description,
  apps,
  onOpen,
  onInspect,
}: {
  lane: "recruiter" | "engineer";
  title: string;
  description: string;
  apps: Application[];
  onOpen: () => void;
  onInspect: (app: Application) => void;
}) {
  const done = laneDoneCount(apps, lane);
  const open = apps.length - done;
  return (
    <section className={`outreach-lane ${lane}`}>
      <header>
        <div>
          <span>{lane === "recruiter" ? "Recruiter lane" : "Engineer lane"}</span>
          <h4>{title}</h4>
          <p>{description}</p>
        </div>
        <button onClick={onOpen} type="button">View all</button>
      </header>
      <div className="lane-counts">
        <b>{done}<small>done</small></b>
        <b>{open}<small>open</small></b>
      </div>
      <div className="recruiter-list compact">
        {apps.slice(0, 7).map((app) => (
          <OutreachRow key={`${lane}-${app.company}-${app.role}-${app.postingKey}`} app={app} lane={lane} onInspect={onInspect} />
        ))}
      </div>
    </section>
  );
}

function ActiveLaneRolesTable({
  lane,
  groups,
  onOpenLane,
}: {
  lane: "recruiter" | "engineer";
  groups: OutreachRoleBucket[];
  onOpenLane: (lane: "recruiter" | "engineer") => void;
}) {
  const visibleGroups = sortActiveRoleBuckets(groups).slice(0, OUTREACH_TABLE_PREVIEW_LIMIT);
  const labels = lane === "recruiter"
    ? { eyebrow: "Recruiters", title: "Recruiter work", person: "Recruiter" }
    : { eyebrow: "Engineers", title: "Engineer work", person: "Engineer" };
  return (
    <section className={`lane-role-card ${lane}`}>
      <header>
        <div>
          <span>{labels.eyebrow}</span>
          <h4>{labels.title}</h4>
          <p>Needs label, labeled but not approved, or approved but not sent.</p>
        </div>
        <button type="button" onClick={() => onOpenLane(lane)}>View all</button>
      </header>
      <div className="role-table-wrap">
        <table className="role-table active-role-table">
          <colgroup>
            <col className="role-index-col" />
            <col className="role-title-col" />
            <col className="role-person-col" />
            <col className="role-state-col" />
            <col className="role-fit-col" />
          </colgroup>
          <thead>
            <tr>
              <th>#</th>
              <th>Role</th>
              <th>{labels.person}</th>
              <th>State</th>
              <th>Fit</th>
            </tr>
          </thead>
          <tbody>
            {visibleGroups.map((group, index) => (
              <tr key={group.key}>
                <td>{index + 1}</td>
                <td>
                  <strong>{group.company}</strong>
                  <small>{group.role}</small>
                </td>
                <td><ContactPillList contacts={group.contacts.map((contact) => contact.name)} empty="Needs label" /></td>
                <td><WorkStatePills states={group.states} /></td>
                <td><b>{group.fitScore || "-"}</b></td>
              </tr>
            ))}
            {!groups.length && (
              <tr>
                <td colSpan={5}>No active {lane} rows need review.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ReachedOutRolesTable({
  lane,
  groups,
  onOpenLane,
  onOpenRole,
}: {
  lane: "recruiter" | "engineer";
  groups: OutreachRoleBucket[];
  onOpenLane: (lane: "recruiter" | "engineer") => void;
  onOpenRole: (group: OutreachRoleBucket) => void;
}) {
  const visibleGroups = groups.slice(0, OUTREACH_TABLE_PREVIEW_LIMIT);
  const labels = lane === "recruiter"
    ? { eyebrow: "Recruiters sent", title: "Recruiter sent history", empty: "No recruiter sends are recorded yet." }
    : { eyebrow: "Engineers sent", title: "Engineer sent history", empty: "No engineer sends are recorded yet." };
  return (
    <section className={`reached-out-section lane-role-card ${lane}`}>
      <div className="batch-section-heading compact">
        <div>
          <span>{labels.eyebrow}</span>
          <h4>{labels.title}</h4>
        </div>
        <button type="button" onClick={() => onOpenLane(lane)}>View all</button>
      </div>
      <div className="role-table-wrap">
        <table className="role-table reached-out-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Role</th>
              <th>Sent</th>
              <th>Latest contact</th>
              <th>View</th>
            </tr>
          </thead>
          <tbody>
            {visibleGroups.map((group, index) => (
              <tr key={group.key}>
                <td>{index + 1}</td>
                <td>
                  <strong>{group.company}</strong>
                  <small>{group.role}</small>
                </td>
                <td><b>{group.contacts.length}</b></td>
                <td><ContactPillList contacts={group.contacts.map((contact) => contact.name)} empty="None" /></td>
                <td><button type="button" onClick={() => onOpenRole(group)}>View</button></td>
              </tr>
            ))}
            {!groups.length && (
              <tr>
                <td colSpan={5}>{labels.empty}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ContactPillList({ contacts, empty }: { contacts: string[]; empty: string }) {
  const visible = contacts.filter(Boolean);
  if (!visible.length) return <span className="empty-cell">{empty}</span>;
  return (
    <div className="contact-pills">
      {visible.slice(0, 3).map((contact) => <span key={contact}>{contact}</span>)}
      {visible.length > 3 && <em>+{visible.length - 3}</em>}
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

function IntakeRow({ job, index }: { job: JobIntake; index: number }) {
  return (
    <tr>
      <td>{index}</td>
      <td>
        <strong>{job.company}</strong>
        <small>{job.role}</small>
        <small>{job.location}</small>
      </td>
      <td>
        <span className="intake-source">{job.source}</span>
        <small>{job.postedAge || readableDate(job.discoveredAt)}</small>
      </td>
      <td>
        <span className={`intake-status ${normalizeKey(job.status)}`}>{job.status}</span>
        <small>{job.reason}</small>
      </td>
      <td><b>{job.fitScore || "-"}</b></td>
      <td>
        {job.jobUrl ? <a className="row-icon-link" href={job.jobUrl} target="_blank" rel="noreferrer" aria-label={`${job.company} posting`}><ArrowUpRight size={16} /></a> : <span />}
      </td>
    </tr>
  );
}

function RecruiterBatchBoard({ rows, ignoredContacts, onOpen }: { rows: RecruiterBatch[]; ignoredContacts: Set<string>; onOpen: () => void }) {
  const stats = data.stats.recruiterBatch || { total: 0, labeled: 0, approved: 0, sent: 0, notReachedOut: 0, needsRecruiter: 0 };
  const labeledRows = rows.filter((row) => row.recruiterName && row.recruiterProfile && row.outcome.toLowerCase() !== "sent" && !ignoredContacts.has(recruiterBatchIgnoreKey(row)));
  if (!rows.length && !stats.total) return null;
  return (
    <section className="recruiter-batch-board">
      <header>
        <div>
          <span>Recruiter batch</span>
          <h4>Labeled, Not Reached Out</h4>
          <p>Pre-run manifest for approved LinkedIn outreach. Sent rows are recorded separately in the tracker.</p>
        </div>
        <button className="batch-open" type="button" onClick={onOpen}>View all</button>
        <div className="batch-counts">
          <b>{labeledRows.length}<small>ready</small></b>
          <b>{stats.approved}<small>approved</small></b>
          <b>{stats.sent}<small>sent</small></b>
        </div>
      </header>
      <div className="batch-list">
        {labeledRows.slice(0, 5).map((row) => (
          <SharedOutreachRow row={outreachRowDataFromRecruiterBatch(row)} key={`batch-${row.postingKey}`} />
        ))}
        {!labeledRows.length && <p className="batch-empty">No labeled recruiter rows are ready to review yet.</p>}
      </div>
    </section>
  );
}

function EngineerBatchBoard({ rows, ignoredContacts, onOpen }: { rows: EngineerBatch[]; ignoredContacts: Set<string>; onOpen: () => void }) {
  const stats = data.stats.engineerBatch || { total: 0, labeled: 0, approved: 0, sent: 0, notReachedOut: 0, needsEngineer: 0 };
  const labeledRows = rows.filter((row) => row.engineerName && row.engineerProfile && row.outcome.toLowerCase() !== "sent" && !ignoredContacts.has(engineerBatchIgnoreKey(row)));
  if (!rows.length && !stats.total) return null;
  return (
    <section className="recruiter-batch-board engineer-batch-board">
      <header>
        <div>
          <span>Engineer batch</span>
          <h4>Labeled, Not Reached Out</h4>
          <p>Pre-run manifest for approved LinkedIn engineer and alumni outreach. Sent rows are recorded separately in the tracker.</p>
        </div>
        <button className="batch-open" type="button" onClick={onOpen}>View all</button>
        <div className="batch-counts">
          <b>{labeledRows.length}<small>ready</small></b>
          <b>{stats.approved}<small>approved</small></b>
          <b>{stats.sent}<small>sent</small></b>
        </div>
      </header>
      <div className="batch-list">
        {labeledRows.slice(0, 5).map((row) => (
          <SharedOutreachRow row={outreachRowDataFromEngineerBatch(row)} key={`engineer-batch-${row.postingKey}`} />
        ))}
        {!labeledRows.length && <p className="batch-empty">No labeled engineer rows are ready to review yet.</p>}
      </div>
    </section>
  );
}

function RecruiterBatchRow({
  row,
  detailed = false,
  displayIndex,
  onIgnore,
}: {
  row: RecruiterBatch;
  detailed?: boolean;
  displayIndex?: number;
  onIgnore?: (key: string) => void;
}) {
  const ignoreKey = recruiterBatchIgnoreKey(row);
  return (
    <article className={`batch-row ${detailed ? "detailed" : ""} ${displayIndex ? "indexed" : ""}`}>
      {displayIndex && <span className="batch-index">{displayIndex}</span>}
      <div>
        <strong>{row.company}</strong>
        <p>{row.role}</p>
        <small className="batch-contact">
          <span>{row.recruiterName || "Needs recruiter label"}</span>
          {row.recruiterPosition && <em>{row.recruiterPosition}</em>}
        </small>
        {detailed && <BatchDetails note={row.connectionNote} notes={row.notes} />}
      </div>
      <BatchState row={row} />
      <b>{row.fitScore || "-"}</b>
      {row.recruiterProfile ? <a href={row.recruiterProfile} target="_blank" rel="noreferrer" aria-label={`${row.recruiterName || row.company} LinkedIn`}><ArrowUpRight size={17} /></a> : <span />}
      {onIgnore && (
        <button className="batch-ignore" type="button" onClick={() => onIgnore(ignoreKey)} aria-label={`Ignore ${row.recruiterName || row.company} for ${row.company}`}>
          <X size={16} />
        </button>
      )}
    </article>
  );
}

function EngineerBatchRow({
  row,
  detailed = false,
  displayIndex,
  onIgnore,
}: {
  row: EngineerBatch;
  detailed?: boolean;
  displayIndex?: number;
  onIgnore?: (key: string) => void;
}) {
  const ignoreKey = engineerBatchIgnoreKey(row);
  return (
    <article className={`batch-row ${detailed ? "detailed" : ""} ${displayIndex ? "indexed" : ""}`}>
      {displayIndex && <span className="batch-index">{displayIndex}</span>}
      <div>
        <strong>{row.company}</strong>
        <p>{row.role}</p>
        <small className="batch-contact">
          <span>{row.engineerName || "Needs engineer label"}</span>
          {row.engineerPosition && <em>{row.engineerPosition}</em>}
        </small>
        {detailed && <BatchDetails note={row.connectionNote} notes={row.notes} />}
      </div>
      <EngineerBatchState row={row} />
      <b>{row.fitScore || "-"}</b>
      {row.engineerProfile ? <a href={row.engineerProfile} target="_blank" rel="noreferrer" aria-label={`${row.engineerName || row.company} LinkedIn`}><ArrowUpRight size={17} /></a> : <span />}
      {onIgnore && (
        <button className="batch-ignore" type="button" onClick={() => onIgnore(ignoreKey)} aria-label={`Ignore ${row.engineerName || row.company} for ${row.company}`}>
          <X size={16} />
        </button>
      )}
    </article>
  );
}

function BatchDetails({ note, notes }: { note: string; notes: string }) {
  return (
    <dl className="batch-details">
      <div>
        <dt>Connection note</dt>
        <dd>{note || "No note drafted yet"}</dd>
      </div>
      {notes && (
        <div>
          <dt>Research notes</dt>
          <dd>{notes}</dd>
        </div>
      )}
    </dl>
  );
}

function RecruiterBatchModal({
  rows,
  ignoredContacts,
  onClose,
  onIgnore,
}: {
  rows: RecruiterBatch[];
  ignoredContacts: Set<string>;
  onClose: () => void;
  onIgnore: (key: string) => void;
}) {
  const availableRows = rows
    .filter((row) => isActiveBatchWork(row))
    .filter((row) => !ignoredContacts.has(recruiterBatchIgnoreKey(row)))
    .map(outreachRowDataFromRecruiterBatch);
  return (
    <SharedOutreachModal
      lane="recruiter"
      rows={availableRows}
      onClose={onClose}
      onSkip={(row) => onIgnore(row.key)}
    />
  );
}

function ActiveRoleQueueModal({
  lane,
  groups,
  onClose,
}: {
  lane: "recruiter" | "engineer";
  groups: OutreachRoleBucket[];
  onClose: () => void;
}) {
  const [skippedKeys, setSkippedKeys] = useState<Set<string>>(() => new Set());
  const rows = sortActiveRoleBuckets(groups)
    .filter((group) => !skippedKeys.has(activeRoleSkipKey(lane, group)))
    .map((group) => outreachRowDataFromGroup(lane, group));
  return (
    <SharedOutreachModal
      lane={lane}
      rows={rows}
      onClose={onClose}
      onSkip={(row) => setSkippedKeys((current) => new Set(current).add(row.key))}
    />
  );
}

function ActiveRoleQueueRow({
  lane,
  group,
  displayIndex,
  onSkip,
}: {
  lane: "recruiter" | "engineer";
  group: OutreachRoleBucket;
  displayIndex: number;
  onSkip: () => void;
}) {
  return <SharedOutreachRow row={outreachRowDataFromGroup(lane, group)} displayIndex={displayIndex} onSkip={() => onSkip()} />;
}

function EngineerBatchModal({
  rows,
  ignoredContacts,
  onClose,
  onIgnore,
}: {
  rows: EngineerBatch[];
  ignoredContacts: Set<string>;
  onClose: () => void;
  onIgnore: (key: string) => void;
}) {
  const availableRows = rows
    .filter((row) => isActiveBatchWork(row))
    .filter((row) => !ignoredContacts.has(engineerBatchIgnoreKey(row)))
    .map(outreachRowDataFromEngineerBatch);
  return (
    <SharedOutreachModal
      lane="engineer"
      rows={availableRows}
      onClose={onClose}
      onSkip={(row) => onIgnore(row.key)}
    />
  );
}

function ReachedOutLaneModal({
  lane,
  groups,
  onClose,
}: {
  lane: "recruiter" | "engineer";
  groups: OutreachRoleBucket[];
  onClose: () => void;
}) {
  const title = lane === "recruiter" ? "Recruiter Sent History" : "Engineer Sent History";
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="outreach-modal batch-modal" role="dialog" aria-modal="true" aria-label={title} onMouseDown={(event) => event.stopPropagation()}>
        <header>
          <div>
            <p className="eyebrow">{lane === "recruiter" ? "Recruiters sent" : "Engineers sent"}</p>
            <h2>{title}</h2>
            <p>{groups.reduce((sum, group) => sum + group.contacts.length, 0)} contacts across {groups.length} roles.</p>
          </div>
          <button onClick={onClose} type="button" aria-label="Close"><X size={18} /></button>
        </header>
        <div className="modal-list sent-modal-list">
          {groups.map((group, index) => (
            <section className="sent-role-group" key={group.key}>
              <header>
                <span>{index + 1}</span>
                <div>
                  <strong>{group.company}</strong>
                  <p>{group.role}</p>
                </div>
                <b>{group.contacts.length}</b>
              </header>
              <ReachedOutContactGrid contacts={group.contacts} />
            </section>
          ))}
        </div>
      </section>
    </div>
  );
}

function ReachedOutRoleModal({
  lane,
  group,
  onClose,
}: {
  lane: "recruiter" | "engineer";
  group: OutreachRoleBucket;
  onClose: () => void;
}) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="outreach-modal batch-modal" role="dialog" aria-modal="true" aria-label={`${group.company} sent ${lane} contacts`} onMouseDown={(event) => event.stopPropagation()}>
        <header>
          <div>
            <p className="eyebrow">{lane === "recruiter" ? "Recruiters sent" : "Engineers sent"}</p>
            <h2>{group.company}</h2>
            <p>{group.role}</p>
          </div>
          <button onClick={onClose} type="button" aria-label="Close"><X size={18} /></button>
        </header>
        <div className="modal-list sent-modal-list">
          <ReachedOutContactGrid contacts={group.contacts} />
        </div>
      </section>
    </div>
  );
}

function ReachedOutContactGrid({ contacts }: { contacts: OutreachRoleBucket["contacts"] }) {
  return (
    <div className="reached-out-contact-grid">
      {contacts.map((contact) => (
        <article key={`${contact.lane}-${contact.name}-${contact.profile}`}>
          <span>{contact.lane}</span>
          <strong>{contact.name}</strong>
          <small>{contact.position || "No title recorded"}</small>
          {contact.profile && <a href={contact.profile} target="_blank" rel="noreferrer"><ArrowUpRight size={15} /> LinkedIn</a>}
        </article>
      ))}
    </div>
  );
}

function BatchModalControls({
  total,
  visible,
  startIndex,
  endIndex,
  onStartIndex,
  onEndIndex,
}: {
  total: number;
  visible: number;
  startIndex: number;
  endIndex: string;
  onStartIndex: (value: number) => void;
  onEndIndex: (value: string) => void;
}) {
  return (
    <div className="batch-modal-controls">
      <label>
        Start index
        <input inputMode="numeric" pattern="[0-9]*" value={startIndex} onChange={(event) => onStartIndex(Number(event.target.value.replace(/\D/g, "")) || 1)} />
      </label>
      <label>
        End index
        <input inputMode="numeric" pattern="[0-9]*" value={endIndex} onChange={(event) => onEndIndex(event.target.value.replace(/\D/g, ""))} placeholder={`${total}`} />
      </label>
      <span>{visible} shown of {total}</span>
    </div>
  );
}

function BatchState({ row }: { row: RecruiterBatch }) {
  const approval = row.approval.toLowerCase();
  const outcome = row.outcome.toLowerCase();
  let label = "Research";
  let tone = "research";
  if (outcome === "skipped" || outcome === "blocked") {
    label = row.outcome;
    tone = "blocked";
  } else if (approval === "approved") {
    label = "Approved";
    tone = "approved";
  } else if (row.recruiterName && row.recruiterProfile) {
    label = "Labeled";
    tone = "labeled";
  }
  return <span className={`batch-state ${tone}`}>{label}</span>;
}

function EngineerBatchState({ row }: { row: EngineerBatch }) {
  const approval = row.approval.toLowerCase();
  const outcome = row.outcome.toLowerCase();
  let label = "Research";
  let tone = "research";
  if (outcome === "skipped" || outcome === "blocked") {
    label = row.outcome;
    tone = "blocked";
  } else if (approval === "approved") {
    label = "Approved";
    tone = "approved";
  } else if (row.engineerName && row.engineerProfile) {
    label = "Labeled";
    tone = "labeled";
  }
  return <span className={`batch-state ${tone}`}>{label}</span>;
}

function OutreachModal({
  lane,
  apps,
  onClose,
  onInspect,
}: {
  lane: "recruiter" | "engineer";
  apps: Application[];
  onClose: () => void;
  onInspect: (app: Application) => void;
}) {
  const title = lane === "recruiter" ? "Recruiter Outreach" : "Engineer Outreach";
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="outreach-modal" role="dialog" aria-modal="true" aria-label={title} onMouseDown={(event) => event.stopPropagation()}>
        <header>
          <div>
            <p className="eyebrow">{lane === "recruiter" ? "Recruiter lane" : "Engineer lane"}</p>
            <h2>{title}</h2>
          </div>
          <button onClick={onClose} type="button" aria-label="Close"><X size={18} /></button>
        </header>
        <div className="modal-list">
          {apps.map((app) => (
            <OutreachRow key={`modal-${lane}-${app.company}-${app.role}-${app.postingKey}`} app={app} lane={lane} onInspect={onInspect} />
          ))}
        </div>
      </section>
    </div>
  );
}

function Panel({
  id,
  title,
  icon,
  info,
  children,
  wide = false,
}: {
  id?: string;
  title: string;
  icon: ReactNode;
  info?: string;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <article id={id} className={`panel section-anchor ${wide ? "wide" : ""}`}>
      <header>
        <h3>{icon}{title}</h3>
        {info && <InfoBubble text={info} />}
      </header>
      {children}
    </article>
  );
}

function InfoBubble({ text }: { text: string }) {
  return (
    <span className="info-bubble" tabIndex={0} aria-label={text}>
      <Info size={16} />
      <span>{text}</span>
    </span>
  );
}

function LegendDots({ items }: { items: Array<{ name: string; value: number }> }) {
  return (
    <div className="legend-dots">
      {items.map((item, index) => (
        <span key={item.name}><i style={{ background: COLORS[index % COLORS.length] }} />{item.name} <b>{item.value}</b></span>
      ))}
    </div>
  );
}

type StageSnakeNode = {
  id: string;
  label: string;
  count: number;
  active: number;
  rejected: number;
  rejectedExamples: Application[];
};

function ApplicationStageSnake({ stages, total }: { stages: StageSnakeNode[]; total: number }) {
  const maxCount = Math.max(...stages.map((stage) => stage.count), 1);
  const dropStages = stages.filter((stage) => stage.rejected > 0);
  return (
    <div className="stage-snake" aria-label="Application stage snake">
      <div className="stage-snake-track">
        {stages.map((stage, index) => {
          const width = `${Math.max(16, (stage.count / maxCount) * 100)}%`;
          const survival = total ? Math.round((stage.count / total) * 100) : 0;
          return (
            <section className="stage-node" key={stage.id}>
              <div className="stage-node-head">
                <span>{index + 1}</span>
                <strong>{stage.label}</strong>
              </div>
              <div className="stage-flow" style={{ width }}>
                <b>{stage.count}</b>
                <small>{survival}% reach</small>
              </div>
              <div className="stage-node-meta">
                <span>{stage.active} alive</span>
                <span className={stage.rejected ? "drop" : ""}>{stage.rejected} rejected here</span>
              </div>
            </section>
          );
        })}
      </div>
      <div className="stage-drop-grid">
        {(dropStages.length ? dropStages : stages.slice(0, 1)).map((stage) => (
          <article className="stage-drop-card" key={`drop-${stage.id}`}>
            <span>{stage.label}</span>
            <strong>{stage.rejected}</strong>
            <p>{stage.rejected ? "rejections at this furthest known stage" : "No rejected rows in the current filter"}</p>
            <div>
              {stage.rejectedExamples.slice(0, 4).map((app) => (
                <small key={`${stage.id}-${app.company}-${app.postingKey}`}>{app.company} | {app.role}</small>
              ))}
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

function OutreachDetailModal({
  app,
  lane,
  prospects,
  onClose,
}: {
  app: Application;
  lane: "recruiter" | "engineer";
  prospects: Prospect[];
  onClose: () => void;
}) {
  const contacts = buildOutreachContacts(app, lane, prospects);
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="outreach-modal detail" role="dialog" aria-modal="true" aria-label={`${app.company} outreach contacts`} onMouseDown={(event) => event.stopPropagation()}>
        <header>
          <div>
            <p className="eyebrow">{lane === "recruiter" ? "Recruiter lane" : "Engineer lane"}</p>
            <h2>{app.company}</h2>
            <p>{app.role}</p>
          </div>
          <button onClick={onClose} type="button" aria-label="Close"><X size={18} /></button>
        </header>
        <div className="contact-list">
          {contacts.map((contact) => (
            <article className="contact-card" key={`${contact.name}-${contact.url}-${contact.kind}`}>
              <span>{contact.kind}</span>
              <h3>{contact.name}</h3>
              <p>{contact.detail}</p>
              <div className="contact-actions">
                {contact.url && <a href={contact.url} target="_blank" rel="noreferrer"><ExternalLink size={15} /> Open</a>}
                {contact.email && <a href={`mailto:${contact.email}`}><MailCheck size={15} /> Email</a>}
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

function OutreachRow({ app, lane, onInspect }: { app: Application; lane: "recruiter" | "engineer"; onInspect: (app: Application) => void }) {
  const contact = lane === "recruiter" ? app.recruiterContact : app.engineerContact;
  const profile = lane === "recruiter" ? app.recruiterProfile : app.engineerProfile;
  const primary = profile || app.jobLink || "";
  const isDone = Boolean(contact || profile);
  return (
    <div className="recruiter-row">
      <div>
        <strong>{app.company}</strong>
        <p>{app.role}</p>
        <small>{contact || (lane === "recruiter" ? "Needs recruiter contact" : "Needs engineer contact")}</small>
      </div>
      <span className={`lane-state ${isDone ? "done" : "open"}`}>{isDone ? "Done" : "Open"}</span>
      <b>{app.fitScore}</b>
      <button className="row-detail" type="button" onClick={() => onInspect(app)}>Details</button>
      {primary ? <a href={primary} target="_blank" rel="noreferrer"><ArrowUpRight size={18} /></a> : <span />}
    </div>
  );
}

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="tooltip">
      <strong>{label || payload[0].name}</strong>
      {payload.map((item: any) => <p key={item.dataKey || item.name}>{item.name || item.dataKey}: {item.value}</p>)}
    </div>
  );
}

function AppTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const app = payload[0].payload as Application;
  const manualReason = manualApplyReason(app);
  return (
    <div className="tooltip">
      <strong>{app.company}</strong>
      <p>{app.role}</p>
      <p>Fit: {app.fitScore} | {app.status}</p>
      {manualReason && <p>Why manual: {manualReason}</p>}
    </div>
  );
}

function StatusBadge({ app }: { app: Application }) {
  const reason = manualApplyReason(app);
  return (
    <span className="status-wrap">
      <span className={`status ${STATUS_TONE[app.status] || "cool"}`}>{app.status}</span>
      {reason && (
        <span className="manual-info" tabIndex={0} aria-label={`Manual apply reason: ${reason}`}>
          <Info size={13} aria-hidden="true" />
          <span className="manual-info-popover" role="tooltip">{reason}</span>
        </span>
      )}
    </span>
  );
}

function manualApplyReason(app: Application) {
  if (app.status !== MANUAL_STATUS) return "";
  const noteParts = app.notes
    .split(";")
    .map((part) => part.trim())
    .filter(Boolean);
  const blocker = [...noteParts].reverse().find((part) => /manual apply needed|blocked on|posting closed|login|captcha|workday|custom question/i.test(part));
  if (!blocker) return app.notes || "Manual follow-up required.";
  return blocker.replace(/^Manual apply needed:\s*/i, "").trim();
}

type ActionLane = {
  id: string;
  title: string;
  hint: string;
  apps: Application[];
};

function ActionMatrix({ apps }: { apps: Application[] }) {
  const lanes = useMemo(() => buildActionLanes(apps), [apps]);
  return (
    <div className="action-matrix">
      {lanes.map((lane) => (
        <section className="action-lane" key={lane.id}>
          <header>
            <div>
              <h4>{lane.title}</h4>
              <p>{lane.hint}</p>
            </div>
            <b>{lane.apps.length}</b>
          </header>
          <div className="action-cards">
            {lane.apps.slice(0, 8).map((app) => (
              <article className="action-card" key={`${lane.id}-${app.company}-${app.role}-${app.postingKey}`}>
                <div className="action-card-top">
                  <strong>{app.company}</strong>
                  <span>{app.fitScore || "-"}</span>
                </div>
                <p>{app.role}</p>
                <div className="action-meta">
                  <StatusBadge app={app} />
                  <small>{app.source} · {app.location}</small>
                </div>
                <div className="link-pack">
                  {app.jobLink && <a href={app.jobLink} target="_blank" rel="noreferrer" aria-label={`${app.company} job`}><ExternalLink size={15} /></a>}
                  {app.recruiterProfile && <a href={app.recruiterProfile} target="_blank" rel="noreferrer" aria-label={`${app.company} recruiter`}><Users size={15} /></a>}
                  {app.resumePdf && <a href={app.resumePdf} target="_blank" rel="noreferrer" aria-label={`${app.company} resume`}><BriefcaseBusiness size={15} /></a>}
                </div>
              </article>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function Constellation({ apps }: { apps: Application[] }) {
  const nodes = apps.map((app, index) => {
    const angle = index * 137.5 * (Math.PI / 180);
    const radius = 22 + (index % 9) * 7 + Math.max(app.fitScore, 1) * 2.2;
    return {
      app,
      x: 50 + Math.cos(angle) * radius,
      y: 50 + Math.sin(angle) * radius * 0.72,
      r: Math.max(3, app.fitScore / 1.8),
    };
  });

  return (
    <svg className="constellation" viewBox="0 0 100 100" role="img" aria-label="Application constellation">
      <defs>
        <radialGradient id="nodeGlow">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="45%" stopColor="#55d6be" />
          <stop offset="100%" stopColor="#55d6be" stopOpacity="0" />
        </radialGradient>
      </defs>
      {nodes.slice(0, 40).map((node, index) => {
        const next = nodes[(index * 7 + 11) % nodes.length];
        return next ? <line key={`line-${index}`} x1={node.x} y1={node.y} x2={next.x} y2={next.y} /> : null;
      })}
      {nodes.map((node, index) => (
        <circle key={`${node.app.company}-${index}`} cx={node.x} cy={node.y} r={node.r} className={node.app.applied ? "applied" : ""}>
          <title>{node.app.company} - {node.app.role} - fit {node.app.fitScore}</title>
        </circle>
      ))}
    </svg>
  );
}

function buildActionLanes(apps: Application[]): ActionLane[] {
  const open = apps.filter((app) => app.status !== "Rejected" && app.status !== "Archived");
  const sort = (items: Application[]) => [...items].sort((a, b) => actionPriority(b) - actionPriority(a));

  return [
    {
      id: "apply",
      title: "Apply Now",
      hint: "Tailored and high-fit, but not submitted yet.",
      apps: sort(open.filter((app) => !app.applied && app.fitScore >= 8)),
    },
    {
      id: "outreach",
      title: "Outreach",
      hint: "Needs recruiter, alumni, or engineer follow-up.",
      apps: sort(open.filter((app) => app.reachOut || app.recruiterContact || app.recruiterProfile)),
    },
    {
      id: "active",
      title: "Interview / OA",
      hint: "Prep and response-critical opportunities.",
      apps: sort(open.filter((app) => app.status === "Interviewing" || app.status.includes("Assessment"))),
    },
    {
      id: "monitor",
      title: "Monitor",
      hint: "Applied roles waiting for movement.",
      apps: sort(open.filter((app) => app.applied && app.status === "Applied")),
    },
    {
      id: "closed",
      title: "Closed",
      hint: "Rejected roles kept for pipeline stats.",
      apps: sort(apps.filter((app) => app.status === "Rejected")),
    },
  ];
}

function actionPriority(app: Application) {
  const statusBoost = app.status === "Interviewing" ? 30 : app.status.includes("Assessment") ? 24 : app.status === "Applied" ? 8 : 0;
  const contactBoost = app.recruiterContact || app.recruiterProfile ? 6 : 0;
  const outreachBoost = app.reachOut ? 4 : 0;
  return app.fitScore * 10 + statusBoost + contactBoost + outreachBoost;
}

function laneDoneCount(apps: Application[], lane: "recruiter" | "engineer") {
  return apps.filter((app) =>
    lane === "recruiter"
      ? Boolean(app.recruiterContact || app.recruiterProfile)
      : Boolean(app.engineerContact || app.engineerProfile),
  ).length;
}

function outreachPriority(app: Application, lane: "recruiter" | "engineer") {
  const done = lane === "recruiter"
    ? Boolean(app.recruiterContact || app.recruiterProfile)
    : Boolean(app.engineerContact || app.engineerProfile);
  const statusBoost = app.status === "Interviewing" ? 20 : app.status.includes("Assessment") ? 16 : app.status === "Applied" ? 8 : 0;
  return app.fitScore * 10 + statusBoost + (app.reachOut ? 6 : 0) + (done ? -100 : 0);
}

function batchPriority(row: RecruiterBatch) {
  const approvalBoost = row.approval.toLowerCase() === "approved" ? 2 : 0;
  const labeledBoost = row.recruiterName && row.recruiterProfile ? 1 : 0;
  const blockedPenalty = ["skipped", "blocked"].includes(row.outcome.toLowerCase()) ? -80 : 0;
  return row.fitScore * 100 + approvalBoost + labeledBoost + blockedPenalty;
}

function engineerBatchPriority(row: EngineerBatch) {
  const approvalBoost = row.approval.toLowerCase() === "approved" ? 2 : 0;
  const labeledBoost = row.engineerName && row.engineerProfile ? 1 : 0;
  const blockedPenalty = ["skipped", "blocked"].includes(row.outcome.toLowerCase()) ? -80 : 0;
  return row.fitScore * 100 + approvalBoost + labeledBoost + blockedPenalty;
}

function readIgnoredBatchContacts() {
  try {
    const stored = window.localStorage.getItem(BATCH_IGNORE_STORAGE_KEY);
    if (!stored) return new Set<string>();
    const values = JSON.parse(stored);
    if (!Array.isArray(values)) return new Set<string>();
    return new Set(values.filter((value): value is string => typeof value === "string"));
  } catch {
    return new Set<string>();
  }
}

function batchIgnoreKey(lane: "recruiter" | "engineer", postingKey: string, name: string, profile: string) {
  return [lane, postingKey, name, profile].map((value) => value.trim().toLowerCase()).join("|");
}

function recruiterBatchIgnoreKey(row: RecruiterBatch) {
  return batchIgnoreKey("recruiter", row.postingKey, row.recruiterName, row.recruiterProfile);
}

function engineerBatchIgnoreKey(row: EngineerBatch) {
  return batchIgnoreKey("engineer", row.postingKey, row.engineerName, row.engineerProfile);
}

function activeRoleSkipKey(lane: "recruiter" | "engineer", group: OutreachRoleBucket) {
  const primaryContact = group.contacts[0];
  return batchIgnoreKey(lane, group.key, primaryContact?.name || "", primaryContact?.profile || "");
}

function batchStateLabel(approval: string, outcome: string, hasContact: boolean): string {
  const a = approval.toLowerCase();
  const o = outcome.toLowerCase();
  if (o === "skipped" || o === "blocked") return outcome || "Blocked";
  if (a === "approved") return "Approved";
  if (hasContact) return "Labeled";
  return "Research";
}

function outreachRowDataFromRecruiterBatch(row: RecruiterBatch): OutreachRowData {
  const hasContact = Boolean(row.recruiterName && row.recruiterProfile);
  return {
    key: recruiterBatchIgnoreKey(row),
    lane: "recruiter",
    company: row.company,
    role: row.role,
    postingKey: row.postingKey,
    fitScore: row.fitScore,
    status: row.status,
    contactName: row.recruiterName || "",
    profile: row.recruiterProfile || "",
    position: row.recruiterPosition || "",
    approval: row.approval || "",
    outcome: row.outcome || "Not reached out",
    route: row.route || "",
    connectionNote: row.connectionNote || "",
    lastChecked: row.lastChecked || "",
    notes: row.notes || "",
    states: [batchStateLabel(row.approval, row.outcome, hasContact)],
    recruiterSignal: row.recruiterSignal,
  };
}

function outreachRowDataFromEngineerBatch(row: EngineerBatch): OutreachRowData {
  const hasContact = Boolean(row.engineerName && row.engineerProfile);
  return {
    key: engineerBatchIgnoreKey(row),
    lane: "engineer",
    company: row.company,
    role: row.role,
    postingKey: row.postingKey,
    fitScore: row.fitScore,
    status: row.status,
    contactName: row.engineerName || "",
    profile: row.engineerProfile || "",
    position: row.engineerPosition || "",
    approval: row.approval || "",
    outcome: row.outcome || "Not reached out",
    route: row.route || "",
    connectionNote: row.connectionNote || "",
    lastChecked: row.lastChecked || "",
    notes: row.notes || "",
    states: [batchStateLabel(row.approval, row.outcome, hasContact)],
    engineerSignal: row.engineerSignal,
  };
}

function outreachRowDataFromGroup(lane: "recruiter" | "engineer", group: OutreachRoleBucket): OutreachRowData {
  const primaryContact = group.contacts[0];
  return {
    key: activeRoleSkipKey(lane, group),
    lane,
    company: group.company,
    role: group.role,
    postingKey: group.key,
    fitScore: group.fitScore,
    status: group.status,
    contactName: primaryContact?.name || "",
    profile: primaryContact?.profile || "",
    position: primaryContact?.position || "",
    approval: primaryContact?.approval || "",
    outcome: primaryContact?.outcome || "Not reached out",
    route: primaryContact?.route || "",
    connectionNote: primaryContact?.connectionNote || "",
    lastChecked: primaryContact?.lastChecked || "",
    notes: primaryContact?.notes || "",
    states: group.states,
    recruiterSignal: primaryContact?.recruiterSignal,
    engineerSignal: primaryContact?.engineerSignal,
  };
}

function roleGroupKey(row: { postingKey: string; company: string; role: string }) {
  return row.postingKey || `${normalizeKey(row.company)}|${normalizeKey(row.role)}`;
}

function ensureActiveGroup(groups: Map<string, OutreachRoleBucket>, row: { postingKey: string; company: string; role: string; fitScore: number; status: string }) {
  const key = roleGroupKey(row);
  const current = groups.get(key);
  if (current) {
    current.fitScore = Math.max(current.fitScore, row.fitScore || 0);
    return current;
  }
  const next: OutreachRoleBucket = {
    key,
    company: row.company,
    role: row.role,
    fitScore: row.fitScore || 0,
    status: row.status,
    count: 0,
    contacts: [],
    states: [],
  };
  groups.set(key, next);
  return next;
}

function buildActiveRoleGroups(rows: Array<RecruiterBatch | EngineerBatch>, lane: "recruiter" | "engineer", ignoredContacts: Set<string>) {
  const groups = new Map<string, OutreachRoleBucket>();
  rows
    .filter((row) => isActiveBatchWork(row) && !ignoredContacts.has(lane === "recruiter" ? recruiterBatchIgnoreKey(row as RecruiterBatch) : engineerBatchIgnoreKey(row as EngineerBatch)))
    .forEach((row) => {
      const group = ensureActiveGroup(groups, row);
      const name = lane === "recruiter" ? (row as RecruiterBatch).recruiterName : (row as EngineerBatch).engineerName;
      const profile = lane === "recruiter" ? (row as RecruiterBatch).recruiterProfile : (row as EngineerBatch).engineerProfile;
      const position = lane === "recruiter" ? (row as RecruiterBatch).recruiterPosition : (row as EngineerBatch).engineerPosition;
      const state = activeBatchState(row, lane);
      group.count += 1;
      if (name || profile) {
        group.contacts.push({
          lane,
          name: name || "Unnamed contact",
          profile,
          position,
          approval: row.approval,
          outcome: row.outcome,
          route: row.route,
          connectionNote: row.connectionNote,
          lastChecked: row.lastChecked,
          notes: row.notes,
          recruiterSignal: (row as RecruiterBatch).recruiterSignal,
          engineerSignal: (row as EngineerBatch).engineerSignal,
        });
      }
      if (!group.states.includes(state)) group.states.push(state);
    });
  return sortActiveRoleBuckets([...groups.values()]);
}

function buildReachedOutRoleGroups(rows: Array<RecruiterBatch | EngineerBatch>, lane: "recruiter" | "engineer") {
  const groups = new Map<string, OutreachRoleBucket>();
  const ensure = (row: { postingKey: string; company: string; role: string }) => {
    const key = `${lane}|${roleGroupKey(row)}`;
    const current = groups.get(key);
    if (current) return current;
    const next: OutreachRoleBucket = { key, company: row.company, role: row.role, fitScore: 0, status: "", count: 0, states: [], contacts: [] };
    groups.set(key, next);
    return next;
  };
  rows
    .filter((row) => row.outcome.toLowerCase() === "sent")
    .forEach((row) => {
      const name = lane === "recruiter" ? (row as RecruiterBatch).recruiterName : (row as EngineerBatch).engineerName;
      const position = lane === "recruiter" ? (row as RecruiterBatch).recruiterPosition : (row as EngineerBatch).engineerPosition;
      const profile = lane === "recruiter" ? (row as RecruiterBatch).recruiterProfile : (row as EngineerBatch).engineerProfile;
      const group = ensure(row);
      group.fitScore = Math.max(group.fitScore, row.fitScore || 0);
      group.status = row.status;
      group.count += 1;
      group.contacts.push({
        lane,
        name: name || (lane === "recruiter" ? "Recruiter" : "Engineer"),
        position,
        profile,
        approval: row.approval,
        outcome: row.outcome,
        route: row.route,
        connectionNote: row.connectionNote,
        lastChecked: row.lastChecked,
        notes: row.notes,
        recruiterSignal: (row as RecruiterBatch).recruiterSignal,
        engineerSignal: (row as EngineerBatch).engineerSignal,
      });
    });
  return [...groups.values()].sort((a, b) => b.contacts.length - a.contacts.length || a.company.localeCompare(b.company));
}

function filterIgnoredRoleBuckets(groups: OutreachRoleBucket[], ignoredContacts: Set<string>, lane: "recruiter" | "engineer") {
  return sortActiveRoleBuckets(groups
    .map((group) => {
      const contacts = group.contacts.filter((contact) => !ignoredContacts.has(batchIgnoreKey(lane, group.key, contact.name, contact.profile)));
      return { ...group, contacts };
    })
    .filter((group) => group.contacts.length || group.states.includes("Needs label")));
}

function isActiveBatchWork(row: RecruiterBatch | EngineerBatch) {
  const outcome = row.outcome.toLowerCase();
  return outcome !== "sent" && outcome !== "skipped" && outcome !== "blocked";
}

function activeBatchState(row: RecruiterBatch | EngineerBatch, lane: "recruiter" | "engineer") {
  const approval = row.approval.toLowerCase();
  const hasContact = lane === "recruiter"
    ? Boolean((row as RecruiterBatch).recruiterName || (row as RecruiterBatch).recruiterProfile)
    : Boolean((row as EngineerBatch).engineerName || (row as EngineerBatch).engineerProfile);
  if (!hasContact) return "Needs label";
  if (approval === "approved") return "Approved, not sent";
  return "Labeled, needs approval";
}

function stateTone(state: string) {
  if (state.startsWith("Approved")) return "approved";
  if (state.startsWith("Labeled")) return "labeled";
  return "research";
}

function stateRank(state: string) {
  if (state.startsWith("Approved")) return 0;
  if (state.startsWith("Labeled")) return 1;
  if (state.startsWith("Needs label")) return 2;
  return 3;
}

function primaryState(group: OutreachRoleBucket) {
  return [...group.states].sort((a, b) => stateRank(a) - stateRank(b))[0] || "";
}

function sortActiveRoleBuckets(groups: OutreachRoleBucket[]) {
  return [...groups].sort((a, b) =>
    stateRank(primaryState(a)) - stateRank(primaryState(b)) ||
    b.fitScore - a.fitScore ||
    a.company.localeCompare(b.company),
  );
}

function oneBasedRangeStart(total: number, startIndex: number) {
  return Math.min(Math.max(startIndex || 1, 1), Math.max(total, 1));
}

function sliceByOneBasedRange<T>(rows: T[], startIndex: number, endIndex: string) {
  const start = oneBasedRangeStart(rows.length, startIndex) - 1;
  const parsedEnd = Number(endIndex);
  const end = endIndex.trim() ? Math.min(Math.max(parsedEnd || rows.length, 1), rows.length) : rows.length;
  return rows.slice(start, end);
}

function buildOutreachContacts(app: Application, lane: "recruiter" | "engineer", prospects: Prospect[]) {
  const contacts: Array<{ kind: string; name: string; detail: string; url: string; email: string }> = [];
  const add = (contact: { kind: string; name: string; detail?: string; url?: string; email?: string }) => {
    const key = `${contact.kind}|${contact.name}|${contact.url || ""}|${contact.email || ""}`.toLowerCase();
    if (contacts.some((item) => `${item.kind}|${item.name}|${item.url}|${item.email}`.toLowerCase() === key)) return;
    contacts.push({
      kind: contact.kind,
      name: contact.name,
      detail: contact.detail || "",
      url: contact.url || "",
      email: contact.email || "",
    });
  };

  const laneContact = lane === "recruiter" ? app.recruiterContact : app.engineerContact;
  const laneProfile = lane === "recruiter" ? app.recruiterProfile : app.engineerProfile;
  if (laneContact || laneProfile) {
    add({
      kind: lane === "recruiter" ? "Tracked recruiter" : "Tracked engineer",
      name: laneContact || "Saved LinkedIn profile",
      detail: "Saved directly on the application row.",
      url: laneProfile,
    });
  }

  const targetWords = lane === "recruiter"
    ? ["recruiter", "talent", "hiring", "university"]
    : ["engineer", "alumni", "employee", "peer"];
  prospects
    .filter((prospect) =>
      normalizeKey(prospect.company) === normalizeKey(app.company) &&
      (!prospect.postingKey || !app.postingKey || normalizeKey(prospect.postingKey) === normalizeKey(app.postingKey)) &&
      targetWords.some((word) => normalizeKey(prospect.targetType).includes(word) || normalizeKey(prospect.title).includes(word)),
    )
    .forEach((prospect) => {
      add({
        kind: prospect.targetType || (lane === "recruiter" ? "Recruiter prospect" : "Engineer prospect"),
        name: prospect.name || "Unnamed prospect",
        detail: [prospect.title, prospect.emailStatus, prospect.notes].filter(Boolean).join(" | "),
        url: prospect.linkedin,
        email: prospect.apolloEmail,
      });
    });

  app.noteLinks
    .filter((link) => link.url.includes("linkedin.com/in/"))
    .forEach((link) => {
      add({
        kind: "LinkedIn note link",
        name: link.label || "LinkedIn profile",
        detail: "Found in tracker notes.",
        url: link.url,
      });
    });

  if (!contacts.length) {
    add({
      kind: lane === "recruiter" ? "Open recruiter slot" : "Open engineer slot",
      name: lane === "recruiter" ? "No recruiter saved yet" : "No engineer saved yet",
      detail: "Run the lane queue, pick contacts, then record sends with update_outreach_tracker.py.",
    });
  }
  return contacts;
}

function normalizeKey(value: string) {
  return (value || "").trim().toLowerCase().split(/\s+/).join(" ");
}

function repoLink(path: string) {
  if (!path) return "";
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  const marker = "/CodexSkills/";
  const relative = path.includes(marker) ? path.split(marker, 2)[1] : path.replace(/^\/+/, "");
  const encoded = relative.split("/").map(encodeURIComponent).join("/");
  const isPdf = relative.toLowerCase().endsWith(".pdf");
  return `https://github.com/SpeciLiam/CodexSkills/${isPdf ? "raw" : "tree"}/main/${encoded}`;
}

function resumeName(path: string) {
  const filename = path.split("/").filter(Boolean).pop() || "Tailored resume";
  return filename.replace(/_/g, " ");
}

function summarize(apps: Application[]) {
  const applied = apps.filter((app) => app.applied).length;
  const avgFit = apps.reduce((sum, app) => sum + app.fitScore, 0) / Math.max(apps.length, 1);
  return { applied, avgFit };
}

const APPLICATION_STAGES = [
  { id: "tailored", label: "Tailored" },
  { id: "applied", label: "Applied" },
  { id: "assessment", label: "OA / Take-home" },
  { id: "screen", label: "Recruiter Screen" },
  { id: "first", label: "First Round" },
  { id: "second", label: "Second Round" },
  { id: "final", label: "Final / Offer" },
] as const;

function buildStageSnake(apps: Application[]) {
  const stages = APPLICATION_STAGES.map((stage) => ({
    ...stage,
    count: 0,
    active: 0,
    rejected: 0,
    rejectedExamples: [] as Application[],
  }));

  apps.forEach((app) => {
    const stageIndex = inferApplicationStageIndex(app);
    const isRejected = app.status.toLowerCase() === "rejected";
    stages.forEach((stage, index) => {
      if (index > stageIndex) return;
      stage.count += 1;
      if (!isRejected) stage.active += 1;
    });
    if (isRejected) {
      stages[stageIndex].rejected += 1;
      stages[stageIndex].rejectedExamples.push(app);
    }
  });

  stages.forEach((stage) => {
    stage.rejectedExamples.sort((a, b) => b.fitScore - a.fitScore || a.company.localeCompare(b.company));
  });

  return { total: apps.length, stages };
}

function inferApplicationStageIndex(app: Application) {
  const status = app.status.toLowerCase();
  const notes = app.notes.toLowerCase();
  const text = `${status}; ${notes}`;
  let index = app.applied ? 1 : 0;

  if (/online assessment|assessment|take-home|take home|coding challenge|codesignal|hackerrank|technical screen/.test(text)) {
    index = Math.max(index, 2);
  }
  if (/recruiter screen|phone screen|intro call|screen requested|screen scheduled/.test(text)) {
    index = Math.max(index, 3);
  }
  if (/first round|one-way video|video interview|interview invite|interview availability|interview signup|interview requested/.test(text)) {
    index = Math.max(index, 4);
  }
  if (/second round|technical interview|onsite|on-site|panel interview|final round/.test(text)) {
    index = Math.max(index, 5);
  }
  if (/offer|finalist|verbal offer|written offer/.test(text)) {
    index = Math.max(index, 6);
  }

  return Math.min(index, APPLICATION_STAGES.length - 1);
}

function buildDailyApplicationPulse(timeline: Array<Record<string, number | string>>, apps: Application[]) {
  const reachOutsByDate = buildReachOutsByDate(apps);
  const outreachCoverage = buildOutreachCoverage(apps);
  const points = timeline.map((point, index, items) => {
    const previous = Number(items[index - 1]?.applied || 0);
    const current = Number(point.applied || 0);
    const next = Number(items[index + 1]?.applied || 0);
    const date = String(point.date || "");
    const reachOuts = reachOutsByDate.get(date) || { recruiter: 0, engineer: 0, other: 0 };
    const totalReachOuts = reachOuts.recruiter + reachOuts.engineer + reachOuts.other;
    return {
      date,
      applications: current,
      pace: Number(((previous + current + next) / 3).toFixed(1)),
      recruiterReachOuts: reachOuts.recruiter,
      engineerReachOuts: reachOuts.engineer,
      otherReachOuts: reachOuts.other,
      totalReachOuts,
    };
  });
  const activeDays = points.filter((point) => point.applications > 0);
  const outreachDays = points.filter((point) => point.totalReachOuts > 0);
  const total = points.reduce((sum, point) => sum + point.applications, 0);
  const recruiterTotal = points.reduce((sum, point) => sum + point.recruiterReachOuts, 0);
  const engineerTotal = points.reduce((sum, point) => sum + point.engineerReachOuts, 0);
  const otherReachOutTotal = points.reduce((sum, point) => sum + point.otherReachOuts, 0);
  const reachOutTotal = recruiterTotal + engineerTotal + otherReachOutTotal;
  const peak = points.reduce(
    (best, point) => (point.applications > best.applications ? point : best),
    points[0] || { date: "", applications: 0, pace: 0, recruiterReachOuts: 0, engineerReachOuts: 0, otherReachOuts: 0, totalReachOuts: 0 },
  );
  const reachOutPeak = points.reduce(
    (best, point) => (point.totalReachOuts > best.totalReachOuts ? point : best),
    points[0] || { date: "", applications: 0, pace: 0, recruiterReachOuts: 0, engineerReachOuts: 0, otherReachOuts: 0, totalReachOuts: 0 },
  );
  const latest = [...points].reverse().find((point) => point.applications > 0) || points[points.length - 1] || peak;

  return {
    points,
    total,
    recruiterTotal,
    engineerTotal,
    otherReachOutTotal,
    reachOutTotal,
    trackedRecruiterTotal: outreachCoverage.recruiter,
    trackedEngineerTotal: outreachCoverage.engineer,
    trackedReachOutTotal: outreachCoverage.recruiter + outreachCoverage.engineer,
    reachOutPeakDate: reachOutPeak.date,
    reachOutPeakCount: reachOutPeak.totalReachOuts,
    reachOutAverage: reachOutTotal / Math.max(outreachDays.length, 1),
    peakDate: peak.date,
    peakCount: peak.applications,
    average: total / Math.max(activeDays.length, 1),
    latestDate: latest.date,
    latestCount: latest.applications,
  };
}

function buildOutreachCoverage(apps: Application[]) {
  return apps.reduce(
    (totals, app) => {
      if (app.recruiterContact || app.recruiterProfile) totals.recruiter += 1;
      if (app.engineerContact || app.engineerProfile) totals.engineer += 1;
      return totals;
    },
    { recruiter: 0, engineer: 0 },
  );
}

function buildReachOutsByDate(apps: Application[]) {
  const counts = new Map<string, { recruiter: number; engineer: number; other: number }>();

  apps.forEach((app) => {
    app.notes
      .split(";")
      .map((note) => note.trim())
      .filter((note) => /LinkedIn (?:invite|invites|InMail) sent/i.test(note))
      .forEach((note) => {
        const date = note.match(/20\d{2}-\d{2}-\d{2}/)?.[0];
        if (!date) return;
        const text = note.toLowerCase();
        const profileCount = Math.max((note.match(/linkedin\.com\/in\//gi) || []).length, 1);
        const hasEngineerSignal = text.includes("(engineer)") || text.includes(" engineer ");
        const hasRecruiterSignal = text.includes("(recruiter)") || text.includes(" recruiter ") || text.includes(" talent ") || text.includes(" hiring ");
        const entry = counts.get(date) || { recruiter: 0, engineer: 0, other: 0 };

        if (hasEngineerSignal && !hasRecruiterSignal) {
          entry.engineer += profileCount;
        } else if (hasRecruiterSignal && !hasEngineerSignal) {
          entry.recruiter += profileCount;
        } else {
          entry.other += profileCount;
        }

      counts.set(date, entry);
      });
  });

  return counts;
}

export default App;
