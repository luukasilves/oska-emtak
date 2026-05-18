# Töötukassa Tööjõuvajaduse Baromeeter — staged raw

Semi-annual qualitative forecast at ISCO-08 4-digit × all 15 maakonnad,
published by Eesti Töötukassa. Snapshot of `periodId=396` (2026 H1) pulled
on 2026-05-18 via headless Playwright against the SPA at
https://www.tootukassa.ee/et/baromeeter/tabel.

## Files
- `baromeeter_396_LABOUR_BALANCE.xlsx` — supply-vs-demand balance per cell.
- `baromeeter_396_LABOUR_DEMAND.xlsx` — 12-month demand change per cell.
- `barometer_long.csv` — combined parse, one row per (period × ratingType × ISCO-4 × location):
  columns `period_id, rating_type, isco4, occupation_et, location_name, indicator`.
- `captured_endpoints.json` — backend calls observed during the scrape; for the next
  person attempting to reproduce.

## Indicator encoding (in `indicator` column)
- 1 = largeDeficit  (++)  — strong shortage / strong demand growth
- 2 = deficit       (+)   — shortage / demand growth
- 3 = stable/balance (=)
- 4 = surplus       (–)
- 5 = largeSurplus  (––)

Blanks omitted from the long CSV. Distribution in 396: ~85% stable, ~9% surplus,
~4% deficit, ~1% large-surplus, <0.1% large-deficit.

## Access pattern
Direct URL: `https://www.tootukassa.ee/etootukassa/baromeeter/table/excel?periodId=X&ratingType=Y`
where `ratingType ∈ {LABOUR_BALANCE, LABOUR_DEMAND}`. Requires an authenticated
browser session — see `scripts/scrape_barometer.py` (if present) or load the
table page once via Playwright with `accept_downloads=True` and click "Salvesta .XLS failina".

## Status
Raw data staged. NOT yet wired into the model/scenario registry. The barometer
is a *forecast* (qualitative ordinal demand signal), not a *stock* (headcount).
The right architectural fit is either:
1. New metric (`demand_indicator`) on existing scenarios — extends the `metric`
   controlled vocab in src/build_matrix.py;
2. New axis alongside (model, scenario, taxonomy) — needs schema design;
3. Separate dashboard tab fed directly from `barometer_long.csv`.

Pick the architecture before adding a builder; flagged as Phase 4 of the
ISCO-4 build-out plan.
