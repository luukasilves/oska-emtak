# Estonian AI Programme — Regional × Industry × Occupation Mapping: Data Inventory & Approach Proposal

## Context

The Estonian National AI Programme needs to allocate AI-skilling resources across the country. The target output is a matrix: **EMTAK (industry) × regional distribution × OSKA occupational AI-exposure assessments**, scaled to ~100,000 workers, that will feed a recommended workshop plan.

This first-phase brief addresses the prerequisite: **how to correlate the regional distribution of jobs, enterprises, and AI exposure** — using publicly available Estonian and EU data. The core difficulty is that EMTAK classifies *firms* (what they produce), while ISCO/OSKA classifies *workers* (what they do); these are related but not directly mappable, and Statistics Estonia uses ~50 occupation names while OSKA's detail level has 400+.

The v2 pipeline and Streamlit dashboard are **built and live** at github.com/luukasilves/oska-emtak. This document is the methodology brief that motivates them; see the **Implementation Status** section below for the current build state and the **Next-Step Ideas** section for documented follow-ups.

---

## Headline Findings

**1. The 3D crosstab already exists at county level.** Statistics Estonia's 2021 register-based Census (REL2021) table **RL21152** directly publishes employment by **EMTAK × ISCO × Maakond × Sex** at full granularity, register-based (no sampling error). The full 3-way crosstab is published only at maakond. Snapshot date: 31 December 2021.

**2. Sub-county granularity is available for the two-way breakdowns.** Table **RL21154** publishes **ISCO × municipality + city-district + settlement** (245 location codes — including Tallinn's 8 districts, Kohtla-Järve's 5 districts, ~79 omavalitsus, and standalone towns). Table **RL21147** does the same for **EMTAK × sub-county**. So the *ISCO-only* model can be built at municipality/district granularity; only the full 3D EMTAK×ISCO×geo matrix is capped at maakond.

**3. For the headline question, ISCO alone is sufficient.** If the goal is *"where are the AI-exposed workers across Estonia,"* we don't strictly need the OSKA mapping or EMTAK at all. International AI-exposure scores (Felten AIOE, ILO WP140, Eloundou, Pizzinelli complementarity) attach directly to ISCO codes. EMTAK and OSKA earn their keep at the *workshop-design* stage, not the regional-allocation stage. This motivates a two-tier delivery.

**4. AI exposure has two dimensions — measurable separately.** "Opportunity" (where AI augments work and training adds value) and "Risk" (where AI threatens displacement) are conceptually distinct and require different scores. The Anthropic Economic Index (measured Claude usage, augmentation/automation split) anchored to ILO WP140's ISCO-08 exposure tiers gives us both axes natively.

**5. OSKA adds a third axis — Demand–Supply gap — that international AI data cannot reproduce.** OSKA's 10-year occupational forecasts (demand × graduate-supply per ametialagrupp) answer "does Estonia need more workers here regardless of AI?" — a question independent of AI exposure. This makes OSKA a non-redundant third lens, not a relabeling of ISCO. Workshop priority logic combines all three: High Opportunity × Shortage = double-win training; High Risk × Surplus = transition support, not retention.

**6. No jurisdiction has used AI exposure scores to allocate skilling funds; Estonia would be first.** OECD, Brookings, IAB, and ONS produced descriptive exposure maps; none drove funding formulas. The UK AI Opportunities Action Plan (2026), US DOL TEGL 03-25 (2025), German *Nationale Weiterbildungsstrategie*, and French *France 2030* all commit to AI upskilling but allocate by population, sector, or partnership. The closest live policy analogue — Sweden's *omställningsstudiestöd* — targets shortage occupations, not exposure. This means our matrix is publishable methodology, not just internal allocation; documentation and evaluation should be built accordingly from day one.

**7. AI exposure ≠ displacement; the Opportunity axis is empirically the primary policy lever.** Guarascio, Reljic & Stöllinger (*Structural Change & Economic Dynamics* 73/2025) find AI exposure correlates with employment *growth* in EU Innovation Leader regions (FI, SE, DK, NL, BE), not decline. Cazzaniga et al. (IMF WP 2024/116) show Brazilian and UK workers transition *into* high-exposure × high-complementarity occupations with wage gains. ETLA Finland (2024) finds no displacement among young workers in high-exposure occupations. Implication: programme messaging should lean "AI fluency for opportunity" rather than "displacement protection". The Risk axis still matters but mostly where complementarity is low.

**8. Naive exposure-weighted allocation would concentrate funds in Tallinn and Tartu; two countermeasures.** AI adoption is geographically concentrated wherever it has been measured — BBVA Research finds 78% of Spanish AI firms in Barcelona+Madrid; Brookings finds 30 US metros captured two-thirds of all AI postings. Estonia will mirror this pattern.
- **Countermeasure A — Exposure-gap allocation.** Target on (exposure − adoption proxy), not exposure alone. Adoption proxy candidates: sectoral AI-firm density from Äriregister, ICT employment share (RL21147 section J), remote-work share (TT2419), Anthropic AEI usage rates if available at regional resolution.
- **Countermeasure B — Shift-share decomposition** on the EMTAK × ISCO × maakond cube: separate "exposed because of industry mix" (Ida-Viru shale, Tartu IT) from "within-industry exposure". The German Kreis-level analogue (Dengler & Matthes, IAB-Kurzbericht 5/2024) shows Dingolfing-Landau scoring 51.8% purely from auto manufacturing — the region didn't need reskilling, the industry did.

**9. Sweden's *omställningsstudiestöd* is the closest policy analogue and a portable delivery-model precedent.** ~30,000 places per year, SEK 4.88bn budget for 2025, 100,000+ applications since October 2022. Targets *shortage* occupations from Arbetsförmedlingen's *Yrkesbarometern* — not exposure. But the mechanism (individual grants, demand-led, application-based, occupation-anchored) is directly portable. A suggested hybrid allocation rule for Estonia, synthesising Sweden plus the exposure work: roughly 50% floor by population, 30% top-up by Opportunity × complementarity, 20% override by OSKA shortage list. Exact weights are a design choice for the workshop-plan phase.

---

## Data Inventory

### A. The Spine — Census 2021 (REL2021)

| Table | Dimensions | Granularity | Role |
|---|---|---|---|
| **RL21154** | ISCO (51) × Sex × Location | **245 location codes** — maakond, omavalitsus, Tallinn/Kohtla-Järve city districts, standalone settlement towns | **Tier 1 spine — ISCO × fine geography** |
| **RL21147** | EMTAK (106) × Sex × Location | Same 245 location codes | Industry × fine geography (for delivery context) |
| **RL21152** | EMTAK (106) × ISCO (51) × Sex × Maakond | 15 counties only | **Tier 2 spine — full 3D matrix** |
| RL21166 | Work-location county × EMTAK × Residence county | Distinguishes where people *work* vs *live* (matters for Tallinn commuter belt, Ida-Viru) | Commuter correction |
| RL21155 | ISCO × Sex × Age × Maakond | Demographic overlay on occupations | Age-cohort targeting |
| RL21158 | ISCO × Sex × Age × Education × Maakond | Adds education level | Skilling-readiness signal |
| RL21148 | EMTAK × Sex × Age × Maakond | Industry × demographics | Sector-level demographics |

- Portal: https://andmed.stat.ee/et/stat/rahvaloendus/rel2021/rahvastiku-majanduslik-aktiivsus/hoivatud-ja-tooranne
- Format: PXWeb (downloadable CSV/Excel/JSON via API)

### B. Currency Updates — Annual & Quarterly Labour Statistics

| Table | What it adds | Limitation |
|---|---|---|
| TT2109 | ISCO (49 detailed groups), annual to 2025 | National only — no region or EMTAK |
| TT0200 | EMTAK (67 industries), annual to 2025 | National only — no region or occupation |
| TT2419 / TT2420 | Maakond × occupation, quarterly | Only 3 broad occupation classes (white/blue-collar) |
| TT241 | Maakond × economic sector, annual | Only 4 macro-sectors |

Use case: reweight RL21152 cells to 2024/2025 totals to handle drift since the Census, using national ISCO/EMTAK growth rates and county-level employment changes as anchors.

### C. Enterprise Layer

| Table | Dimensions | Use |
|---|---|---|
| EM001 | Enterprise count + economic indicators × EMTAK × employee-size class | Firm-density by industry |
| EM003 | Enterprises × maakond × size class | Where firms cluster geographically |

These let us answer: *how many firms in each EMTAK in each maakond, broken by size?* — important because workshop delivery models differ for "1,000 sole traders" vs "10 large employers."

### D. AI-Exposure Scores — Two-Axis Framework

We will produce **two separate scores per occupation**, not one composite. They answer different policy questions:

- **Opportunity axis** — where AI is actually being used to *augment* work (= where training delivers productivity gains).
- **Risk axis** — where AI is being used to *automate* work (= where displacement threat is concrete, not theoretical).

The literature splits into two paradigms: (i) *theoretical exposure* — expert or LLM ratings of how much of an occupation's task profile AI *could* touch; (ii) *measured usage* — actual usage data from AI products. The measured-usage paradigm (Anthropic AEI, Microsoft) is methodologically superior where coverage permits. We will use both, anchored to an ISCO-native baseline.

| Source | What it measures | Granularity | Public data? | Role in our model | Wired in v2? |
|---|---|---|---|---|---|
| **Anthropic Economic Index (AEI)** (Handa et al., Feb 2025 + quarterly updates) | **Measured Claude usage** classified into augmentation vs automation per O*NET task; aggregates to SOC | O*NET task → SOC → ISCO via crosswalk | Yes — huggingface.co/datasets/Anthropic/EconomicIndex (CC-BY) | **Primary augmentation/automation split** | **Yes (primary, 1P-API release; ISCO-2 and ISCO-4)** |
| **ILO WP140** (Gmyrek et al., 2025) | Expert-rated GenAI exposure, 4-class categorical: Not Affected / Big Unknown / Augmentation Potential / Automation Potential | ISCO-08 4-digit (436 occs) | Yes — github.com/pgmyrek/GenAI_Exposure_Tree_Plot (categorical); ilo.org WP140 PDF appendix (numeric) | **ISCO-native expert-rated baseline** | **Yes (`ilo_wp140` model, ISCO-4)** |
| **Demirev** (Industry & Innovation, 2026) | AI-product-derived exposure with explicit aug/auto decomposition; ESCO → ISCO-4 via cosine similarity of skills × AI capabilities | ISCO-08 4-digit (~427 occs) | Yes — github.com/demirev/ai-products | **Continuous ISCO-4 exposure with native aug/auto split** | **Yes (`demirev_ai_products` model, ISCO-4)** |
| **Cazzaniga et al.** (IMF Staff Discussion Note 2024/001) | Updated Pizzinelli — Felten exposure × complementarity; 40 OECD countries | ISCO-08 | Yes — IMF PDF + occupation-level appendix | Cross-validation; complementarity-based axis split. **Substituted by Demirev in build sandbox (IMF data is PDF-only and not retrievable from the build environment)** | No — pending data drop |
| **Felten et al. AIOE** (2021/2023) | Composite of 10 AI domains × O*NET abilities, expert-rated | SOC → crosswalk to ISCO-4/3 | Yes — github.com/AIOE-Data/AIOE | Most-cited baseline; use for sanity check / external comparability | **Yes (primary exposure baseline; `felten_aei` ISCO-2 and `felten_aei_isco4` ISCO-4)** |
| **Eloundou et al.** ("GPTs are GPTs", 2024) | LLM-rated exposure levels E1/E2/E3 | SOC → ISCO | Yes — github.com/openai/GPTs-are-GPTs | Demoted to side reference. Yin et al. 2026 documents instability of LLM-rated scores (Cohen's κ ≈ 0.36 across models) | No — demoted |
| **Microsoft "Working with AI"** (Tomlinson et al., 2025) | Measured Copilot usage for 40+ occupations | SOC → ISCO | Methodology only; raw data not public | Validation for Anthropic AEI in the white-collar segment | No — no public data |
| **JRC Casas** (JRC145832, 2024) | 352 benchmarks → 14 cognitive abilities → 127 ISCO-3 occupations | ISCO-3 | Yes (methodology); appendix table in PDF | Validation; benchmark-anchored alternative to LLM/expert ratings | Stub — `jrc_casas` aggregator registered, needs CSV drop per `data/raw/jrc_casas/README.md` |
| **OSKA AI uuring** | Qualitative Estonia-specific findings | Sectoral / role archetypes | Yes (PDFs only) | Qualitative overlay / sanity check | No — Tier 2 |
| **OSKA 69 ametialagrupid** | Estonian professional groups | Per-group narrative; ISCO crosswalk not public | Yes (web pages) | Tier 2 only — readability for Estonian stakeholders | No — Tier 2 |

**Methodological note — LLM-rating instability:** Yin, Vu, Persico (NBER 2026, "How (un)Stable Are LLM Occupational Exposure Scores?") show poor inter-model agreement on LLM-annotated task exposure. This is a reason to anchor on (a) human-expert rated indices (ILO WP140, Felten) and (b) measured-usage data (AEI), rather than LLM-annotated exposure (Eloundou). It also implies we should treat AEI's *task-level classification* (which uses LLM annotation) with some caution while still valuing its *usage measurement* itself.

**Operational definition:**

*As built in v2 baseline:*
- `exposure = Felten AIOE` (SOC-6 → ISCO-2 simple mean per Felten convention, then min-max rescaled to [0,1])
- `augmentation_share = AEI 1P-API task-iteration + learning + validation share` (O*NET task → SOC-6 → ISCO-2, weighted by classified observations per task; collaboration-pattern classification per Anthropic Feb 2025 paper)
- `automation_share = AEI 1P-API directive + feedback-loop share` (same chain)
- `Opportunity = exposure × augmentation_share`
- `Risk = exposure × automation_share`
- Low-confidence cells (n<10 matched O*NET tasks per ISCO-2) fall back to ISCO-1 means; if the whole ISCO-1 group is low-confidence, fall back to the global mean. Flagged in `data/processed/scores/scores_long.csv` `source` column as `derived_aug_fallback`.

*Operational target (next-step A):* swap exposure to `ILO WP140 tier` (1–4, ISCO-08 native, human-expert rated) and add Cazzaniga complementarity scores as cross-validation. Register both as new models alongside `felten_aei`; matrices auto-generate per the v2 architecture.

### E. Classification Crosswalks (already aligned)

- **EMTAK ↔ NACE Rev. 2**: identical at digits 1–4 (EMTAK adds national level 5). Confirmed via vana.stat.ee/30845.
- **AK 2008 (Ametite klassifikaator) ↔ ISCO-08**: identical at digits 1–4 (AK adds national level 5 with Estonian job titles). Source: klassifikaatorid.stat.ee.
- **OSKA 69 ametialagrupid ↔ ISCO**: no public crosswalk file; OSKA's internal mapping is at ISCO-4 per CEDEFOP documentation. Would need either (i) a request to Kutsekoda, or (ii) a manual mapping pass using occupation names.

### F. Eurostat as Validation / Backstop

- **lfsa_eisn2**: Employment by NACE × ISCO at national and NUTS2 levels. Estonia = 1 NUTS2 (EE0) → not regionally useful, but provides annual national crosstabs for currency-adjusting RL21152 between censuses.

---

## Implementation Status

The v2 pipeline is built and pushed to **github.com/luukasilves/oska-emtak** (public). The Streamlit dashboard's first deploy is in progress at *ee-ai-exposure.streamlit.app*.

**v2 architecture — three first-class dimensions:**
- **model** — an AI-exposure source bundle (e.g. `felten_aei`). Registered in `src/fetch_ai_scores.py` and `data/processed/scores/MODELS.md`.
- **scenario** — an employment-weighting basis (e.g. `2021_census`). Registered in `src/build_weights.py` and `data/processed/weights/SCENARIOS.md`.
- **taxonomy** — an occupational classification at which scores and weights are expressed (e.g. `isco2`, `isco4`, `soc6`, `oska69`). Bridged when mismatched via `data/crosswalks/<from>_to_<to>.csv`.

Adding a new model, scenario, or taxonomy is a drop-in: implement an aggregator/builder function, no schema changes. Matrices are produced per `(model, scenario)` combination and live at `data/processed/matrices/matrix_<model>_<scenario>.csv`.

**Currently wired:** `felten_aei × 2021_census × isco2` only. All other models/scenarios from the table above are documented stubs.

**Pipeline scripts (under `src/`):**
- `fetch_rl21154.py` — Statistics Estonia PXWeb fetcher (idempotent).
- `fetch_ai_scores.py` — model aggregators → `scores_long.csv`. Auto-downloads the gitignored ~44 MB AEI 1P-API CSV from Hugging Face on first run.
- `build_weights.py` — scenario builders → `weights_long.csv`.
- `build_matrix.py` — joins scores × weights → `matrices/` + `summaries/`. Handles taxonomy mismatch via crosswalk lookup; skips cleanly when no crosswalk available.
- `visualize.py` — discovers matrices, renders 8 PNGs per combo into `output/charts/<model>_<scenario>/`.
- `dashboard.py` — Streamlit explorer with Map / Occupations / AEI breakdown / Data tabs; auto-discovers combos.
- `common.py` — shared constants and helpers (`AMET_TO_ISCO`, `OMAV_REMAP`, `KNOWN_TAXONOMIES`, geometry builder, crosswalk loader).

**What was verified end-to-end:** v2 matrix and scores are bit-for-bit identical to the v0 prototype (zero numeric drift); HARJU MAAKOND total employed = 312,346; TARTU MAAKOND = 77,229; top-5 ISCO-2 by exposure are codes 24/12/25/95/23; municipality choropleth matches 87 of 90 polygons (Kukruse, Oru, Sompa Kohtla-Järve linnaosa unmatched because RL21154 doesn't publish them). Fresh-clone test passed: `git clone` + `python3 src/fetch_ai_scores.py` re-fetches AEI raw data and produces identical `scores_long.csv`.

**Heavy raw AEI files** (~44 MB 1P-API CSV, ~92 MB Claude.ai CSV) are .gitignored; the 1P-API is re-downloaded on demand by `ensure_aei_raw_downloaded()` in `fetch_ai_scores.py`. The Claude.ai variant is not yet used by any registered model — see Open Question 6 below.

---

## International Precedents — How Others Built Sub-National AI Exposure Maps

Six sub-national mapping efforts inform the methodology choices below. None produced a true industry × occupation × region tensor; none drove skilling allocation. Estonia's contribution is methodologically distinct.

| Study | Spatial unit | Exposure metric | Industry × region cross? | Validation | Policy use |
|---|---|---|---|---|---|
| **OECD 2024** *Geography of Generative AI* | TL2 (NUTS-2), 35 countries | Felten AIOE | No | None | Descriptive only |
| **Guarascio, Reljic & Stöllinger 2025** *Diverging Paths* | NUTS-2, 240+ EU regions | Felten AIOE, four typologies | No | 2011–2021 employment change | Descriptive only |
| **JRC Casas et al. 2025/26** | ISCO-3 (national) | 352 benchmarks → 14 abilities → 127 occupations | No (national only) | None | Methodology paper |
| **Brookings (Muro/Maxim/Whiton)** 2019 + 2024 | ~800 US MSAs | Switched: Frey-Osborne → Webb → Eloundou | No | Limited retrospective | Descriptive; no allocation |
| **IAB-Kurzbericht 5/2024** (Dengler & Matthes) | German Kreis (401 districts) | Task-based *Substituierbarkeitspotenzial* | No | Lower growth in high-substitution occupations | Feeds *Job-Futuromat*; not allocation |
| **UK ONS 2019** *Probability of Automation in England* | English local authorities | Frey-Osborne adjusted via PIAAC two-stage regression | Industry as regression covariate, not output dim | None | Descriptive only |

Selected takeaways:

- **OECD 2024** — Stockholm 45% exposed vs rural Colombian Cauca 13%. Closest published comparator to our maakond-level mapping.
- **Guarascio et al. 2025** — exposure correlates with employment *growth* in Innovation Leader regions (see headline #7). Closest EU comparator.
- **Brookings's metric switches** show metric choice changes findings more than spatial method — argues for running multiple scores side-by-side rather than committing to one.
- **IAB Dingolfing-Landau** at 51.8% illustrates the sectoral-concentration trap that motivates the shift-share decomposition in headline #8.
- **UK ONS PIAAC two-stage regression** is more sophisticated than simple employment-share averaging but was capped in Scotland/Wales by sample size. Direct relevance: Estonia's PIAAC sample is ~5,000 nationally; finer-than-maakond cuts will be noisy.

What Estonia's matrix adds beyond the existing literature:

1. **True industry × occupation × region tensor** — no published study has built one. Felten/Raj/Seamans builds occupation×industry and occupation×geography separately; OECD, Brookings, IAB do occupation×region only.
2. **Validation against actual training outcomes** — no published study has done this. Headline #6 plus the evaluation-by-design protocol below make this achievable.
3. **Complementarity-adjusted exposure operationalised in a sub-national map** — Pizzinelli/Cazzaniga complementarity is widely cited but rarely applied in regional maps. Our Opportunity = Exposure × augmentation_share and Risk = Exposure × automation_share is the operational analogue.

---

## Proposed Approach — Two Tiers

Tier 1 answers regional allocation with the minimum data needed, at the finest geographic detail possible. Tier 2 adds the dimensions required to actually design and deliver workshops.

### Tier 1 — ISCO-only matrix at sub-county granularity, with Opportunity + Risk axes

**Goal:** answer *"in each Estonian locality (down to municipality / city district), how many workers face high AI opportunity, and how many face high AI risk?"* — the input needed to allocate the 100,000-person training budget across the country.

**Step 1a — Pull RL21154** via the Statistics Estonia PXWeb API. **[DONE]** Implemented in `src/fetch_rl21154.py`; produces `data/raw/RL21154_long.csv` (~12k rows: 245 location codes × ~51 ISCO categories × sex breakdowns).

**Step 1b — Build the ISCO crosswalks. [DONE]**
- ISCO-4 → ISCO-3 (trivial truncation) — handled in `src/common.py`.
- Estonian AK 2008 ↔ ISCO-08 (identical at digits 1–4 per klassifikaatorid.stat.ee) — encoded in `common.AMET_TO_ISCO`.
- ISCO-3 → SOC via BLS crosswalk in `data/raw/bls_soc_isco_crosswalk.xls`; used by Felten and AEI aggregators.

**Step 1c — Attach the two AI-exposure axes. [PARTIAL]**
- Felten AIOE wired (not ILO WP140 — that's next-step A). `src/fetch_ai_scores.py::aggregate_felten_aei` reads `data/raw/AIOE_DataAppendix.xlsx`, joins via BLS crosswalk to ISCO-2 with simple mean.
- Anthropic Economic Index wired (1P-API release; the Claude.ai consumer release is downloaded but not yet a registered model). Per-O*NET-task collaboration patterns → SOC-6 → ISCO-2.
- For each ISCO-2: `Opportunity = exposure × augmentation_share`; `Risk = exposure × automation_share`.
- Side columns for sanity in `scores_long.csv`: `source` flag distinguishes derived from fallback cells.

**Step 1d — Attach the OSKA demand-supply layer. [PENDING]** OSKA is not redundant with international AI-exposure data; it answers a *different* question (does Estonia need more workers in this occupation, regardless of AI?). For workshop allocation this is decisive:
- Map ISCO-4 → OSKA 69 ametialagrupid (manual ~1 day, or request crosswalk from Kutsekoda).
- For each ametialagrupp, attach OSKA's:
  - 10-year demand forecast (positions needed by 2035)
  - Annual graduate-supply forecast (VET + HE)
  - Shortage/surplus classification (CEDEFOP "Mismatch Priority Occupations" + OSKA's own tier)
- Use this as the **Demand_gap** column on the matrix. Workshop priority logic:
  - High Opportunity × Shortage = train more (double win)
  - High Risk × adjacent Shortage = reskill / pipeline transition
  - High Risk × Surplus = displacement support, not retention training

**Step 1e — Aggregate by location. [DONE]** `src/build_matrix.py` produces `matrix_felten_aei_2021_census.csv` (9,800 rows: per (location, ISCO-2)) and `maakond_summary_felten_aei_2021_census.csv` (15-row county roll-up with weighted exposure/Opportunity/Risk + raw totals). The Streamlit dashboard aggregates further on the fly (top-N occupations per locality, ISCO 1-digit filtering, etc.).

**Step 1f — Output. [DONE]** Three artefacts now ship in place of the originally-planned single Excel workbook:
- 8 static PNG charts per combo at `output/charts/felten_aei_2021_census/` (maakond bars, choropleth, scatter, top-15, plus municipality + linnaosa choropleth + people-affected map).
- Interactive **Streamlit dashboard** (`src/dashboard.py`) — Map / Occupations / AEI breakdown / Data tabs with click-to-drill-down and download-as-CSV.
- Long-format CSVs (`scores_long.csv`, `weights_long.csv`, `matrix_*.csv`, `maakond_summary_*.csv`) for downstream consumers.

### Tier 2 — Full matrix (workshop design and delivery) [PENDING — Tier 2 not yet started]

**Goal:** answer *"who exactly do we reach in each county, through which industries and intermediaries, and what content do they need?"*

**Step 2a — Restore the EMTAK dimension at maakond level.** Pull RL21152 in full. Industry context matters for delivery channels (sectoral associations) and for AI-impact nuance (same ISCO behaves differently in different industries).

**Step 2b — Pull RL21147** for sub-county EMTAK detail. Same 245 locations as RL21154. Even without the three-way intersection, this tells us *which industries cluster where* at fine geography — answering "mis tööstus kontsentreerunud Ida-Virusse" directly.

**Step 2c — Add OSKA sectoral and adoption narratives.** The OSKA AI uuring's qualitative findings (sectoral adoption rates, "smart buyer" / end-user / leader roles, firm-level barriers) feed into the workshop content design, not the allocation matrix. Layer these as narrative annotations per sector, not as scores. Note: the ISCO → OSKA-69 crosswalk and OSKA forecast data were already pulled in Tier 1.

**Step 2d — Layer enterprise data.** Join EM003 (enterprises × maakond × size) and EM001 (enterprises × EMTAK × size). Adds firm count and size distribution — critical because workshop delivery differs hugely between "50,000 workers in 50 large firms" and "50,000 across 5,000 micro-businesses."

**Step 2e — Currency adjustment (optional).** Single-pass marginal scaling to rescale RL21152 cells to latest annual totals from TT2109 / TT0200 / TT2419 / TT241. Likely not needed for a first round.

**Step 2f — Full output.** Long-format CSV plus pivot-ready Excel:
`location | maakond | EMTAK_code | EMTAK_label | ISCO4_code | ISCO4_label | OSKA_69_group | employed_persons | Opportunity_score | Risk_score | OSKA_AI_tier | n_enterprises | enterprise_size_mix`

### Out of scope for both tiers
- The workshop plan itself (next phase: content, cadence, budget per locality).
- Forecasting employment changes 2026–2030 (OSKA publishes separate forecasts; can be added later).
- True three-way sub-county (EMTAK × ISCO × omavalitsus). Statistics Estonia does not publish this; municipality-level industry and municipality-level occupation must be linked through the maakond-level three-way RL21152 if needed.

---

## Next-Step Ideas Beyond Tier 2

These are concrete extensions to the built v2 baseline; each is independent and ordered by payoff-to-effort.

**A — Register JRC Casas 2025/26 + ILO WP140 + Cazzaniga as additional exposure models.** *(Mostly DONE — May 2026.)* Three new ISCO-3/4 models are now wired alongside Felten: `felten_aei_isco4` (Felten re-exposed at ISCO-4), `ilo_wp140` (ILO categorical 4-class exposure), and `demirev_ai_products` (continuous ISCO-4 with aug/auto decomposition; substituted for Cazzaniga because the IMF SDN 2024/001 PDF appendix isn't retrievable from the build sandbox). `jrc_casas` is registered as a stub aggregator pending a CSV drop per `data/raw/jrc_casas/README.md`. New visualizations: chart 09 (top-30 ISCO-4 detailed occupations per model) and chart 10 (cross-model rank correlation heatmap); dashboard now has a "🔬 ISCO-4 detail" tab with per-occupation side-by-side scores and a `divergence` flag. **ISCO-4 county-level employment is not publicly available** (RL21154 / RL21157 / TT2109 all top out at ~50-category ISCO-2 Amet codes), so the ISCO-4 richness is on the score side only; the county-level matrix collapses ISCO-3/4 scores to ISCO-2 via `data/crosswalks/isco{3,4}_to_isco2.csv` with per-model weight renormalisation (no fabricated employment splits).

**B — Compute an exposure-gap metric for catch-up targeting.** New per-location column `Adoption_proxy_score` sourced from one or a blend of: sectoral AI-firm density from Äriregister, ICT employment share (RL21147 section J), remote-work share (TT2419), Anthropic AEI usage rates if available at regional resolution. New column `Exposure_gap = Opportunity_score − Adoption_proxy_score` flags regions that are exposed but under-adopted (target for catch-up training) versus exposed and already self-adapting. Use as a secondary allocation signal alongside the primary Opportunity score. Effort: ~1 day once the adoption proxy is chosen.

**C — Shift-share decomposition on the Tier 2 matrix.** For each maakond, decompose exposure into three components: an *industry-mix* term (what its exposure would be if it had the national within-industry occupational mix but its actual EMTAK distribution), a *within-industry* term (what its exposure would be if it had the national EMTAK distribution but its actual within-industry occupational composition), and an interaction term. Reveals whether high rankings in Ida-Viru, Tartu, or Harju are about industry concentration versus genuinely different occupational composition. Standard regional-science technique; ~0.5 day in Python.

**D — Evaluation-by-design protocol.** Pre-register outcome metrics before workshop rollout: 12-month employment retention, wage growth, course completion, self-reported AI-tool adoption rate. Stagger workshop delivery across maakond (e.g. randomised 2-month phasing) to create natural comparison cohorts for difference-in-differences identification. Build a 2-page protocol document during the matrix design phase, not retrospectively. Estonia could publish the first retrospective validation of exposure-targeted skilling in 3–5 years (see headline #6).

**E — Sweden *omställningsstudiestöd* delivery-structure memo.** Even though Sweden targets by shortage occupation rather than exposure, the mechanism is the closest live analogue: individual grant amounts, application/approval flow, occupation-list governance, intermediary role of Arbetsförmedlingen + CSN. A 2–3 page memo mapping Sweden's design to Estonia's institutional landscape (Eesti Töötukassa as the CSN + Arbetsförmedlingen analogue?) feeds the workshop-plan phase. Separate from the data work but tightly related.

**F — Reframe Opportunity axis as primary in the deliverable narrative.** Following headline #7 and the Guarascio/Cazzaniga/ETLA evidence, the Tier 1 output memo (Step 1f above) should lead with the Opportunity map and treat the Risk map as a "small but real" supplement, not as the primary policy lever. This is a narrative and framing change, not a calculation change — but it sets the tone for stakeholder reception.

---

## Critical Files / Resources

### As built in the repo at github.com/luukasilves/oska-emtak/

**Code (`src/`):**
- `common.py` — shared constants, paths, taxonomy registry, BLS crosswalk loader, RL21154 location-code parser, combined-municipality geometry builder.
- `fetch_rl21154.py` — Statistics Estonia PXWeb fetcher.
- `fetch_ai_scores.py` — model aggregators → `scores_long.csv`. Includes `ensure_aei_raw_downloaded()` so fresh clones auto-fetch the gitignored AEI 1P-API CSV.
- `build_weights.py` — scenario builders → `weights_long.csv`.
- `build_matrix.py` — joins scores × weights → `matrices/` + `summaries/` per `(model, scenario)`. Taxonomy-aware via `data/crosswalks/`.
- `visualize.py` — discovers matrices, renders 8 PNGs per combo.
- `dashboard.py` — Streamlit explorer.

**Pristine inputs (`data/raw/`):**
- `RL21154_long.csv` — Statistics Estonia census employment.
- `anthropic_aei/aei_raw_1p_api_*.csv` (gitignored; auto-fetched), `aei_raw_claude_ai_*.csv` (gitignored), `aei_2025_02_*.csv` (committed: O*NET task statements, SOC structure, BLS employment).
- `AIOE_DataAppendix.xlsx`, `Language%20Modeling%20AIOE%20and%20AIIE.xlsx` — Felten AIOE source.
- `bls_soc_isco_crosswalk.xls` — Wayback-Machine-cached BLS 2010 SOC ↔ ISCO-08.
- `maakond.geojson`, `omavalitsus.geojson`, `asustusyksus.geojson` — EHAK administrative geometries (buildig/EHAK).

**Derived outputs (`data/processed/`):**
- `scores/scores_long.csv`, `scores/MODELS.md` — model registry.
- `weights/weights_long.csv`, `weights/SCENARIOS.md` — scenario registry.
- `matrices/matrix_<model>_<scenario>.csv` — one file per combo.
- `summaries/maakond_summary_<model>_<scenario>.csv` — per-combo county roll-up.
- `geometry/estonia_municipalities_combined.geojson` — 90-polygon merged municipality + linnaosa geometry.

**Crosswalks (`data/crosswalks/`):**
- `CROSSWALKS.md` — registry; currently empty (only `taxonomy=isco2` in use).

**Output (`output/`):**
- `charts/felten_aei_2021_census/` — 8 PNGs.
- `README.md` — chart documentation, AEI extension options, dashboard run/deploy instructions.

**Streamlit deployment scaffolding:**
- `requirements.txt`, `.streamlit/config.toml`, `.streamlit/secrets.toml.example`.

### Upstream sources (URLs)

- https://andmed.stat.ee/api/v1/et/stat/rahvaloendus/rel2021/rahvastiku-majanduslik-aktiivsus/hoivatud-ja-tooranne/RL21154.px (Tier 1 spine: ISCO × sub-county)
- https://andmed.stat.ee/api/v1/et/stat/rahvaloendus/rel2021/rahvastiku-majanduslik-aktiivsus/hoivatud-ja-tooranne/RL21147.px (EMTAK × sub-county)
- https://andmed.stat.ee/api/v1/et/stat/rahvaloendus/rel2021/rahvastiku-majanduslik-aktiivsus/hoivatud-ja-tooranne/RL21152.px (Tier 2 spine: EMTAK × ISCO × maakond)
- https://andmed.stat.ee/api/v1/et/stat (PXWeb API root for all tables)
- https://huggingface.co/datasets/Anthropic/EconomicIndex (Anthropic AEI — measured Claude usage, augmentation/automation split; CC-BY)
- https://www.anthropic.com/economic-index (AEI landing page + reports)
- https://www.ilo.org/publications/generative-ai-and-jobs-refined-global-index-occupational-exposure (ILO WP140 ISCO-08 native scores; next-step A)
- https://www.imf.org/-/media/files/publications/sdn/2024/english/sdnea2024001.pdf (Cazzaniga et al. IMF SDN 2024/001 — updated Pizzinelli/Felten complementarity; next-step A)
- https://github.com/AIOE-Data/AIOE (Felten AIOE scores — currently the primary exposure source in v2)
- https://github.com/openai/GPTs-are-GPTs (Eloundou E1/E2/E3 scores — demoted, see Yin et al. 2026)
- https://www.nber.org/papers/w35110 (Yin, Vu, Persico — LLM-rating instability warning)
- https://uuringud.oska.kutsekoda.ee/uuringud/ai-uuring (OSKA AI report — qualitative overlay; Tier 2)
- https://oska.kutsekoda.ee/naidikulehed/?tab=ametialagrupid-tab (69 ametialagrupid; Tier 2)
- https://oskused.ee/ametid (~400 occupations for OSKA→ISCO mapping)
- https://klassifikaatorid.stat.ee (AK 2008 ↔ ISCO-08 classifier)
- https://vana.stat.ee/30845 (EMTAK 2008 ↔ NACE Rev. 2)

---

## Verification

**Verified for v2 baseline (felten_aei × 2021_census × isco2):**

1. **Bit-for-bit equivalence to v0 prototype** — zero numeric drift on scores, matrix, and maakond summary. Re-runs from raw produce identical files.
2. **Total check** — HARJU MAAKOND total_employed = 312,346; TARTU MAAKOND = 77,229; national total ~642,000.
3. **Sanity ranges** — top-5 ISCO-2 by exposure are `[24, 12, 25, 95, 23]` (95 is a known crosswalk outlier flagged in source column); bottom-5 are `[91, 92, 63, 93, 71]`. ISCO 23 (Teachers) is most augmentation-tilted at ~0.35; ISCO 83 (Drivers) most automation-tilted at ~0.985.
4. **Municipality join** — 87 of 90 polygons matched (Kukruse, Oru, Sompa Kohtla-Järve linnaosa unmatched because RL21154 doesn't publish them separately).
5. **Fresh-clone test** — `git clone` to a clean directory, then `python3 src/fetch_ai_scores.py`, produces identical `scores_long.csv`. The gitignored AEI raw file is auto-downloaded from Hugging Face.
6. **Multi-combo extensibility** — smoke tests A–D in the v2 refactor (dummy second model at same taxonomy; dummy second scenario; dummy model at different taxonomy with no crosswalk → cleanly skipped; same combo after adding a stub crosswalk → builds) all passed.

**Pending verifications (will apply when next-step A is implemented):**

1. **Marginal checks vs Statistics Estonia annual tables** — sum over (EMTAK, ISCO) per county should match TT2419 / TT241 totals within ~2% once ILO WP140 + RL21152 EMTAK dimension are wired.
2. **Rank-order agreement across exposure models** — ILO WP140 vs Felten AIOE vs JRC Casas should rank ISCO-2 codes similarly at the top end; divergences are interesting and worth annotating.
3. **EMTAK sanity spots** — once Tier 2 starts: Ida-Viru should show high concentration in EMTAK B/C (mining/manufacturing); Harju in J/M (ICT/professional); Tartu in P/Q (education/health) relative to its size.
4. **AI-exposure vs OSKA agreement** — high-exposure occupations should align with OSKA's qualitative findings on which ametialagrupid are flagged "critically affected."

---

## Open Questions

1. ~~**If Pizzinelli complementarity scores are not in clean tabular form**~~ — **resolved.** Current build uses AEI collaboration-pattern shares directly as the augmentation/automation split. Pizzinelli-style complementarity is a documented next step (next-step A via Cazzaniga IMF SDN 2024/001).

2. ~~**Output naming.**~~ — **resolved.** Opportunity / Risk used throughout the build, dashboard, and this document.

3. **Tier 2 trigger.** Build Tier 2 immediately after next-step A, or wait until allocation decisions need the full matrix? Tier 2 (EMTAK + enterprise + OSKA-69 + Demand-gap) is the workshop-design layer; Tier 1 already covers regional allocation.

4. **Kutsekoda outreach (Tier 2 only).** Request internal ISCO-4 → 69 ametialagrupid mapping vs build it manually? Saves ~1 day.

5. **Currency adjustment (Tier 2 only).** Use 2021 Census as-is, or rescale RL21152 cells to 2025 totals via TT2109/TT0200 marginals?

6. **AEI source: 1P-API vs Claude.ai consumer.** Current build uses the 1P-API release, which reflects programmatic/agentic usage and skews ~80% directive (automation pattern). The Claude.ai consumer release would shift the augmentation/automation mix toward augmentation. The Claude.ai CSV is already downloaded but not yet registered. Should we register it as a second model (`felten_aei_consumer`) per the AEI extensions documented in `output/README.md`?
