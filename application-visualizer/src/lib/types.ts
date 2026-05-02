export type CountDatum = {
  name: string;
  value: number;
};

export type Application = {
  company: string;
  role: string;
  applied: boolean;
  status: string;
  fitScore: number;
  reachOut: boolean;
  referral: string;
  dateAdded: string;
  location: string;
  source: string;
  jobLink: string;
  postingKey: string;
  resumeFolder: string;
  resumePdf: string;
  recruiterContact: string;
  recruiterProfile: string;
  engineerContact: string;
  engineerProfile: string;
  notes: string;
  noteLinks: Array<{ label: string; url: string }>;
  activityDates: string[];
};

export type OutreachQueue = {
  company: string;
  role: string;
  postingKey: string;
  fitScore: number;
  status: string;
  reachOut: boolean;
  jobLink: string;
  prospectCount: number;
  readyEmails: number;
  lastUpdated: string;
  notes: string;
};

export type Prospect = {
  company: string;
  postingKey: string;
  priority: number;
  targetType: string;
  name: string;
  title: string;
  linkedin: string;
  apolloEmail: string;
  emailStatus: string;
  notes: string;
};

export type JobIntake = {
  source: string;
  company: string;
  role: string;
  location: string;
  postingKey: string;
  jobUrl: string;
  discoveredAt: string;
  postedAge: string;
  fitScore: number;
  status: string;
  reason: string;
  trackerPostingKey: string;
};

export type RecruiterBatch = {
  batch: string;
  company: string;
  role: string;
  postingKey: string;
  fitScore: number;
  status: string;
  recruiterName: string;
  recruiterProfile: string;
  recruiterPosition: string;
  route: string;
  connectionNote: string;
  approval: string;
  outcome: string;
  lastChecked: string;
  notes: string;
};

export type EngineerBatch = {
  batch: string;
  company: string;
  role: string;
  postingKey: string;
  fitScore: number;
  status: string;
  engineerName: string;
  engineerProfile: string;
  engineerPosition: string;
  route: string;
  connectionNote: string;
  approval: string;
  outcome: string;
  lastChecked: string;
  notes: string;
};

export type OutreachContactSummary = {
  lane: "recruiter" | "engineer";
  name: string;
  profile: string;
  position: string;
  approval: string;
  outcome: string;
  route: string;
  connectionNote: string;
  lastChecked: string;
  notes: string;
};

export type OutreachRoleBucket = {
  key: string;
  company: string;
  role: string;
  fitScore: number;
  status: string;
  count: number;
  states: string[];
  contacts: OutreachContactSummary[];
};

export type OutreachBuckets = {
  recruiter: {
    activeRoles: OutreachRoleBucket[];
    sentRoles: OutreachRoleBucket[];
  };
  engineer: {
    activeRoles: OutreachRoleBucket[];
    sentRoles: OutreachRoleBucket[];
  };
};

export type TrackerData = {
  generatedAt: string;
  sourceFiles: {
    applications: string;
    outreach: string;
    intake?: string;
    recruiterBatch?: string;
    engineerBatch?: string;
  };
  stats: {
    kpis: Record<string, number>;
    statusCounts: CountDatum[];
    sourceCounts: CountDatum[];
    locationCounts: CountDatum[];
    roleCounts: CountDatum[];
    fitCounts: Array<{ score: string; count: number }>;
    targetCounts: CountDatum[];
    emailCounts: CountDatum[];
    intakeStatusCounts?: CountDatum[];
    intakeSourceCounts?: CountDatum[];
    timeline: Array<Record<string, number | string>>;
    topCompanies: Array<{ company: string; roles: number; avgFit: number; bestFit: number }>;
    outreachGaps: Array<{
      company: string;
      role: string;
      fitScore: number;
      status: string;
      prospectCount: number;
      readyEmails: number;
      jobLink: string;
    }>;
    recruiterBatch?: {
      total: number;
      labeled: number;
      approved: number;
      sent: number;
      notReachedOut: number;
      needsRecruiter: number;
    };
    engineerBatch?: {
      total: number;
      labeled: number;
      approved: number;
      sent: number;
      notReachedOut: number;
      needsEngineer: number;
    };
  };
  applications: Application[];
  jobIntake?: JobIntake[];
  outreachQueue: OutreachQueue[];
  prospects: Prospect[];
  recruiterBatch?: RecruiterBatch[];
  engineerBatch?: EngineerBatch[];
  outreachBuckets?: OutreachBuckets;
};
