# Batch State Contract Ver2

Use `/tmp/linkedin_batch_drain_codex_ver2_state.json` as the durable source of
truth. Write atomically: read the latest state, update only the relevant
item/search/batch fields, write a temp file in the same directory, then rename.

`/tmp/linkedin_batch_drain_codex_ver2_monitor.md` is the human-readable resume
point after context compaction. It must match state.

## Top-Level Fields

```json
{
  "schemaVersion": 1,
  "runPolicy": {
    "mode": "linkedin-batch-drain-codex",
    "ver2": true,
    "batchFirst": true,
    "stateFile": "/tmp/linkedin_batch_drain_codex_ver2_state.json",
    "lockFile": "/tmp/linkedin_batch_drain_codex_ver2_worker.lock",
    "outputDir": "/tmp/linkedin_batch_drain_codex_ver2_outputs",
    "descriptionDir": "/tmp/linkedin_batch_drain_codex_ver2_descriptions",
    "workerResultDir": "/tmp/linkedin_batch_drain_codex_ver2_worker_results",
    "monitorFile": "/tmp/linkedin_batch_drain_codex_ver2_monitor.md",
    "batchTarget": 40,
    "maxJobs": 40
  },
  "search": {
    "searchUrl": "",
    "currentResultIndex": 0,
    "lastJobUrl": "",
    "scrollCheckpoint": "",
    "stopRequested": false,
    "finalSearchSaturation": false,
    "saturationReason": "",
    "visitedJobUrls": [],
    "skippedJobUrls": []
  },
  "batch": {
    "phase": "discovering | tailoring | applying | complete | blocked",
    "usableTarget": 40,
    "usableKeys": [],
    "atsOrder": [
      "linkedin_easy_apply",
      "ashby",
      "greenhouse",
      "lever",
      "smartrecruiters",
      "icims",
      "custom",
      "workday",
      "unknown"
    ]
  },
  "items": []
}
```

## Item Fields

```json
{
  "key": "linkedin-<postingKey>",
  "postingKey": "",
  "company": "",
  "role": "",
  "location": "",
  "compensation": "",
  "jobUrl": "",
  "externalApplyUrl": "",
  "atsBucket": "ashby",
  "jobDescriptionPath": "",
  "fitScore": 0,
  "state": "discovered | tailor_needed | tailoring | apply_needed | applying | submitted | manual | duplicate | already_applied | archived",
  "resumeFolder": "",
  "resumePdf": "",
  "trackerStatus": "",
  "result": "",
  "blocker": "",
  "confirmationEvidence": "",
  "manualHandoffPath": "",
  "leaseOwner": "",
  "leasePid": "",
  "updatedAt": ""
}
```

## Worker Result Fields

Application browser workers write one result file and exit:

```json
{
  "postingKey": "",
  "company": "",
  "role": "",
  "status": "submitted | manual_blocker | already_applied | duplicate | archived | child_browser_blocker | systemic_blocker",
  "resumePdf": "",
  "jobUrl": "",
  "applyUrl": "",
  "confirmationEvidence": "",
  "blocker": "",
  "filledAnswers": [],
  "frqDrafts": [],
  "tabsKept": [],
  "trackerRecommendation": "",
  "finishedAt": ""
}
```

## State Rules

- `usableKeys` contains only postings worth pursuing. Do not include duplicate,
  already-applied, or archived items.
- In batch-first mode, do not start tailoring or applying until
  `usableKeys.length >= batch.usableTarget` or final search-space saturation is
  recorded after all configured expansions have been exhausted.
- Final saturation requires `search.stopRequested: true`,
  `search.finalSearchSaturation: true`, and a precise `search.saturationReason`
  with scanned, matched, duplicate/already-applied, archived, and usable counts.
- `tailoring` and `applying` are leases. Include `leaseOwner` and `leasePid`
  when a separate worker is active; clear them on terminal state.
- A submitted item must include `confirmationEvidence`.
- A manual item must include `blocker` and `manualHandoffPath`.
- A child Chrome bridge or upload permission limitation is not a row-level
  manual blocker until inline conductor fallback has also failed.
- An archived item must include a concrete reason in `result`.
- Do not mark `batch.phase: complete` until every `usableKeys` item is
  terminal and the tracker/cache have been reconciled.
