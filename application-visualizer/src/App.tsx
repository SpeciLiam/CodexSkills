import { useMemo, useState, type ReactNode } from "react";
import {
  Activity,
  ArrowUpRight,
  BriefcaseBusiness,
  ExternalLink,
  Filter,
  Info,
  Link as LinkIcon,
  MailCheck,
  Network,
  Radar,
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
import { hostFromUrl, percent, readableDate } from "./lib/format";
import type { Application, Prospect, TrackerData } from "./lib/types";

const data = rawData as TrackerData;

const COLORS = ["#55d6be", "#f7b267", "#f25f5c", "#70a1ff", "#b388ff", "#f4d35e", "#8dd7cf", "#ff8fab"];
const STATUS_TONE: Record<string, string> = {
  Applied: "good",
  Interviewing: "hot",
  "Online Assessment": "hot",
  Rejected: "bad",
  "Resume Tailored": "cool",
  Offer: "hot",
};

const NAV_ITEMS = [
  { href: "#overview", label: "Overview" },
  { href: "#actions", label: "Actions" },
  { href: "#trends", label: "Trends" },
  { href: "#outreach", label: "Outreach" },
  { href: "#browser", label: "Browser" },
  { href: "#pipeline", label: "Pipeline" },
];

const INFO_COPY = {
  actions: "A practical action board. Roles are grouped by what to do next: apply, follow up, prepare for interviews or assessments, monitor, or deprioritize closed/rejected roles. Cards are sorted by fit score so the strongest opportunities stay visible.",
  velocity: "Shows how the pipeline grew over time. The filled curve is cumulative tracked roles, while the line highlights applications submitted on each date.",
  status: "Breaks the tracker into current outcomes such as tailored, applied, interviewing, assessment, rejected, or offer.",
  fit: "Counts roles by fit score, making it easy to see whether the pipeline is concentrated around high-fit opportunities.",
  source: "Compares where roles are coming from, so you can see which channels are feeding the most opportunities.",
  role: "Plots visible applications by fit score and status. It is useful for spotting high-fit roles that are still only tailored or need action.",
  radar: "Summarizes campaign health across applied rate, high-fit share, reach-out coverage, recruiter coverage, and active share.",
  recruiters: "Lists applications with a known recruiter or LinkedIn path, sorted toward stronger fit so outreach targets are easy to open.",
  gaps: "Highlights high-fit reach-out rows that still need more prospects or ready email addresses.",
  pipeline: "Explains which Codex skills to ask Codex to run. The commands are the deterministic scripts behind those skills, but the intended workflow is that Codex runs them and updates the tracker for you.",
} as const;

const PIPELINE_MODES = [
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
    name: "Recruiter Lane",
    command: "python3 skills/recruiting-pipeline/scripts/build_daily_recruiting_plan.py --mode recruiter",
    description: "Ask Codex for recruiter-only outreach. It focuses on talent, university, and technical recruiter contacts.",
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
    name: "Tailor or apply",
    command: "python3 skills/recruiting-pipeline/scripts/build_daily_recruiting_plan.py --mode resume",
    note: "Use this lane when adding a new role, tailoring a resume, or finding high-fit tailored roles that are ready to submit.",
  },
  {
    step: "4",
    name: "Recruiter outreach lane",
    command: "python3 skills/linkedin-outreach/scripts/build_outreach_targets.py --contact-type recruiter --limit 20",
    note: "Ask Codex to run this as its own lane. It finds one recruiter or talent contact per reachable role.",
  },
  {
    step: "5",
    name: "Engineer outreach lane",
    command: "python3 skills/linkedin-outreach/scripts/build_outreach_targets.py --contact-type engineer --limit 20",
    note: "Ask Codex to run this as a separate lane. It finds one engineer, UGA alum, or relevant employee per role.",
  },
  {
    step: "6",
    name: "Fill prospect gaps",
    command: "python3 skills/company-prospecting/scripts/build_company_prospect_targets.py --limit 20",
    note: "Use this when LinkedIn lanes need deeper company-level people or Apollo-ready email candidates.",
  },
  {
    step: "7",
    name: "Prep hot opportunities",
    command: "python3 skills/recruiting-pipeline/scripts/build_daily_recruiting_plan.py --mode prep",
    note: "Pull interviews and online assessments to the top so prep work does not get buried under new applications.",
  },
  {
    step: "8",
    name: "Rebuild dashboard",
    command: "python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py && cd application-visualizer && npm run build",
    note: "Run after tracker or outreach edits so the website reflects the latest markdown data.",
  },
  {
    step: "9",
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
    name: "linkedin-outreach",
    role: "Networking",
    text: "Builds separate recruiter and engineer queues, drafts connection notes, and records each successful invite back into the tracker.",
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

function App() {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("All");
  const [minFit, setMinFit] = useState(0);
  const [openOutreachLane, setOpenOutreachLane] = useState<"recruiter" | "engineer" | null>(null);
  const [selectedOutreach, setSelectedOutreach] = useState<{ app: Application; lane: "recruiter" | "engineer" } | null>(null);

  const statuses = useMemo(() => ["All", ...data.stats.statusCounts.map((item) => item.name)], []);
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return data.applications.filter((app) => {
      const matchesText =
        !needle ||
        [app.company, app.role, app.location, app.source, app.recruiterContact, app.engineerContact, app.notes].some((value) =>
          value.toLowerCase().includes(needle),
        );
      return matchesText && (status === "All" || app.status === status) && app.fitScore >= minFit;
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

  return (
    <main>
      <nav className="sticky-nav" aria-label="Dashboard sections">
        <a className="brand-chip" href="#overview"><Sparkles size={16} /> Tracker</a>
        <div>
          {NAV_ITEMS.map((item) => (
            <a key={item.href} href={item.href}>{item.label}</a>
          ))}
        </div>
        <span>{filtered.length} visible</span>
      </nav>

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
          <Kpi icon={<Send />} label="Reach out" value={data.stats.kpis.reachOut} sub="queued targets" />
          <Kpi icon={<MailCheck />} label="Ready emails" value={data.stats.kpis.readyEmails} sub={`${data.stats.kpis.prospects} prospects`} />
        </div>
      </section>

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

      <section className="metric-strip">
        <MiniMetric label="Visible roles" value={filtered.length} />
        <MiniMetric label="Visible applied" value={filteredStats.applied} />
        <MiniMetric label="Avg fit" value={filteredStats.avgFit.toFixed(1)} />
        <MiniMetric label="Recruiter lanes" value={laneDoneCount(recruiterApps, "recruiter")} />
        <MiniMetric label="Engineer lanes" value={laneDoneCount(engineerApps, "engineer")} />
      </section>

      <section id="actions" className="dashboard-grid section-anchor">
        <Panel title="Action Matrix" icon={<Target />} info={INFO_COPY.actions} wide>
          <ActionMatrix apps={filtered} />
        </Panel>

        <Panel id="trends" title="Application Velocity" icon={<Activity />} info={INFO_COPY.velocity}>
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

      <section id="outreach" className="split section-anchor">
        <Panel title="Outreach Flight Deck" icon={<Users />} info={INFO_COPY.recruiters} wide>
          <div className="outreach-lanes">
            <OutreachLane
              lane="recruiter"
              title="Recruiter Outreach"
              description="Talent, university, technical recruiter, or hiring contact."
              apps={recruiterApps}
              onOpen={() => setOpenOutreachLane("recruiter")}
              onInspect={(app) => setSelectedOutreach({ app, lane: "recruiter" })}
            />
            <OutreachLane
              lane="engineer"
              title="Engineer Outreach"
              description="Engineer, UGA alum, team-aligned employee, or credible peer contact."
              apps={engineerApps}
              onOpen={() => setOpenOutreachLane("engineer")}
              onInspect={(app) => setSelectedOutreach({ app, lane: "engineer" })}
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

      {openOutreachLane && (
        <OutreachModal
          lane={openOutreachLane}
          apps={openOutreachLane === "recruiter" ? recruiterApps : engineerApps}
          onClose={() => setOpenOutreachLane(null)}
          onInspect={(app) => setSelectedOutreach({ app, lane: openOutreachLane })}
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

      <section id="browser" className="table-section section-anchor">
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
                <th>Status</th>
                <th>Fit</th>
                <th>Recruiter</th>
                <th>Engineer</th>
                <th>Links</th>
              </tr>
            </thead>
            <tbody>
              {filtered.slice(0, 80).map((app) => (
                <tr key={`${app.company}-${app.role}-${app.postingKey}`}>
                  <td><strong>{app.company}</strong><small>{app.source}</small></td>
                  <td>{app.role}<small>{app.location}</small></td>
                  <td><span className={`status ${STATUS_TONE[app.status] || "cool"}`}>{app.status}</span></td>
                  <td><b>{app.fitScore || "-"}</b></td>
                  <td>{app.recruiterContact || "Open"}<small>{app.recruiterProfile && hostFromUrl(app.recruiterProfile)}</small></td>
                  <td>{app.engineerContact || "Open"}<small>{app.engineerProfile && hostFromUrl(app.engineerProfile)}</small></td>
                  <td>
                    <div className="link-pack">
                      {app.jobLink && <a href={app.jobLink} target="_blank" rel="noreferrer" aria-label="Job"><ExternalLink size={16} /></a>}
                      {app.recruiterProfile && <a href={app.recruiterProfile} target="_blank" rel="noreferrer" aria-label="Recruiter"><Users size={16} /></a>}
                      {app.engineerProfile && <a href={app.engineerProfile} target="_blank" rel="noreferrer" aria-label="Engineer"><Users size={16} /></a>}
                      {app.resumePdf && <a href={app.resumePdf} target="_blank" rel="noreferrer" aria-label="Resume"><BriefcaseBusiness size={16} /></a>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section id="pipeline" className="pipeline-section section-anchor">
        <div className="section-heading">
          <div>
            <p className="eyebrow"><TerminalSquare size={16} /> Codex skills</p>
            <h2>Codex Skill Runbook</h2>
          </div>
          <InfoBubble text={INFO_COPY.pipeline} />
        </div>

        <div className="pipeline-hero">
          <div>
            <h3>Ask Codex to run the whole machine, or just one lane.</h3>
            <p>
              A Codex skill is a local workflow Codex can follow with scripts, tracker rules, and guardrails. You can ask Codex to run a skill by name,
              or ask for the outcome in plain English. The commands shown here are the underlying scripts Codex runs when it needs deterministic data.
            </p>
          </div>
          <div className="pipeline-flow" aria-label="Recommended recruiting flow">
            {["Refresh", "Tailor", "Apply", "Recruiter", "Engineer", "Prospect", "Prep", "Visualize"].map((step) => (
              <span key={step}>{step}</span>
            ))}
          </div>
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

function MiniMetric({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <span>{label}</span>
      <b>{value}</b>
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
  return (
    <div className="tooltip">
      <strong>{app.company}</strong>
      <p>{app.role}</p>
      <p>Fit: {app.fitScore} | {app.status}</p>
    </div>
  );
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
                  <span className={`status ${STATUS_TONE[app.status] || "cool"}`}>{app.status}</span>
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

function summarize(apps: Application[]) {
  const applied = apps.filter((app) => app.applied).length;
  const avgFit = apps.reduce((sum, app) => sum + app.fitScore, 0) / Math.max(apps.length, 1);
  return { applied, avgFit };
}

export default App;
