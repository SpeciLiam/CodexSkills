# Housing Visualizer

The dashboard is a derived view of `housing-trackers/listings.md`. `npm run dev`
and `npm run build` first run `export_housing_data.py`, so a deployment cannot
silently reuse an older checked-in JSON snapshot.

The header distinguishes dashboard build time from `pipelineRunAt` and renders
the per-source results in `housing-trackers/run-health.json`.

## Local commands

```bash
npm run dev
npm run build
```

## Remote-write safety

Production builds keep anonymous Supabase profile/mark sync and the dashboard
Agent inbox disabled by default. Local development keeps them available.

- `VITE_ENABLE_REMOTE_SYNC=true` enables remote profile/mark reads and writes.
- `VITE_ENABLE_REMOTE_AGENT=true` enables the Agent panel.

Do not enable either flag on a public deployment until Supabase Auth, owner-scoped
RLS, and authenticated server-side mutation endpoints are in place. Google-backed
`/api/geocode` and `/api/commute` should likewise sit behind Vercel deployment
protection or an authenticated/rate-limited gateway when a paid Maps key is set.
They fail closed unless the server-side `HOUSING_ENABLE_GOOGLE_PROXY=true` flag is
set; enable it only after the deployment is private/protected.
