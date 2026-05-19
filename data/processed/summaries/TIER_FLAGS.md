# Tier flags — `tier_flags_isco4.csv`

Per-ISCO-4 cross-model agreement summary built by `src/build_tier_flags.py`. One
row per ISCO-4 code present in either the scores or the Estonian employment data.

## Why two tier columns

Inter-model agreement is the central methodological problem in AI-exposure
allocation: pairwise Spearman across our three ISCO-4-native models ranges
0.29–0.46 on exposure rankings, and ~0 on the augmentation/automation split.
This matches the published consensus (Tolan/JRC, Yale Budget Lab, IADB GENOE,
Yin/Vu/Persico NBER 2026): single-model allocation is indefensible. The
recommended response is ensemble + dispersion + tier framing.

We expose **two tier labelings side-by-side** rather than commit to one:

- **`tier_label_quintile`** — counts how many of the 3 models place the code in
  their top/bottom quintile. Transparent, easy to defend ("top-quintile in 2 of
  3 independent measures"). Picks ~33 Robust High occupations.
- **`tier_label_ensemble`** — thresholds on standardized ensemble z-score
  (`ensemble_z_mean ≥ 1.0` for Robust High, with dispersion check). Smoother
  boundary but uses free parameters. Stricter — picks ~7 Robust High.

Both labelings share the same underlying `ensemble_z_mean` and `ensemble_z_sd`.
The difference is whether the tier boundary is set by count of models (quintile)
or by position on the standardized axis (ensemble).

## Tier rules

### `tier_label_quintile`

| Tier | Rule |
|---|---|
| Robust High | `top_quintile_count ≥ 2` AND `ensemble_z_sd ≤ median` (of top-quintile codes) |
| Contested High | `top_quintile_count ≥ 1` and not Robust High |
| Mixed | neither top nor bottom quintile in any model |
| Consensus Low | `bottom_quintile_count ≥ 2` |
| Insufficient coverage | `n_models < 2` |

### `tier_label_ensemble`

| Tier | Rule |
|---|---|
| Robust High | `ensemble_z_mean ≥ +1.0` AND `ensemble_z_sd ≤ p50` |
| Contested High | `ensemble_z_mean ≥ +0.5` and not Robust High |
| Mixed | `-0.5 < ensemble_z_mean < +0.5` |
| Consensus Low | `ensemble_z_mean ≤ -1.0` |
| Insufficient coverage | `n_models < 2` |

## What's deliberately omitted

- **Augmentation/automation split.** Cross-model Spearman is ~0 on these
  metrics; collapsing them into a tier label would be a political choice in
  analytical clothing. Raw per-model values remain in `scores_long.csv`.
- **OSKA shortage tier.** Requires the OSKA-69 ↔ ISCO-4 crosswalk currently
  flagged as missing (see `data/crosswalks/isco4_to_oska69.README.md`). Phase 2.

## Local-demand overlay

The Töötukassa national labour-balance and labour-demand indicators (1–5 scale)
are joined as `tootukassa_balance_national` and `tootukassa_demand_national`.
These are independent of the AI exposure tier and meant to be combined
downstream — e.g. "Robust High AI exposure × shortage" warrants different
treatment than "Robust High × surplus".

## Notes column

- `no_score` — code present in employment data but no model scored it
- `partial_coverage` — fewer than 3 models scored this code
- `no_employment_signal` — code is in the AI-exposure data but has 0 Estonian
  employment in palgad.stat.ee (either suppressed under-20 cells everywhere, or
  the ISCO code doesn't apply to Estonia)

## Verification (last run)

- 438 rows; 2 with insufficient coverage (single-model)
- Spearman of each model's z vs `ensemble_z_mean`: felten 0.83, ilo 0.76, demirev 0.70 (all above the ρ ≥ 0.5 sanity threshold)
- Tier distribution under quintile rule: 33 Robust High / 146 Contested High / 225 Mixed / 32 Consensus Low / 2 Insufficient
- Tier distribution under ensemble rule: 7 Robust High / 101 Contested High / 303 Mixed / 25 Consensus Low / 2 Insufficient
