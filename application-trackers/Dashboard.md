# Application Dashboard

> Requires the **Dataview** community plugin.

---

## Top by Fit Score

```dataviewjs
const COLS = ["Company","Role","Applied","Status","Fit Score","Reach Out","Company Resume","Referral","Date Added","Location","Source","Job Link","Posting Key","Resume Folder","Resume PDF","Notes"];

const content = await dv.io.load("application-trackers/applications.md");
const lines = content.split("\n");
const headerLine = lines.find(l => l.startsWith("| ") && l.includes("Company") && l.includes("Fit Score"));
if (!headerLine) { dv.paragraph("⚠️ Could not find tracker table."); return; }
const headerIndex = lines.indexOf(headerLine);
const columns = headerLine.split("|").map(c => c.trim()).filter(Boolean);

const rows = lines
  .slice(headerIndex + 2)
  .filter(l => l.startsWith("| "))
  .map(l => {
    const cells = l.split("|").map(c => c.trim()).filter((_, i, a) => i > 0 && i < a.length);
    const obj = {};
    columns.forEach((col, i) => { obj[col] = (cells[i] || "").trim(); });
    return obj;
  })
  .filter(r => r["Company"]);

const sorted = [...rows].sort((a, b) => (parseFloat(b["Fit Score"]) || 0) - (parseFloat(a["Fit Score"]) || 0));

dv.paragraph(`${sorted.length} total — sorted by Fit Score ↓`);
dv.table(COLS, sorted.map(r => COLS.map(c => r[c] || "")));
```

---

## Most Recent

```dataviewjs
const COLS = ["Company","Role","Applied","Status","Fit Score","Reach Out","Company Resume","Referral","Date Added","Location","Source","Job Link","Posting Key","Resume Folder","Resume PDF","Notes"];

const content = await dv.io.load("application-trackers/applications.md");
const lines = content.split("\n");
const headerLine = lines.find(l => l.startsWith("| ") && l.includes("Company") && l.includes("Date Added"));
if (!headerLine) { dv.paragraph("⚠️ Could not find tracker table."); return; }
const headerIndex = lines.indexOf(headerLine);
const columns = headerLine.split("|").map(c => c.trim()).filter(Boolean);

const rows = lines
  .slice(headerIndex + 2)
  .filter(l => l.startsWith("| "))
  .map(l => {
    const cells = l.split("|").map(c => c.trim()).filter((_, i, a) => i > 0 && i < a.length);
    const obj = {};
    columns.forEach((col, i) => { obj[col] = (cells[i] || "").trim(); });
    return obj;
  })
  .filter(r => r["Company"]);

const sorted = [...rows].sort((a, b) => (b["Date Added"] || "").localeCompare(a["Date Added"] || ""));

dv.paragraph(`${sorted.length} total — sorted by Date Added ↓`);
dv.table(COLS, sorted.map(r => COLS.map(c => r[c] || "")));
```

---

## Applied & Active

```dataviewjs
const COLS = ["Company","Role","Applied","Status","Fit Score","Reach Out","Company Resume","Referral","Date Added","Location","Source","Job Link","Posting Key","Resume Folder","Resume PDF","Notes"];

const content = await dv.io.load("application-trackers/applications.md");
const lines = content.split("\n");
const headerLine = lines.find(l => l.startsWith("| ") && l.includes("Company") && l.includes("Status"));
if (!headerLine) { dv.paragraph("⚠️ Could not find tracker table."); return; }
const headerIndex = lines.indexOf(headerLine);
const columns = headerLine.split("|").map(c => c.trim()).filter(Boolean);

const rows = lines
  .slice(headerIndex + 2)
  .filter(l => l.startsWith("| "))
  .map(l => {
    const cells = l.split("|").map(c => c.trim()).filter((_, i, a) => i > 0 && i < a.length);
    const obj = {};
    columns.forEach((col, i) => { obj[col] = (cells[i] || "").trim(); });
    return obj;
  })
  .filter(r => r["Company"]);

const active = rows
  .filter(r => {
    const s = (r["Status"] || "").toLowerCase();
    return !["rejected","archived"].includes(s) && (r["Applied"] || "").toLowerCase() === "yes";
  })
  .sort((a, b) => (parseFloat(b["Fit Score"]) || 0) - (parseFloat(a["Fit Score"]) || 0));

dv.paragraph(`${active.length} applied & active — sorted by Fit Score ↓`);
dv.table(COLS, active.map(r => COLS.map(c => r[c] || "")));
```
