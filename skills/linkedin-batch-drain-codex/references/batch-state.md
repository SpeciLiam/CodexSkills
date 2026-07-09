# Batch State Contract

Use `/tmp/linkedin_batch_drain_codex_state.json` as the durable source of truth.
Write atomically: read the latest state, update only the relevant item/search
fields, write a temp file in the same directory, then rename.

## Top-Level Fields

```json
{
  "schema": "linkedin-batch-drain-codex/v1",
  "runPolicy": {
    "stateFile": "/tmp/linkedin_batch_drain_codex_state.json",
    "lockFile": "/tmp/linkedin_batch_drain_codex_worker.lock",
    "outputDir": "/tmp/linkedin_batch_drain_codex_outputs",
    "descriptionDir": "/tmp/linkedin_batch_drain_codex_descriptions",
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
  "updatedAt": ""
}
```

## State Rules

- `usableKeys` contains only postings worth pursuing. Do not include duplicate,
  already-applied, or archived items. If final search saturation leaves fewer
  than `batch.usableTarget` usable postings, record the exact scanned counts
  and exhausted search/freshness expansions in `search.saturationReason`.
- In batch-first mode, do not start tailoring or applying until
  `usableKeys.length >= batch.usableTarget` or final search-space saturation is
  recorded after all configured expansions have been exhausted. Final
  saturation requires both `search.stopRequested: true` and
  `search.finalSearchSaturation: true`.
- `tailoring` and `applying` are leases. Include `leaseOwner`, `leasePid` when
  a separate worker is active, and clear them on terminal state.
- A submitted item must include `confirmationEvidence`.
- A manual item must include `blocker` and `manualHandoffPath`.
- An archived item must include a concrete reason in `result`.
- Do not mark `batch.phase: complete` until every `usableKeys` item is terminal
  and the tracker/cache have been reconciled.
