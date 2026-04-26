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
import type { Application, TrackerData } from "./lib/types";

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
} as const;

function App() {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("All");
  const [minFit, setMinFit] = useState(0);

  const statuses = useMemo(() => ["All", ...data.stats.statusCounts.map((item) => item.name)], []);
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return data.applications.filter((app) => {
      const matchesText =
        !needle ||
        [app.company, app.role, app.location, app.source, app.recruiterContact, app.notes].some((value) =>
          value.toLowerCase().includes(needle),
        );
      return matchesText && (status === "All" || app.status === status) && app.fitScore >= minFit;
    });
  }, [query, status, minFit]);

  const filteredStats = useMemo(() => summarize(filtered), [filtered]);
  const recruiterApps = useMemo(
    () =>
      filtered
        .filter((app) => app.recruiterContact || app.recruiterProfile || app.noteLinks.some((link) => link.url.includes("linkedin.com/in/")))
        .sort((a, b) => b.fitScore - a.fitScore)
        .slice(0, 18),
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
          <Constellation apps={filtered.slice(0, 90)} />
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
        <MiniMetric label="Recruiter paths" value={recruiterApps.length} />
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
        <Panel title="Recruiter Flight Deck" icon={<Users />} info={INFO_COPY.recruiters} wide>
          <div className="recruiter-list">
            {recruiterApps.map((app) => <RecruiterRow key={`${app.company}-${app.role}-${app.postingKey}`} app={app} />)}
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
                  <td>
                    <div className="link-pack">
                      {app.jobLink && <a href={app.jobLink} target="_blank" rel="noreferrer" aria-label="Job"><ExternalLink size={16} /></a>}
                      {app.recruiterProfile && <a href={app.recruiterProfile} target="_blank" rel="noreferrer" aria-label="Recruiter"><Users size={16} /></a>}
                      {app.resumePdf && <a href={app.resumePdf} target="_blank" rel="noreferrer" aria-label="Resume"><BriefcaseBusiness size={16} /></a>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
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

function RecruiterRow({ app }: { app: Application }) {
  const linkedinNotes = app.noteLinks.filter((link) => link.url.includes("linkedin.com/in/"));
  const primary = app.recruiterProfile || linkedinNotes[0]?.url || "";
  return (
    <div className="recruiter-row">
      <div>
        <strong>{app.company}</strong>
        <p>{app.role}</p>
        <small>{app.recruiterContact || linkedinNotes[0]?.label || "LinkedIn path in notes"}</small>
      </div>
      <span className={`status ${STATUS_TONE[app.status] || "cool"}`}>{app.status}</span>
      <b>{app.fitScore}</b>
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

function summarize(apps: Application[]) {
  const applied = apps.filter((app) => app.applied).length;
  const avgFit = apps.reduce((sum, app) => sum + app.fitScore, 0) / Math.max(apps.length, 1);
  return { applied, avgFit };
}

export default App;
