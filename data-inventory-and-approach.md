# Estonian AI Programme — Regional × Industry × Occupation Mapping: Data Inventory & Approach Proposal

## Context

The Estonian National AI Programme needs to allocate AI-skilling resources across the country. The target output is a matrix: **EMTAK (industry) × regional distribution × OSKA occupational AI-exposure assessments**, scaled to ~100,000 workers, that will feed a recommended workshop plan.

This first-phase brief addresses the prerequisite: **how to correlate the regional distribution of jobs, enterprises, and AI exposure** — using publicly available Estonian and EU data. The core difficulty is that EMTAK classifies *firms* (what they produce), while ISCO/OSKA classifies *workers* (what they do); these are related but not directly mappable, and Statistics Estonia uses ~50 occupation names while OSKA's detail level has 400+.

This document is a **data inventory + methodology proposal**. No analysis is run yet.

---

## Headline Findings

**1. The 3D crosstab already exists at county level.** Statistics Estonia's 2021 register-based Census (REL2021) table **RL21152** directly publishes employment by **EMTAK × ISCO × Maakond × Sex** at full granularity, register-based (no sampling error). The full 3-way crosstab is published only at maakond. Snapshot date: 31 December 2021.

**2. Sub-county granularity is available for the two-way breakdowns.** Table **RL21154** publishes **ISCO × municipality + city-district + settlement** (245 location codes — including Tallinn's 8 districts, Kohtla-Järve's 5 districts, ~79 omavalitsus, and standalone towns). Table **RL21147** does the same for **EMTAK × sub-county**. So the *ISCO-only* model can be built at municipality/district granularity; only the full 3D EMTAK×ISCO×geo matrix is capped at maakond.

**3. For the headline question, ISCO alone is sufficient.** If the goal is *"where are the AI-exposed workers across Estonia,"* we don't strictly need the OSKA mapping or EMTAK at all. International AI-exposure scores (Felten AIOE, ILO WP140, Eloundou, Pizzinelli complementarity) attach directly to ISCO codes. EMTAK and OSKA earn their keep at the *workshop-design* stage, not the regional-allocation stage. This motivates a two-tier delivery.

**4. AI exposure has two dimensions — measurable separately.** "Opportunity" (where AI augments work and training adds value) and "Risk" (where AI threatens displacement) are conceptually distinct and require different scores. The Anthropic Economic Index (measured Claude usage, augmentation/automation split) anchored to ILO WP140's ISCO-08 exposure tiers gives us both axes natively.

**5. OSKA adds a third axis — Demand–Supply gap — that international AI data cannot reproduce.** OSKA's 10-year occupational forecasts (demand × graduate-supply per ametialagrupp) answer "does Estonia need more workers here regardless of AI?" — a question independent of AI exposure. This makes OSKA a non-redundant third lens, not a relabeling of ISCO. Workshop priority logic combines all three: High Opportunity × Shortage = double-win training; High Risk × Surplus = transition support, not retention.

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

| Source | What it measures | Granularity | Public data? | Role in our model |
|---|---|---|---|---|
| **Anthropic Economic Index (AEI)** (Handa et al., Feb 2025 + quarterly updates) | **Measured Claude usage** classified into augmentation vs automation per O*NET task; aggregates to SOC | O*NET task → SOC → ISCO via crosswalk | Yes — huggingface.co/datasets/Anthropic/EconomicIndex (CC-BY) | **Primary augmentation/automation split** |
| **ILO WP140** (2025) | Expert-rated GenAI exposure gradient 1–4, ISCO-08 native | ISCO-08 4-digit (~427 occs) | Yes — ilo.org WP140 appendix | **Primary ISCO-native exposure baseline** |
| **Cazzaniga et al.** (IMF Staff Discussion Note 2024/001) | Updated Pizzinelli — Felten exposure × complementarity; 40 OECD countries | ISCO-08 | Yes — IMF PDF + occupation-level appendix | Cross-validation; complementarity-based axis split as backup |
| **Felten et al. AIOE** (2021/2023) | Composite of 10 AI domains × O*NET abilities, expert-rated | SOC → crosswalk to ISCO-3 | Yes — github.com/AIOE-Data/AIOE | Most-cited baseline; use for sanity check / external comparability |
| **Eloundou et al.** ("GPTs are GPTs", 2024) | LLM-rated exposure levels E1/E2/E3 | SOC → ISCO | Yes — github.com/openai/GPTs-are-GPTs | Demoted to side reference. Yin et al. 2026 documents instability of LLM-rated scores (Cohen's κ ≈ 0.36 across models) |
| **Microsoft "Working with AI"** (Tomlinson et al., 2025) | Measured Copilot usage for 40+ occupations | SOC → ISCO | Methodology only; raw data not public | Validation for Anthropic AEI in the white-collar segment |
| **JRC AIRE** (JRC145832, 2024) | EU-native AI exposure | ISCO-3 | Methodology yes; dataset access unclear | Validation only |
| **OSKA AI uuring** | Qualitative Estonia-specific findings | Sectoral / role archetypes | Yes (PDFs only) | Qualitative overlay / sanity check |
| **OSKA 69 ametialagrupid** | Estonian professional groups | Per-group narrative; ISCO crosswalk not public | Yes (web pages) | Tier 2 only — readability for Estonian stakeholders |

**Methodological note — LLM-rating instability:** Yin, Vu, Persico (NBER 2026, "How (un)Stable Are LLM Occupational Exposure Scores?") show poor inter-model agreement on LLM-annotated task exposure. This is a reason to anchor on (a) human-expert rated indices (ILO WP140, Felten) and (b) measured-usage data (AEI), rather than LLM-annotated exposure (Eloundou). It also implies we should treat AEI's *task-level classification* (which uses LLM annotation) with some caution while still valuing its *usage measurement* itself.

**Operational definition:**
- `exposure_baseline = ILO WP140 tier` (1–4, ISCO-08 native, human-expert rated)
- `augmentation_share, automation_share = AEI ratios per SOC code` (cross-walked from SOC → ISCO; default to OECD average where Estonian-specific data thin)
- `Opportunity_score = exposure_baseline × augmentation_share`
- `Risk_score = exposure_baseline × automation_share`
- Cross-validate against Cazzaniga et al. (IMF SDN 2024/001) complementarity-based scores; flag discrepancies.

### E. Classification Crosswalks (already aligned)

- **EMTAK ↔ NACE Rev. 2**: identical at digits 1–4 (EMTAK adds national level 5). Confirmed via vana.stat.ee/30845.
- **AK 2008 (Ametite klassifikaator) ↔ ISCO-08**: identical at digits 1–4 (AK adds national level 5 with Estonian job titles). Source: klassifikaatorid.stat.ee.
- **OSKA 69 ametialagrupid ↔ ISCO**: no public crosswalk file; OSKA's internal mapping is at ISCO-4 per CEDEFOP documentation. Would need either (i) a request to Kutsekoda, or (ii) a manual mapping pass using occupation names.

### F. Eurostat as Validation / Backstop

- **lfsa_eisn2**: Employment by NACE × ISCO at national and NUTS2 levels. Estonia = 1 NUTS2 (EE0) → not regionally useful, but provides annual national crosstabs for currency-adjusting RL21152 between censuses.

---

## Proposed Approach — Two Tiers

Tier 1 answers regional allocation with the minimum data needed, at the finest geographic detail possible. Tier 2 adds the dimensions required to actually design and deliver workshops.

### Tier 1 — ISCO-only matrix at sub-county granularity, with Opportunity + Risk axes

**Goal:** answer *"in each Estonian locality (down to municipality / city district), how many workers face high AI opportunity, and how many face high AI risk?"* — the input needed to allocate the 100,000-person training budget across the country.

**Step 1a — Pull RL21154** via the Statistics Estonia PXWeb API. This gives a long-format table: `(location, ISCO-4, sex) → employed persons`. ~245 location codes × ~51 ISCO categories.

**Step 1b — Build the ISCO crosswalks.**
- ISCO-4 → ISCO-3 (trivial truncation).
- Estonian AK 2008 ↔ ISCO-08 (identical at digits 1–4 per klassifikaatorid.stat.ee).
- ISCO-3 → SOC (for any score originally published in SOC). Standard BLS/ILO crosswalks exist.

**Step 1c — Attach the two AI-exposure axes.**
- Download ILO WP140 occupation tier table (ISCO-08 native) — this is the primary exposure baseline.
- Download Anthropic Economic Index from huggingface.co/datasets/Anthropic/EconomicIndex — extract per-SOC augmentation_share and automation_share.
- Crosswalk SOC → ISCO-3 (BLS/ILO crosswalk).
- For each ISCO-4 (or ISCO-3 where AEI granularity tops out): `Opportunity_score = ILO_tier × augmentation_share` ; `Risk_score = ILO_tier × automation_share`.
- Side columns for sanity: Felten AIOE, Cazzaniga IMF complementarity, Eloundou E1/E2 (note known LLM-rating instability), OSKA AI-uuring qualitative tier.

**Step 1d — Attach the OSKA demand-supply layer.** OSKA is not redundant with international AI-exposure data; it answers a *different* question (does Estonia need more workers in this occupation, regardless of AI?). For workshop allocation this is decisive:
- Map ISCO-4 → OSKA 69 ametialagrupid (manual ~1 day, or request crosswalk from Kutsekoda).
- For each ametialagrupp, attach OSKA's:
  - 10-year demand forecast (positions needed by 2035)
  - Annual graduate-supply forecast (VET + HE)
  - Shortage/surplus classification (CEDEFOP "Mismatch Priority Occupations" + OSKA's own tier)
- Use this as the **Demand_gap** column on the matrix. Workshop priority logic:
  - High Opportunity × Shortage = train more (double win)
  - High Risk × adjacent Shortage = reskill / pipeline transition
  - High Risk × Surplus = displacement support, not retention training

**Step 1e — Aggregate by location.** For each of the 245 locations (and at maakond rollups), compute:
- Total employed.
- Sum of `Opportunity score × employed` and `Risk score × employed` (employment-weighted exposure).
- Headcount in top-quartile Opportunity occupations and top-quartile Risk occupations.
- Headcount in shortage-flagged occupations (OSKA Demand_gap).
- Top 10 occupations by Opportunity, by Risk, and by Demand_gap, with headcounts.

**Step 1f — Output.** Excel workbook:
- Tab 1: Maakond-level summary (15 rows + totals).
- Tab 2: Municipality / district level (245 rows).
- Tab 3: Long-format detail (location × ISCO × all three axes).
- Tab 4: ISCO master table with scores, OSKA-69 labels, and OSKA forecast figures (Tier 2 prep).
- Plus a 2-page memo explaining the three axes (Opportunity, Risk, Demand_gap), the score sources, and how to read the numbers for workshop allocation.

This is buildable in roughly 1–2 days once data and scores are downloaded (extra day for the ISCO → OSKA-69 crosswalk).

### Tier 2 — Full matrix (workshop design and delivery)

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

## Critical Files / Resources

- **Source data** (no local file yet):
  - https://andmed.stat.ee/api/v1/et/stat/rahvaloendus/rel2021/rahvastiku-majanduslik-aktiivsus/hoivatud-ja-tooranne/RL21154.px (Tier 1 spine: ISCO × sub-county)
  - https://andmed.stat.ee/api/v1/et/stat/rahvaloendus/rel2021/rahvastiku-majanduslik-aktiivsus/hoivatud-ja-tooranne/RL21147.px (EMTAK × sub-county)
  - https://andmed.stat.ee/api/v1/et/stat/rahvaloendus/rel2021/rahvastiku-majanduslik-aktiivsus/hoivatud-ja-tooranne/RL21152.px (Tier 2 spine: EMTAK × ISCO × maakond)
  - https://andmed.stat.ee/api/v1/et/stat (PXWeb API root for all tables)
  - https://huggingface.co/datasets/Anthropic/EconomicIndex (Anthropic AEI — measured Claude usage, augmentation/automation split; CC-BY)
  - https://www.anthropic.com/economic-index (AEI landing page + reports)
  - https://www.ilo.org/publications/generative-ai-and-jobs-refined-global-index-occupational-exposure (ILO WP140 ISCO-08 native scores, primary baseline)
  - https://www.imf.org/-/media/files/publications/sdn/2024/english/sdnea2024001.pdf (Cazzaniga et al. IMF SDN 2024/001 — updated Pizzinelli/Felten complementarity)
  - https://github.com/AIOE-Data/AIOE (Felten AIOE scores — sanity check)
  - https://github.com/openai/GPTs-are-GPTs (Eloundou E1/E2/E3 scores — demoted, see Yin et al. 2026)
  - https://www.nber.org/papers/w35110 (Yin, Vu, Persico — LLM-rating instability warning)
  - https://uuringud.oska.kutsekoda.ee/uuringud/ai-uuring (OSKA AI report — qualitative overlay)
  - https://oska.kutsekoda.ee/naidikulehed/?tab=ametialagrupid-tab (69 ametialagrupid, Tier 2)
  - https://oskused.ee/ametid (~400 occupations for OSKA→ISCO mapping)
  - https://klassifikaatorid.stat.ee (AK 2008 ↔ ISCO-08 classifier)
  - https://vana.stat.ee/30845 (EMTAK 2008 ↔ NACE Rev. 2)

- **To be created in this project directory** (when execution phase begins):
  - `data/raw/` — pulled tables
  - `data/crosswalks/isco4_to_oska69.csv` — manual mapping
  - `data/matrix.csv` — long-format output
  - `methodology.md` — assumptions memo

## Verification (for the execution phase, not now)

When the matrix is actually built:
1. **Marginal checks**: sum over (EMTAK, ISCO) per county should match TT2419 / TT241 totals within ~2%.
2. **Total check**: grand total ≈ Statistics Estonia's published employed-persons figure for the reference year (~640k).
3. **Sanity spots**: Ida-Viru should show high concentration in EMTAK B/C (mining/manufacturing); Harju in J/M (ICT/professional); Tartu in P/Q (education/health) relative to its size.
4. **AI-exposure sanity**: high-exposure occupations (ISCO 4 — clerical support; 2 — professionals in certain sub-fields) should align with OSKA's qualitative findings on which ametialagrupid are flagged "critically affected."

## Open Questions

1. **If Pizzinelli complementarity scores are not in clean tabular form**, fallback is to derive complementarity from O*NET task attributes (social, physical, ethical context) following the published methodology, or substitute the OECD Lassébie–Quintini skill-automatability data. Either is defensible. Worth knowing the user's tolerance for methodological work vs picking a single-axis fallback (ILO WP140 only).
2. **Output naming.** The two axes can be called Opportunity/Risk, Augmentation/Substitution, or Complement/Replace. The terminology matters for stakeholder framing.
3. **Tier 2 trigger.** Build Tier 2 immediately after Tier 1, or wait until Tier 1 is reviewed and we know whether workshop design needs the full matrix at all?
4. **Kutsekoda outreach (Tier 2 only).** Request internal ISCO-4 → 69 ametialagrupid mapping vs build it manually. Saves ~1 day.
5. **Currency adjustment (Tier 2 only).** Use 2021 Census as-is, or rescale to 2025 totals?
