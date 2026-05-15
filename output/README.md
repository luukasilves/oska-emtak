# Estonia AI exposure — v2 outputs

Eight static charts per (AI-exposure model × employment-weighting scenario) combination, mapping AI exposure / opportunity / risk across Estonia.

## v2 architecture

The pipeline is now organised around three first-class dimensions:

- **Scores** — long-format AI-exposure scores per `(model, taxonomy, code, metric)`.
- **Weights** — long-format employment headcounts per `(scenario, taxonomy, code, location)`.
- **Crosswalks** — optional bridges between taxonomies for when a model and scenario don't share one.

A matrix file is produced per `(model, scenario)` combination, with output charts in a matching subdirectory.

### Currently registered

| dimension | id | taxonomy | source |
|---|---|---|---|
| model | `felten_aei` | `isco2` | Felten AIOE × Anthropic AEI March 2026 |
| scenario | `2021_census` | `isco2` | REL2021 RL21154 raw counts |
| crosswalks | (none) | — | scaffolding only; the only registered model and scenario share `taxonomy=isco2` |

### Future PRs can add

- ILO WP140 as a second `model` (likely `taxonomy=isco4`).
- OSKA-projected employment as a second `scenario` (likely `taxonomy=oska69`).
- Crosswalks between taxonomies (e.g. `isco4_to_isco2.csv`, `oska69_to_isco2.csv`).
- **Firm-side companion matrix** at `taxonomy=emtak` (firm counts × omavalitsus). See "EMTAK firm-level extension (planned)" below — this is a parallel deliverable, not a new model/scenario in the v2 pipeline.

No code changes needed beyond registering the new aggregator/builder; matrices/summaries/charts are produced automatically for every viable combo.

## Dashboard

Interactive Streamlit explorer over the v2 outputs.

### Run locally

```bash
cd ~/code/oska-emtak    # or wherever the repo is cloned
pip install -r requirements.txt
streamlit run src/dashboard.py
```

Opens at http://localhost:8501. The app auto-discovers `(model, scenario)` combos from `data/processed/matrices/`; currently only `felten_aei × 2021_census` is registered, but the dropdowns expand automatically as new combos are added.

### Features

- **Map tab** — Folium choropleth at maakond (15) or municipality + linnaosa (~90) granularity, colored by exposure / opportunity / risk / absolute people-affected. Click any region to see its top-N occupations broken into augmentation vs automation people.
- **Occupations tab** — National Opportunity × Risk scatter (sized by employment, colored by ISCO major group), plus top-N people-affected bar chart with augmentation/automation split.
- **AEI breakdown tab** — Per-ISCO-2 100% stacked bar of augmentation vs automation share, with explainer about Anthropic's collaboration-pattern classification and the API-vs-consumer caveat.
- **Data tab** — Filtered long-format matrix, downloadable as CSV.
- **Sidebar filters** — model, scenario, geography level, metric, ISCO 1-digit major-group filter, top-N slider.

### Deploy to Streamlit Community Cloud

The repo is already on GitHub at https://github.com/luukasilves/oska-emtak. To deploy:

1. Visit https://share.streamlit.io and sign in with GitHub.
2. Click "New app", select the `oska-emtak` repo, set the main file to `src/dashboard.py`, branch `main`.
3. Streamlit auto-installs `requirements.txt`. First deploy takes ~3 minutes.
4. On the first run, `fetch_ai_scores.ensure_aei_raw_downloaded()` re-fetches the gitignored AEI 1P-API CSV (~44 MB) from Hugging Face. Adds ~30 sec to cold start; subsequent loads are fast.

No secrets are required for the v2 baseline. If a future model variant needs an API key, add it to the Streamlit Cloud app settings under "Secrets" and read with `st.secrets["KEY_NAME"]`. See `.streamlit/secrets.toml.example` for the format.

URL pattern: `https://<your-app-name>.streamlit.app`.

The dashboard reads CSVs and GeoJSON from `data/processed/`. Those processed files are small (matrix ~700 KB, geometry ~3 MB) and committed to the repo. Heavy raw AEI inputs (~92 MB Claude.ai + ~42 MB 1P-API CSVs) are gitignored.

## Directory layout

```
data/
  raw/                        — pristine inputs, do not edit
  crosswalks/                 — inter-taxonomy bridges (only used when scores and weights differ in taxonomy)
    CROSSWALKS.md             — registry; empty for v2
  processed/
    scores/
      scores_long.csv         — all models × taxonomies, long format
      MODELS.md               — registry
    weights/
      weights_long.csv        — all scenarios × taxonomies, long format
      SCENARIOS.md            — registry
    geometry/
      estonia_municipalities_combined.geojson   — ~90-polygon combined map
    matrices/
      matrix_<model>_<scenario>.csv             — one per combo
    summaries/
      maakond_summary_<model>_<scenario>.csv    — one per combo
output/
  charts/
    <model>_<scenario>/
      01_employment_by_maakond.png … 08_municipality_people_affected.png
  README.md (this file)
src/
  common.py                   — shared constants/helpers
  fetch_rl21154.py            — Statistics Estonia PXWeb fetcher (unchanged)
  fetch_ai_scores.py          — model aggregators → scores_long.csv
  build_weights.py            — scenario builders → weights_long.csv
  build_matrix.py             — joins scores × weights → matrices/ + summaries/
  visualize.py                — iterates matrices → charts/<combo>/
```

## What's in each chart (per combo)

| File | What it shows |
|---|---|
| `01_employment_by_maakond.png` | Total employed per county (RL21154; n≈642k). Harju 312k (49%), Tartu 77k, Hiiu 4k. |
| `02_exposure_by_maakond.png` | Employment-weighted AI exposure score per county. Harju 0.61, Tartu 0.58, rest 0.46–0.51. |
| `03_opportunity_vs_risk_by_maakond.png` | Paired bars: Opportunity (augmentation) and Risk (automation) per county. Risk dominates per AEI 1P-API data. |
| `04_opportunity_risk_scatter.png` | ISCO 2-digit groups on Opportunity × Risk plane, sized by national headcount. |
| `05_top15_people_affected.png` | Top 15 occupational groups nationally by `employed × exposure`, split into augmentation/automation. |
| `06_estonia_choropleth.png` | Maakond-level 3-panel map (Exposure / Opportunity / Risk). |
| `07_estonia_municipality_choropleth.png` | Municipality + city-district 3-panel map. ~87 of 90 polygons matched. |
| `08_municipality_people_affected.png` | Absolute "people affected" (employed × exposure) per locality. Tallinn districts dominate. |

## Data sources used (felten_aei × 2021_census)

- **Estonia Census 2021** — `RL21154` (employment by ISCO occupation × county × sex) pulled from Statistics Estonia PXWeb API. 12,495 cells, register-based, no sampling error.
- **AI exposure score** — Felten et al. AIOE (github.com/AIOE-Data/AIOE), Appendix A. SOC-6 → ISCO-2 via BLS SOC-2010↔ISCO-08 crosswalk (Aug 2012, June 2015 update); simple mean per Felten convention.
- **Augmentation / automation split** — Anthropic Economic Index, March 2026 release. O*NET task × collaboration pattern data. Augmentation = task iteration + learning + validation; Automation = directive + feedback loop. Aggregated to ISCO-2 via O*NET task statements → SOC-6 → ISCO, weighted by classified observations per task.
- **Maakond geometry** — github.com/buildig/EHAK/geojson/maakond.json.
- **Municipality + linnaosa geometry** — github.com/buildig/EHAK (omavalitsus.json + asustusyksus.json with TYYP=6).

## Methodological notes

1. **Why Risk > Opportunity globally**: AEI March 2026 1P-API data shows ~80% of classified collaboration is "directive" (single-shot execution) or "feedback loop" — both classified as automation patterns by Anthropic. Augmentation patterns (task iteration, learning, validation) make up the remaining ~20%. This is API usage data, which skews more programmatic than Claude.ai conversations. A future Claude.ai-based model variant would tilt this distribution toward augmentation.

2. **Low-confidence ISCO-2 cells**: ISCO 91, 92, 93, 94, 95, 96 (Elementary occupations) and a few small groups in Agriculture/Trades have <10 matched O*NET tasks in AEI. Their augmentation/automation shares fall back to the ISCO 1-digit mean (or global mean if the 1-digit group also has no good cells), flagged `source=derived_aug_fallback` in `scores_long.csv`.

3. **ISCO 95 anomaly**: shows AIOE ≈ 1.11 (high) despite being "Street and related sales/service workers". This is an artifact of the SOC→ISCO crosswalk — some SOC codes that map to ISCO 95 happen to have high AIOE. Affects very few Estonian workers.

4. **Municipality join coverage**: 87 of 90 polygons matched. The 3 unmatched are Kohtla-Järve sub-districts (Kukruse, Oru, Sompa) whose employment data RL21154 does not publish separately.

5. **Score scale**: exposure is min-max rescaled to [0, 1] across the 40 ISCO-2 codes. Opportunity = exposure × augmentation_share. Risk = exposure × automation_share. Since aug + auto ≈ 1 after filtering, Opportunity + Risk ≈ exposure.

## How to add a new model

1. Add an aggregator function in `src/fetch_ai_scores.py` returning a long-format DataFrame with columns `model, taxonomy, code, metric, value, source, notes`.
2. Register it in the `MODELS` dict at the top of that file.
3. Re-run `python3 src/fetch_ai_scores.py`. The model's rows are appended to `scores_long.csv`.
4. If the model's taxonomy differs from any registered scenario's taxonomy, add a crosswalk under `data/crosswalks/`.
5. Re-run `python3 src/build_matrix.py` then `python3 src/visualize.py`. New matrices/summaries/charts are produced automatically.
6. Update `data/processed/scores/MODELS.md`.

## How to add a new scenario

1. Add a builder function in `src/build_weights.py` returning a long-format DataFrame.
2. Register it in the `SCENARIOS` dict.
3. Re-run `python3 src/build_weights.py`, then `build_matrix.py` and `visualize.py`.
4. Update `data/processed/weights/SCENARIOS.md`.

## How to regenerate

```bash
cd OSKA-EMTAK
python3 src/fetch_rl21154.py     # idempotent (skip if RL21154_long.csv exists)
python3 src/fetch_ai_scores.py
python3 src/build_weights.py
python3 src/build_matrix.py
python3 src/visualize.py
```

## Future model variants — Anthropic Economic Index extensions

The current `felten_aei` model uses the AEI March 2026 1P-API release's `onet_task::collaboration` facet to derive augmentation/automation shares. AEI publishes considerably more that could feed additional models or scenarios under the v2 architecture (each is a drop-in: new aggregator/builder function, no schema changes):

| Slice | What it adds | Architectural slot |
|---|---|---|
| **AEI Claude.ai consumer data** | Same release also contains `aei_raw_claude_ai_<date>.csv`. Consumer conversations tilt augmentation-heavier than the API's directive/programmatic ~80%-automation pattern. Different policy story. | Second `model`, e.g. `felten_aei_consumer`. Identical pipeline, point at the Claude.ai CSV. ~30 min. |
| **`ai_autonomy` facet** | Continuous 0–1 score per O*NET task of how autonomously AI completed it. More granular than discrete collaboration buckets. | Either refined aug/auto split inside `felten_aei`, or a parallel model `felten_aei_autonomy`. |
| **Time-savings facets** (`human_only_time` vs `human_with_ai_time`) | Per-task ratio = productivity multiplier. Could size the 100k workshop pool by expected hours saved, not just headcount. | New `metric` column on existing scores (`productivity_multiplier`). |
| **AEI usage volumes per SOC** (`onet_task_count`) | Where AI is being *adopted right now*, not where it could be. | New `scenario` (e.g. `2026_aei_observed`) that multiplies census employment by per-SOC usage share. Answers "where are the currently-AI-using workers?" |
| **Country-state geographic facet** | AEI publishes per-country usage; Estonia-specific patterns (filter `geo_id=EST` or similar). Likely small sample but Estonia-relative. | Model variant like `felten_aei_estonia`. |

Sources:
- AEI dataset: https://huggingface.co/datasets/Anthropic/EconomicIndex
- AEI March 2026 documentation: `release_2026_03_24/data_documentation.md`
- AEI Feb 2025 paper (collaboration-pattern classification): "Which Economic Tasks are Performed with AI?"

## Known limitations (v2 → future)

1. **Single model and scenario registered** — pipeline is scaffolded for more but only `felten_aei × 2021_census` is currently populated.
2. **ISCO granularity is 2-digit** because that's what RL21154 publishes. Adding ISCO-4 source data (e.g. ILO WP140) requires a crosswalk back to ISCO-2 or a scenario at finer granularity.
3. **No OSKA Demand-gap layer** — third axis from the plan; deferred.
4. **No EMTAK / firm-side overlay** — planned as a separate workstream, see next section.
5. **3 Kohtla-Järve linnaosa not displayed** (Kukruse/Oru/Sompa) — no published data in RL21154.

---

## EMTAK firm-level extension (planned)

The v2 matrix above answers *"where do AI-exposed workers live, by occupation?"* — the right denominator for **individual outreach** (training people near home). But the AI Programme will also reach workers **through firms** — sectoral associations, large-employer partnerships, HR-led rollouts. For that, you need a parallel matrix on the firm side: *"where are the firms in each industry, how big are they, who controls them?"*

This section describes that planned extension. It is **not** part of the v2 ISCO pipeline — it produces a sibling deliverable, `firm_matrix.csv`, that can later be joined with the ISCO matrix for combined allocation logic.

### Why this is a separate workstream, not a new `taxonomy` in the v2 pipeline

The ISCO pipeline measures *exposure per worker*. The firm extension measures *firm characteristics per locality × industry* — different unit of analysis (firm vs person), different geographic attribution (legal seat vs residence), different relevance to allocation (delivery design vs targeting). They share the AI-exposure score layer (industry-mean of ISCO scores, weighted by RL21152) but otherwise live independently.

### The data landscape — three buckets, each with a flaw

All published Estonian employment / firm data falls into one of three buckets:

| Bucket | Examples | Geographic meaning | What it misses |
|---|---|---|---|
| **A. Residence-based** | RL21154, RL21147, RL21152, LFS TT241/TT2419 | Where the worker **lives** | A Rapla resident commuting to a Tallinn bank counts in Rapla |
| **B. Firm-address-based** | ER0309, ER0271, ER0320, EM001, EM003, Äriregister, PAT wages | Where the firm's **legal seat** is registered | A bank with 1,500 staff across 15 maakond counts as 1 firm in Harju |
| **C. Workplace, but relational and shallow** | RL21166/RL21167/RL21163, LFS TT234 | Workplace expressed as same-vs-different omavalitsus/maakond as residence; **only Tallinn and Tartu** named as absolute destinations | No absolute workplace for Pärnu, Narva, Viljandi, etc. |

Estonia's **TÖR (Töötamise register)** at the Tax Authority does carry workplace address + occupation + employer EMTAK per employment relationship at full resolution (mandatory fields since 2019). But **TÖR microdata is not publicly accessible** and no published PXWeb table exposes `workplace municipality × EMTAK × headcount` at the granularity we'd want.

### Four paths to actual workplace × EMTAK data

| Path | Output | Effort | Cost |
|---|---|---|---|
| **A** — Tallinn/Tartu directly from RL21166 + maakond commuter correction | Tallinn & Tartu workplace totals exact; net inflow/outflow per maakond × EMTAK | Days | Free |
| **B** — Local Activity Unit (KAU) extract from Statistics Estonia's Statistical Business Register | True multi-establishment firm decomposition: employees by physical workplace × EMTAK × omavalitsus | Formal request, ~2–6 weeks | Modest (commission fee) |
| **C** — TÖR aggregate request to Tax Authority + Statistics Estonia | Employment relationships by workplace municipality × employer EMTAK × occupation (post-coded) | Formal request, ~6–12 weeks; data-protection review | Modest to high |
| **D** — PSU microdata (Structure of Earnings Survey) | ~32K-employee sample with workplace + ISCO + salary | Research access agreement, ~3–6 months | Free for accredited research; on-site/secure access |

The plan below uses **Path A and B**. Path C is a stretch goal for later evaluation work; Path D is out of scope.

### Phase 3a — Firm-side bottom-up matrix (free, ~2 weeks)

Build a firm-level mapping from the public Business Register plus Statistics Estonia aggregates, **flagging but not correcting** the legal-seat bias.

1. **Pull Äriregister bulk open data** (daily-refreshed, JSON/XML/CSV, free): for every active legal entity get registry code, name, legal address, **primary EMTAK-5**, status, legal form, employee count (where filed in annual report), revenue split by EMTAK (where filed).
2. **Geocode each legal address** to omavalitsus + Tallinn linnaosa via the Maa-amet ADS (Address Data Service) batch endpoint. Free.
3. **Aggregate** firm counts by `EMTAK-5 × omavalitsus`. Result: ~250K firms collapsed into a ~1,000 × ~80 grid (sparse).
4. **Layer Statistics Estonia aggregates** as marginal validation:
   - ER0309 firm counts × 132 admin units × 22 EMTAK sections — sum your RIK counts per (maakond, section) should match within ~5%.
   - ER0320 size distribution × omavalitsus.
   - ER051U industry births/deaths × maakond.
   - EM001 financials × 319 EMTAK × 7 size classes (national; allocate per locality by firm-count share if needed).
5. **Tag each (omavalitsus, EMTAK) cell with a legal-seat-bias flag** using RL21166: for EMTAK sections with high commuter flows (K finance, J ICT, large G retail chains, public sector O), mark the firm-count attribution as "low confidence — likely under-counts workplaces outside Harju."

**Output**: `data/processed/firm_matrix.csv`
```
omavalitsus | emtak_section | emtak_4digit | firm_count | size_distribution_json
employment_estimate | revenue_estimate | foreign_controlled_share | bias_flag
```

### Phase 3b — Workplace correction (commissioned, ~6 weeks)

Submit a narrow Path B request to Statistics Estonia for **KAU-based employee counts by EMTAK section × omavalitsus**, drawing on their Statistical Business Register's local-unit data. This is the only clean way to decompose multi-establishment firms (banks, retail chains, public sector) to actual workplace.

Frame it tightly:
- Variable: employees (annual average) by **physical workplace omavalitsus × EMTAK section (or letter)**.
- Reference period: latest available year.
- No ISCO crosstab needed at this stage (keeps cost down, avoids occupational suppression).

When delivered, merge into `firm_matrix.csv` as a `kau_employment` column and recompute the bias flags.

### Phase 3c — Workshop delivery model classifier (~1 week after 3a)

For each `(omavalitsus, EMTAK section)` cell, classify the recommended delivery model based on firm-size distribution:

| Pattern | Indicator | Delivery model |
|---|---|---|
| Few large firms dominate employment | top-3 firm employment > 60% of cell employment | **HR-led**: direct partnership with the firms' HR/L&D |
| Sectoral cluster, mid-size firms | many firms, none dominant, EMTAK is industry-association-organised | **Association-led**: sectoral chamber / EATL / EVEA / IT Klubi etc. |
| Long tail of micro-firms | majority of firms have <10 employees, no clusters | **Individual outreach**: open-enrollment workshops, online formats |
| Mixed | none of the above | **Hybrid**: pilot with the top firms, scale via association |

Output: enriches `firm_matrix.csv` with `delivery_model_recommendation` + `top_employers` (named list from RIK for the HR-led cells — actual firms to call).

### Integration with the v2 ISCO matrix

Two natural joins:

1. **Industry-mean AI exposure per EMTAK**: weighted average of ISCO-2 exposure scores within each EMTAK section, using RL21152 (national EMTAK × ISCO employment shares). Attached to every firm by its EMTAK code.
2. **AEI NAICS-level usage** as an independent second signal: Anthropic's industry-level augmentation/automation shares, NAICS ↔ NACE/EMTAK crosswalk. Crucially this measures *actual usage*, not occupational mix — captures industries that adopt AI faster or slower than their occupational composition would predict.

Cross-product diagnostics:
- *"People affected per firm"* = ISCO matrix's `people_affected` per locality ÷ firm matrix's `firm_count` per locality. Tells you delivery scale (1 large training vs many small).
- *"Workshop-reachable share"* = share of locality's AI-exposed workers in cells classified HR-led or association-led (i.e. delivery channels with low marginal-outreach cost) vs individual-outreach (high marginal cost).

### Caveats to flag up-front

- **Legal seat ≠ workplace** for banks (K), ICT firms (J), retail chains (G), public sector (O, P, Q). Phase 3a flags this; Phase 3b corrects it for EMTAK section but not below.
- **Principal EMTAK undercounts cross-activity firms.** Annual-report revenue-share-by-EMTAK exists for filed reports — use where present.
- **Self-reported, slow to update.** Many firms haven't refreshed EMTAK since founding.
- **Sole proprietors (FIE) cluster at residential address** — Tallinn/Tartu over-represented at the micro-firm tail. Filter or weight accordingly.
- **Foreign-controlled firms** (~30% of large-firm employment per ER013/EM061) often already have parent-led AI rollouts — flag rather than fund.

### Why the worker matrix is still the primary deliverable

For ~70% of the workforce, residence and workplace are the same omavalitsus, so the v2 residence-based ISCO matrix already approximates workplace-based well. The legal-seat distortions concentrate in Harju (Tallinn pull) and in a handful of industry sections. The firm-side matrix is essential **for delivery design**, but the ISCO matrix remains the right denominator for **how many people to train and where they live**. The two are complements, not substitutes.

### Suggested sequencing

1. **Now** — complete v2 (this README's scope) and ship the residence-based ISCO deliverable.
2. **Week 1–2 post v2** — Phase 3a (Äriregister + ADS geocoding + Statistics Estonia aggregates).
3. **Week 1 (parallel)** — submit Path B request to Statistics Estonia.
4. **Week 3** — Phase 3c delivery-model classifier on whatever Phase 3a + early Phase 3b data is in hand.
5. **Week 6–8** — Phase 3b correction lands, re-run Phase 3c, produce final firm-side matrix.

### Sources

- Statistics Estonia PXWeb: RL21163, RL21166, RL21167 (workplace–residence), TT231/TT234 (workplace distance/location), TT241/TT2419 (LFS residence × region × sector/occupation), ER0309/ER0271/ER0320 (firm × geography × EMTAK), ER0250/EM001/EM003 (size, financials), ER051U/ER060U (dynamics, survival), ER013/EM061 (groups, foreign control), PAT001–PAT005 (wages × industry), PAV014 (vacancies × maakond).
- [Äriregister open data portal](https://avaandmed.ariregister.rik.ee) — 8 daily-refreshed datasets in JSON/XML, some CSV; includes general data, EMTAK revenue distribution, annual reports.
- [Maa-amet In-ADS address geocoding service](https://inaadress.maaamet.ee/inaadress/gazetteer) — batch endpoint for address → omavalitsus.
- [TÖR (Töötamise register) — Estonian Tax and Customs Board](https://www.emta.ee/en/business-client/registration-business/employment-register) — administrative employment register, mandatory workplace address + occupation title fields since 2019. Microdata not publicly accessible; aggregate outputs derived by Statistics Estonia.
- [Statistics Estonia — Employment Register data submission methodology](https://stat.ee/en/submit-data/about-data-submission/surveys-enterprises/submit-data-employment-register).
