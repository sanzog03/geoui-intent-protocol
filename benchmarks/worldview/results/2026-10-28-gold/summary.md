# Benchmark summary — 2026-10-28-gold

Reference agent for ratios: `geoui`. Scores are deepeval metric scores (pass ✓ / fail ✗ at the metric's threshold); tokens are cache-adjusted per prompts.md (input − cache_read + 0.1·cache_read + output).

| scenario | agent | Success | Completion | Tool eff | Time eff | Token eff | Relevancy | turns | tool calls | s | tokens | cost $ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| core-1-single-render | geoui | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1 | 2 | 24 | 14.0k | 0.032 |
| core-1-single-render | vlm | 1.00 ✓ | 1.00 ✓ | 0.72 ✓ | 0.13 ✗ | 0.14 ✗ | 1.00 ✓ | 1 | 47 | 461 | 147.2k | 0.561 |
|  | **vlm/geoui** |  |  |  |  |  |  |  | 23.5× | 19.3× | 10.5× |  |
| core-2-date-change | geoui | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 2 | 6 | 49 | 18.2k | 0.055 |
| core-2-date-change | vlm | 1.00 ✓ | 1.00 ✓ | 0.78 ✓ | 0.48 ✗ | 0.39 ✗ | 1.00 ✓ | 2 | 32 | 252 | 102.6k | 0.303 |
|  | **vlm/geoui** |  |  |  |  |  |  |  | 5.3× | 5.2× | 5.6× |  |
| core-3-pan | geoui | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1 | 2 | 16 | 6.2k | 0.018 |
| core-3-pan | vlm | 1.00 ✓ | 1.00 ✓ | 0.53 ✗ | 0.17 ✗ | 0.11 ✗ | 1.00 ✓ | 1 | 86 | 355 | 178.4k | 0.520 |
|  | **vlm/geoui** |  |  |  |  |  |  |  | 43.0× | 22.6× | 28.8× |  |
| core-4-compare | geoui | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1 | 3 | 20 | 8.4k | 0.027 |
| core-4-compare | vlm | 0.00 ✗ | 0.00 ✗ | 0.68 ✗ | 0.07 ✗ | 0.01 ✗ | 0.00 ✗ | 1 | 84 | 814 | 1967.5k | 0.000 |
|  | **vlm/geoui** |  |  |  |  |  |  |  | 28.0× | 39.9× | 234.5× |  |
| core-5-chart | geoui | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1 | 3 | 28 | 9.6k | 0.036 |
| core-5-chart | vlm | 0.00 ✗ | 0.00 ✗ | 0.57 ✗ | 0.07 ✗ | 0.01 ✗ | 0.00 ✗ | 1 | 62 | 818 | 2028.0k | 0.000 |
|  | **vlm/geoui** |  |  |  |  |  |  |  | 20.7× | 28.7× | 210.6× |  |
| core-6-multilayer | geoui | 1.00 ✓ | 0.00 ✗ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 1 | 2 | 21 | 6.8k | 0.025 |
| core-6-multilayer | vlm | 0.00 ✗ | 0.00 ✗ | 0.64 ✗ | 0.06 ✗ | 0.01 ✗ | 0.00 ✗ | 1 | 52 | 933 | 1510.8k | 0.000 |
|  | **vlm/geoui** |  |  |  |  |  |  |  | 26.0× | 45.4× | 220.9× |  |
| workflow-a-wildfire | geoui | 0.69 ✗ | 1.00 ✓ | 0.85 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 5 | 20 | 209 | 75.6k | 0.275 |
| workflow-a-wildfire | vlm | 0.38 ✗ | 0.70 ✓ | 0.62 ✗ | 0.12 ✗ | 0.01 ✗ | 0.60 ✗ | 5 | 267 | 2438 | 12644.7k | 1.164 |
|  | **vlm/geoui** |  |  |  |  |  |  |  | 13.3× | 11.7× | 167.3× |  |
| workflow-b-saharan-dust | geoui | 0.56 ✗ | 1.00 ✓ | 0.88 ✓ | 1.00 ✓ | 1.00 ✓ | 1.00 ✓ | 5 | 24 | 217 | 89.7k | 0.313 |
| workflow-b-saharan-dust | vlm | 0.67 ✗ | 0.78 ✓ | 0.59 ✗ | 0.21 ✗ | 0.02 ✗ | 0.80 ✓ | 5 | 187 | 1432 | 4747.2k | 1.857 |
|  | **vlm/geoui** |  |  |  |  |  |  |  | 7.8× | 6.6× | 52.9× |  |

## Per-agent totals

| agent | conversations | turns | error turns | tool calls | s | tokens | cost $ | Success pass | Completion pass | Tool eff pass | Time eff pass | Token eff pass | Relevancy pass | Success mean | Completion mean | Tool eff mean | Time eff mean | Token eff mean | Relevancy mean |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| geoui | 8 | 17 | 0 | 62 | 584 | 228.5k | 0.782 | 0.75 | 0.88 | 1.00 | 1.00 | 1.00 | 1.00 | 0.91 | 0.88 | 0.97 | 1.00 | 1.00 | 1.00 |
| vlm | 8 | 17 | 6 | 817 | 7504 | 23326.4k | 4.405 | 0.38 | 0.62 | 0.25 | 0.00 | 0.00 | 0.50 | 0.51 | 0.56 | 0.64 | 0.16 | 0.09 | 0.55 |
