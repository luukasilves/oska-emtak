"""Build per-ISCO-4 cross-model agreement / tier-flags table.

Post-processes data/processed/scores/scores_long.csv to summarise where the three
ISCO-4-native AI-exposure models (felten_aei_isco4, ilo_wp140, demirev_ai_products)
agree on which occupations are highly AI-exposed and where they diverge. Joins
Estonian employment headcounts (palgad.stat.ee) and the Töötukassa labour-balance
signal at ISCO-4.

Why two tier columns: literature consensus (Tolan/JRC, IADB GENOE, Yale Budget Lab,
Yin/Vu/Persico NBER 2026) is that single-model allocation is indefensible; the
recommended response is ensemble + dispersion. We compute two tier framings:
  - tier_label_quintile: counts how many of the 3 models place the code in their
    top/bottom quintile. Transparent, easy to defend politically.
  - tier_label_ensemble: thresholds on standardized ensemble z-score + dispersion.
    Smoother, but uses free parameters (+/-1.0 sigma boundaries).

Augmentation/automation split is intentionally NOT collapsed into a tier label —
cross-model Spearman on that axis is ~0, so any single labeling would be a
political choice masquerading as analytics. Raw per-model values stay in
scores_long.csv for downstream inspection.

OSKA shortage tier is deferred to a follow-up build (needs the OSKA-69 ↔ ISCO-4
crosswalk currently flagged as missing — see data/crosswalks/isco4_to_oska69.README.md).

Output: data/processed/summaries/tier_flags_isco4.csv
"""

from pathlib import Path

import numpy as np
import pandas as pd

from common import (
    SCORES_DIR, SUMMARIES_DIR, RAW,
    isco_parent, load_isco_labels,
)


ISCO4_MODELS = ["felten_aei_isco4", "ilo_wp140", "demirev_ai_products"]


def _load_scores() -> pd.DataFrame:
    df = pd.read_csv(SCORES_DIR / "scores_long.csv",
                     dtype={"taxonomy": str, "code": str})
    df = df[(df["taxonomy"] == "isco4") & (df["metric"] == "exposure")]
    df = df[df["model"].isin(ISCO4_MODELS)].copy()
    df["code"] = df["code"].str.zfill(4)
    pv = df.pivot_table(index="code", columns="model", values="value", aggfunc="first")
    pv = pv.reindex(columns=ISCO4_MODELS)
    return pv


def _load_employment() -> pd.Series:
    """National ISCO-4 employment from palgad.stat.ee.

    The raw file suppresses cells <20 workers (NaN). We sum across gender at the
    national (Kogu Eesti) row; suppressed cells become 0, so this is a lower-bound
    headcount, which is the conservative choice for allocation weighting.
    """
    w = pd.read_csv(RAW / "palgad_stat_ee" / "workers_long.csv")
    nat = w[(w["county_name"] == "Kogu Eesti") & (w["gender"].isin(["M", "F"]))]
    nat = nat.assign(count=nat["count"].fillna(0),
                     code=nat["isco4"].astype(int).astype(str).str.zfill(4))
    return nat.groupby("code")["count"].sum().astype(int)


def _load_barometer_national() -> pd.DataFrame:
    """National Töötukassa indicator per ISCO-4.

    Returns columns: tootukassa_balance_national, tootukassa_demand_national.
    Indicator scale (per Töötukassa): 1-5 for LABOUR_BALANCE
    (1=major surplus, 3=balanced, 5=major shortage); LABOUR_DEMAND
    (1=much less, 3=same, 5=much more demand).
    """
    b = pd.read_csv(RAW / "tootukassa_barometer" / "barometer_long.csv")
    nat = b[b["location_name"] == "Kogu Eesti"].copy()
    nat["code"] = nat["isco4"].astype(int).astype(str).str.zfill(4)
    pv = nat.pivot_table(index="code", columns="rating_type",
                         values="indicator", aggfunc="first")
    pv = pv.rename(columns={
        "LABOUR_BALANCE": "tootukassa_balance_national",
        "LABOUR_DEMAND": "tootukassa_demand_national",
    })
    return pv


def _quintile(series: pd.Series) -> pd.Series:
    """Return 1..5 quintile rank ignoring NaN (1=lowest, 5=highest exposure).

    Uses rank-percentile rather than pd.qcut so ties at bin edges don't collapse
    the bins (qcut + duplicates='drop' would silently produce <5 buckets).
    """
    pct = series.rank(method="average", pct=True)
    q = np.ceil(pct * 5).clip(1, 5).astype("Int64")
    return q


def _zscore(series: pd.Series) -> pd.Series:
    mu = series.mean()
    sd = series.std(ddof=0)
    return (series - mu) / sd if sd > 0 else series * 0


def _tier_label_quintile(top_count: int, bot_count: int,
                         z_sd: float, top_sd_median: float, n_models: int):
    if n_models < 2:
        return "Insufficient coverage"
    if top_count >= 2 and (pd.notna(z_sd) and z_sd <= top_sd_median):
        return "Robust High"
    if top_count >= 1:
        return "Contested High"
    if bot_count >= 2:
        return "Consensus Low"
    return "Mixed"


def _tier_label_ensemble(z_mean: float, z_sd: float, z_sd_p50: float, n_models: int):
    if n_models < 2 or pd.isna(z_mean):
        return "Insufficient coverage"
    if z_mean >= 1.0 and pd.notna(z_sd) and z_sd <= z_sd_p50:
        return "Robust High"
    if z_mean >= 0.5:
        return "Contested High"
    if z_mean <= -1.0:
        return "Consensus Low"
    if -0.5 < z_mean < 0.5:
        return "Mixed"
    return "Mixed"


def build():
    scores = _load_scores()
    employment = _load_employment()
    barometer = _load_barometer_national()
    labels = load_isco_labels()

    code_idx = sorted(set(scores.index) | set(employment.index))
    out = pd.DataFrame(index=code_idx)
    out.index.name = "isco4_code"

    out["isco4_label"] = out.index.map(labels[4].get)
    out["isco2_code"] = [isco_parent(c, 2) for c in out.index]
    out["isco2_label"] = out["isco2_code"].map(labels[2].get)
    out["employment_estonia"] = out.index.map(employment).fillna(0).astype(int)

    for m in ISCO4_MODELS:
        out[f"{m}_exposure"] = out.index.map(scores[m] if m in scores.columns else {})

    z_cols = {}
    q_cols = {}
    for m in ISCO4_MODELS:
        exp = out[f"{m}_exposure"]
        z = _zscore(exp.dropna())
        z = z.reindex(out.index)
        out[f"{m}_z"] = z
        z_cols[m] = z
        q = _quintile(exp.dropna())
        q = q.reindex(out.index)
        out[f"{m}_quintile"] = q
        q_cols[m] = q

    z_df = pd.DataFrame(z_cols)
    out["n_models"] = z_df.notna().sum(axis=1)
    out["ensemble_z_mean"] = z_df.mean(axis=1, skipna=True)
    out["ensemble_z_sd"] = z_df.std(axis=1, ddof=0, skipna=True)

    q_df = pd.DataFrame(q_cols)
    out["top_quintile_count"] = (q_df == 5).sum(axis=1).astype(int)
    out["bottom_quintile_count"] = (q_df == 1).sum(axis=1).astype(int)

    top_mask = out["top_quintile_count"] >= 2
    top_sd_median = out.loc[top_mask, "ensemble_z_sd"].median()
    z_sd_p50 = out["ensemble_z_sd"].median()

    out["tier_label_quintile"] = [
        _tier_label_quintile(t, b, sd, top_sd_median, n)
        for t, b, sd, n in zip(out["top_quintile_count"], out["bottom_quintile_count"],
                                out["ensemble_z_sd"], out["n_models"])
    ]
    out["tier_label_ensemble"] = [
        _tier_label_ensemble(m, sd, z_sd_p50, n)
        for m, sd, n in zip(out["ensemble_z_mean"], out["ensemble_z_sd"], out["n_models"])
    ]

    out = out.join(barometer, how="left")
    if "tootukassa_balance_national" not in out.columns:
        out["tootukassa_balance_national"] = pd.NA
    if "tootukassa_demand_national" not in out.columns:
        out["tootukassa_demand_national"] = pd.NA

    out["notes"] = ""
    out.loc[out["n_models"] == 0, "notes"] = "no_score"
    out.loc[(out["n_models"] >= 1) & (out["n_models"] < 3), "notes"] = "partial_coverage"
    out.loc[out["employment_estonia"] == 0, "notes"] += "|no_employment_signal"

    out = out.reset_index()
    out = out[[
        "isco4_code", "isco4_label", "isco2_code", "isco2_label",
        "employment_estonia",
        "felten_aei_isco4_exposure", "ilo_wp140_exposure", "demirev_ai_products_exposure",
        "felten_aei_isco4_z", "ilo_wp140_z", "demirev_ai_products_z",
        "felten_aei_isco4_quintile", "ilo_wp140_quintile", "demirev_ai_products_quintile",
        "ensemble_z_mean", "ensemble_z_sd", "n_models",
        "top_quintile_count", "bottom_quintile_count",
        "tier_label_quintile", "tier_label_ensemble",
        "tootukassa_balance_national", "tootukassa_demand_national",
        "notes",
    ]]

    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SUMMARIES_DIR / "tier_flags_isco4.csv"
    out.to_csv(out_path, index=False)
    print(f"Wrote {out_path}  ({len(out):,} rows)")

    print("\nTier distribution (quintile rule):")
    print(out["tier_label_quintile"].value_counts())
    print("\nTier distribution (ensemble rule):")
    print(out["tier_label_ensemble"].value_counts())

    covered = out[out["n_models"] >= 2]
    rho = covered[[f"{m}_z" for m in ISCO4_MODELS] + ["ensemble_z_mean"]].corr(method="spearman")
    print("\nSpearman correlation of each model's z vs ensemble_z_mean:")
    print(rho["ensemble_z_mean"].round(3))


if __name__ == "__main__":
    build()
