# Benchmark summary — 2026-10-28-gold-geoui-predeclared

Reference agent for ratios: `geoui`. Scores are deepeval metric scores (pass ✓ / fail ✗ at the metric's threshold); tokens are cache-adjusted (input − cache_read + 0.1·cache_read + output).

| scenario | agent | Success | Completion | Tool eff | Time eff | Token eff | Relevancy | turns | tool calls | s | tokens | cost $ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| core-1-single-render | geoui | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1 | 2 | 44 | 14.5k | 0.033 |
| core-2-date-change | geoui | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 2 | 6 | 41 | 18.4k | 0.054 |
| core-3-pan | geoui | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1 | 2 | 23 | 7.0k | 0.024 |
| core-4-compare | geoui | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1 | 2 | 25 | 7.3k | 0.032 |
| core-5-chart | geoui | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1 | 3 | 29 | 11.3k | 0.040 |
| core-6-multilayer | geoui | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1 | 2 | 21 | 7.2k | 0.025 |
| workflow-a-wildfire | geoui | 0.77 ✗ | 1.00 ✓ | 0.84 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 5 | 19 | 170 | 74.2k | 0.250 |
| workflow-b-saharan-dust | geoui | 0.56 ✗ | 1.00 ✓ | 0.84 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 5 | 19 | 156 | 69.0k | 0.228 |

## Per-agent totals

| agent | conversations | turns | error turns | tool calls | s | tokens | cost $ | Success pass | Completion pass | Tool eff pass | Time eff pass | Token eff pass | Relevancy pass | Success mean | Completion mean | Tool eff mean | Time eff mean | Token eff mean | Relevancy mean |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| geoui | 8 | 17 | 0 | 55 | 510 | 209.0k | 0.686 | 0.75 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.92 | 1.00 | 0.96 | 1.00 | 1.00 | 1.00 |
