# palgad.stat.ee — ISCO-4 employment headcount scrape

Statistics Estonia's salary application (https://palgad.stat.ee/) publishes
administrative employment data at ISCO-4 × maakond × quarterly granularity,
sourced from the Estonian Employment Register (TÖR) and tax declarations.
It is the **only public Estonian dataset that breaks employment down at
the 4-digit ISCO occupation level** — PXWeb (RL21154, TT2109, TT2419, etc.)
caps at ~ISCO-2 (51 categories).

## Why we scrape it

- Stat.ee does not expose the data through PXWeb or any documented JSON API.
- The application is a Drupal SPA; data is delivered to chart components
  through an undocumented endpoint pattern.
- We reverse-engineered it to feed `scenario=2025q4_palgad_isco4` in the
  Estonia AI exposure pipeline.

## URL pattern (reverse-engineered 2026-05-18)

The "workers total" chart is served as a Drupal page (HTML) at:

```
GET /api/charts/workers_total_section/<isco4>/<year>/<quarter>/<salary>/<county>/<age>/<gender>
```

| Slot | Values | Meaning |
|---|---|---|
| isco4 | `all` or 4-digit (e.g. `1211`) | OK occupation group / ametirühm |
| year | `2021..2025` | Calendar year |
| quarter | `Q1` `Q2` `Q3` `Q4` | Quarter |
| salary | `average` `median` | Salary statistic basis (ignored for headcount) |
| county | `all` `harju` `hiiu` `ida_viru` `jogeva` `jarva` `laane` `laane_viru` `polva` `parnu` `rapla` `saare` `tartu` `valga` `viljandi` `voru` | Maakond filter |
| age | `all` `0-24` `25-34` `35-44` `45-54` `55-64` `65+` | Age group |
| gender | `all` `M` `N` | Sex |

Response is HTML containing a `<table class="workers_total--table">` with
`<th>Mehed/Naised</th><td>count</td>` rows. **Cells with fewer than 20
persons are suppressed by stat.ee** — those responses have no table.

## Taxonomy source

The ISCO-4 codes the system tracks are embedded in the front-page DOM as a
hidden `<div id="edit-occupations-overlay">` — a 650 KB chunk containing
the full hierarchy of 428 ISCO-4 groups → 2,744 leaf occupations (8-digit
Estonian extension). We extract this at scrape time.

Two-step hierarchy per occupation:
- `<a data-parent-id="1111">Seadusandjad</a>` — the ISCO-4 group label
- `<a data-parent-id="1111" data-id="11110001">Minister</a>` — leaf

## Files in this directory

| File | Contents |
|---|---|
| `occupations_overlay.html` | Cached overlay HTML (taxonomy source) |
| `taxonomy_isco4.csv` | 428 rows: `isco4, name_et` |
| `taxonomy_leaves.csv` | 2,744 rows: `isco4, leaf_id, leaf_name_et` |
| `workers_raw/<isco4>_<county>.html` | Per-cell raw HTML response (cache) |
| `workers_long.csv` | Parsed long format: `isco4, name_et, county, county_name, gender, count, source_url` |

## How to re-run

```bash
pip install playwright
python -m playwright install chromium
python scripts/scrape_palgad_stat_ee.py --counties=all --year=2025 --quarter=Q4
# or for full national + 15 maakonnad:
python scripts/scrape_palgad_stat_ee.py --counties=each --year=2025 --quarter=Q4
```

The script caches per-cell HTML under `workers_raw/`; re-runs only fetch
missing cells. Default delay is 1.0 s between requests; lower with `--delay`
only if you have a reason.

## Coverage

The current scrape covers **2025 Q4** for **national + all 15 maakonnad**
(16 locations × 428 ISCO-4 codes = 6,848 cells fetched). The `workers_raw/`
per-cell HTML cache is gitignored (~150 MB); the canonical artefact is
`workers_long.csv` (7,951 rows).

## Quality caveats

- **Suppression**: cells with <20 persons return no table. Actual observed
  suppression rates per maakond (2025 Q4, out of 390 ISCO-4 codes that have
  any data nationally):

  | Maakond | Suppression rate | Surviving codes |
  |---|---|---|
  | Kogu Eesti (national) | 1% | 385 |
  | Harju | 7% | 362 |
  | Tartu | 31% | 270 |
  | Ida-Viru | 51% | 193 |
  | Pärnu | 52% | 187 |
  | Lääne-Viru | 66% | 133 |
  | Viljandi | 68% | 125 |
  | Võru | 74% | 100 |
  | Saare | 75% | 97 |
  | Rapla | 77% | 89 |
  | Järva | 80% | 79 |
  | Jõgeva | 82% | 69 |
  | Põlva | 84% | 62 |
  | Valga | 84% | 63 |
  | Lääne | 85% | 59 |
  | Hiiu | 95% | 18 |

  Aggregating to national eliminates almost all suppression. Hiiu and
  Saare retain so few codes that any per-maakond ISCO-4 analysis there
  must lean on coarser groupings (ISCO-1 or ISCO-2 rollups).
- **Single quarter snapshot**: 2025 Q4 is the most recent at scrape time.
  Re-run with `--year=Y --quarter=Q` for any quarter 2021Q1 onward.
- **Sex coverage**: cells are published as M / F separately. We sum to total
  in `workers_long.csv`. Per-sex retention is preserved in the raw HTML.
- **Source date**: a `source_url` column is included in `workers_long.csv`
  for each row so the scrape is reproducible.
- **Comparison with REL2021**: palgad.stat.ee covers active-employee
  population from TÖR + tax declarations, which differs slightly from the
  REL2021 register-based census definition. Differences of ~5–10% on
  national totals are expected.
