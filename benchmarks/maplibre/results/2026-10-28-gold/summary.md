# Benchmark summary — 2026-10-28-gold

Reference agent for ratios: `geoui`. Scores are deepeval metric scores (pass ✓ / fail ✗ at the metric's threshold); tokens are cache-adjusted (input − cache_read + 0.1·cache_read + output).

| scenario | agent | Success | Completion | Tool eff | Time eff | Token eff | Relevancy | turns | tool calls | s | tokens | cost $ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| core-1-single-render | geoui | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1 | 2 | 9 | 6.9k | 0.017 |
| core-2-date-change | geoui | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 2 | 4 | 14 | 8.9k | 0.023 |
| core-3-pan | geoui | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1 | 3 | 13 | 7.3k | 0.020 |
| core-4-compare | geoui | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1 | 3 | 13 | 7.6k | 0.022 |
| core-6-multilayer | geoui | 1.00 ✓ | 0.00 ✗ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1 | 2 | 9 | 6.7k | 0.017 |
| workflow-a-wildfire | geoui | 1.00 ✓ | 1.00 ✓ | 0.67 ✗ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 4 | 9 | 41 | 21.4k | 0.064 |
| workflow-b-saharan-dust | geoui | 1.00 ✓ | 1.00 ✓ | 0.75 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 4 | 8 | 32 | 18.1k | 0.053 |

## Per-agent totals

| agent | conversations | turns | error turns | tool calls | s | tokens | cost $ | Success pass | Completion pass | Tool eff pass | Time eff pass | Token eff pass | Relevancy pass | Success mean | Completion mean | Tool eff mean | Time eff mean | Token eff mean | Relevancy mean |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| geoui | 7 | 14 | 0 | 31 | 131 | 76.9k | 0.216 | 1.00 | 0.86 | 0.86 | 1.00 | 1.00 | 1.00 | 1.00 | 0.86 | 0.92 | 1.00 | 1.00 | 1.00 |
