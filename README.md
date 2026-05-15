# Estonia AI exposure pipeline

Mapping ~640k Estonian workers by region × occupation × AI exposure, to inform the National AI Programme's skilling allocation.

The pipeline pulls real employment data from Statistics Estonia (REL2021 Census), attaches AI exposure scores derived from Felten AIOE + Anthropic Economic Index, and produces both static PNG charts and an interactive Streamlit dashboard.

See [`output/README.md`](output/README.md) for the v2 architecture, model/scenario registry, and chart-by-chart documentation.

See [`data-inventory-and-approach.md`](data-inventory-and-approach.md) for the methodology brief (data sources, taxonomy crosswalks, two-axis Opportunity / Risk framework).

## Quick start

```bash
pip install -r requirements.txt

python3 src/fetch_rl21154.py        # idempotent; ~1 min on first run
python3 src/fetch_ai_scores.py       # auto-downloads heavy AEI raw file (~44 MB) if missing
python3 src/build_weights.py
python3 src/build_matrix.py
python3 src/visualize.py             # 8 PNG charts → output/charts/<model>_<scenario>/

streamlit run src/dashboard.py       # interactive explorer at http://localhost:8501
```

## Architecture

v2 organises everything around three first-class dimensions:

- **Scores** — long-format AI-exposure scores per `(model, taxonomy, code, metric)`
- **Weights** — long-format employment headcounts per `(scenario, taxonomy, code, location)`
- **Crosswalks** — optional bridges between taxonomies when scores and weights don't share one

A matrix file is produced per `(model, scenario)` combination, with output charts in a matching subdirectory. Adding a new model, scenario, or taxonomy is a drop-in: write an aggregator/builder function, no schema changes.

Currently registered: `felten_aei × 2021_census × isco2`. Future PRs can add ILO WP140, OSKA forecasts, Claude.ai consumer data, etc. — see the registry markdown files under `data/processed/scores/MODELS.md` and `data/processed/weights/SCENARIOS.md`.

## Data sources

- **Statistics Estonia REL2021 Census** — register-based; `RL21154` table for ISCO × location × sex.
- **Felten et al. AIOE** — github.com/AIOE-Data/AIOE, Appendix A (SOC-6 exposure scores).
- **Anthropic Economic Index** — huggingface.co/datasets/Anthropic/EconomicIndex, March 2026 release (O*NET task × collaboration patterns).
- **BLS SOC ↔ ISCO crosswalk** — Wayback-Machine-cached 2010 SOC vs ISCO-08.
- **EHAK administrative geometries** — github.com/buildig/EHAK.

## Deployment

Streamlit dashboard deploys to Streamlit Community Cloud directly from this repo. See [`output/README.md` § Dashboard](output/README.md#dashboard) for instructions.
