import type { OutreachLane } from "./types";

export type NoteAnalysisInput = {
  contactName: string;
  lane: OutreachLane;
  postingContext: {
    company?: string;
    role?: string;
    notes?: string;
    position?: string;
  };
};

export type NoteQualityFlag = {
  id: "length" | "personal" | "lane";
  label: string;
  passed: boolean;
};

const ROLE_KEYWORDS = [
  "backend",
  "frontend",
  "full stack",
  "full-stack",
  "platform",
  "infrastructure",
  "data",
  "ai",
  "ml",
  "machine learning",
  "product",
  "cloud",
  "security",
  "mobile",
  "new grad",
  "software",
  "engineer",
];

const ALUMNI_RE = /\b(alumni|alum|uga|georgia|university of georgia|dawgs?)\b/i;
const PROJECT_RE = /\b(team|project|platform|product|infra|infrastructure|backend|frontend|full.stack|api|cloud|data|ai|ml|security)\b/i;

function words(value: string) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9+\s-]/g, " ")
    .split(/\s+/)
    .filter((word) => word.length > 2);
}

function firstName(name: string) {
  return words(name)[0] || "";
}

function roleKeywordMatch(note: string, role: string) {
  const roleText = role.toLowerCase();
  const noteText = note.toLowerCase();
  const directRoleWords = words(role).filter((word) => !["software", "engineer", "role"].includes(word));
  return (
    directRoleWords.some((word) => noteText.includes(word)) ||
    ROLE_KEYWORDS.some((keyword) => roleText.includes(keyword) && noteText.includes(keyword))
  );
}

export function analyzeConnectionNote(note: string, input: NoteAnalysisInput): NoteQualityFlag[] {
  const normalizedNote = note.trim();
  const noteText = normalizedNote.toLowerCase();
  const first = firstName(input.contactName);
  const role = input.postingContext.role || "";
  const notes = input.postingContext.notes || "";
  const position = input.postingContext.position || "";
  const personal =
    Boolean(first && noteText.includes(first)) ||
    ALUMNI_RE.test(normalizedNote) ||
    PROJECT_RE.test(normalizedNote) ||
    words(position).some((word) => word.length > 4 && noteText.includes(word));
  const laneHook =
    input.lane === "engineer"
      ? roleKeywordMatch(normalizedNote, role) || ALUMNI_RE.test(normalizedNote) || PROJECT_RE.test(normalizedNote)
      : roleKeywordMatch(normalizedNote, role) || Boolean(notes && words(notes).some((word) => word.length > 5 && noteText.includes(word)));

  return [
    { id: "length", label: "<300 chars", passed: normalizedNote.length > 0 && normalizedNote.length <= 300 },
    { id: "personal", label: "Personal hook", passed: personal },
    { id: "lane", label: input.lane === "engineer" ? "Engineer hook" : "Recruiter hook", passed: laneHook },
  ];
}
