# Score models registry

| model | taxonomy | exposure source | aug/auto source | added | notes |
|---|---|---|---|---|---|
| felten_aei | isco2 | Felten et al. AIOE (Appendix A) | Anthropic Economic Index March 2026 (1P API) | 2026-05-15 | v1 baseline; collaboration patterns per AEI Feb 2025 paper |
| felten_aei_isco4 | isco4 | Felten et al. AIOE (Appendix A) | Anthropic Economic Index March 2026 (1P API) | 2026-05-17 | same recipe as felten_aei but native at ISCO-4; ISCO-2 → ISCO-1 → global fallback chain for low-confidence cells |
| ilo_wp140 | isco4 | ILO WP140 / Gmyrek et al. 2025 (4-class categorical) | derived from the same class | 2026-05-17 | Categorical classes mapped to numeric: Not Affected=0, Big Unknown=0.33, Augmentation Potential=0.66, Automation Potential=1.0. Source: github.com/pgmyrek/GenAI_Exposure_Tree_Plot |
| demirev_ai_products | isco4 | Demirev 2026 (Industry & Innovation, AI-products method) | Demirev ESCO aug/auto scores aggregated to ISCO-4 | 2026-05-17 | continuous slot originally targeted for Cazzaniga IMF SDN 2024/001 — IMF data is PDF-only and not retrievable from the build sandbox. Source: github.com/demirev/ai-products |
| jrc_casas | isco3 | JRC Casas et al. 2025/26 (JRC145832) | — | stub | needs manual CSV drop at data/raw/jrc_casas/jrc_casas_isco3.csv per data/raw/jrc_casas/README.md |

## How to add a new model
1. Implement an aggregator function in `src/fetch_ai_scores.py` that emits rows with `model = <new_id>` and `taxonomy = <one of KNOWN_TAXONOMIES>`, one per (code, metric).
2. Wire it into the `MODELS = {...}` dict at the top of the file.
3. Re-run `python3 src/fetch_ai_scores.py`. New rows are appended; existing models are not touched.
4. If the new model uses a taxonomy not yet bridged to any weight scenario's taxonomy, add a crosswalk file in `data/crosswalks/` and document it in `CROSSWALKS.md`.
5. Add a row to this table.
