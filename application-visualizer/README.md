# Application Visualizer

Run `npm run dev` to refresh the generated data and open the Vite dashboard locally.

The Pipeline tab shows the last 7 days of intake and application health. Stale timestamps mean the matching automation has not run recently. Rebuild its data with:

```bash
python3 ../scripts/build_pipeline_metrics.py
```
