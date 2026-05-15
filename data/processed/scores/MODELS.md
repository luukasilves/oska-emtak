# Score models registry

| model | taxonomy | exposure source | aug/auto source | added | notes |
|---|---|---|---|---|---|
| felten_aei | isco2 | Felten et al. AIOE (Appendix A) | Anthropic Economic Index March 2026 (1P API) | 2026-05-15 | v1 baseline; collaboration patterns per AEI Feb 2025 paper |

## How to add a new model
1. Implement an aggregator function in `src/fetch_ai_scores.py` that emits rows with `model = <new_id>` and `taxonomy = <one of KNOWN_TAXONOMIES>`, one per (code, metric).
2. Wire it into the `MODELS = {...}` dict at the top of the file.
3. Re-run `python3 src/fetch_ai_scores.py`. New rows are appended; existing models are not touched.
4. If the new model uses a taxonomy not yet bridged to any weight scenario's taxonomy, add a crosswalk file in `data/crosswalks/` and document it in `CROSSWALKS.md`.
5. Add a row to this table.
