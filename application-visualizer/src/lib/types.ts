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

export type TrackerData = {
  generatedAt: string;
  sourceFiles: {
    applications: string;
    outreach: string;
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
  };
  applications: Application[];
  outreachQueue: OutreachQueue[];
  prospects: Prospect[];
};
