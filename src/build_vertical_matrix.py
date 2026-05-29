"""Build the occupation-vertical × maakond AI-exposure coverage matrix.

Standalone post-processor (modeled on src/build_tier_flags.py). Reads:
  - data/raw/palgad_stat_ee/workers_long.csv         (ISCO-4 × maakond × gender)
  - data/processed/summaries/tier_flags_isco4.csv    (cross-model consensus exposure)
  - data/crosswalks/isco4_to_vertical.csv            (editable vertical map)

Produces (idempotent, regenerated each run):
  - data/processed/summaries/vertical_county_matrix_long.csv          (tidy)
  - data/processed/matrices/matrix_vertical_county_2025q4_palgad.csv  (wide, estimate)
  - data/processed/matrices/matrix_vertical_county_2025q4_palgad_lower.csv (wide, floor)
  - output/charts/_vertical_county/vertical_county_heatmap.png        (estimate heatmap)
  - output/charts/_vertical_county/vertical_county_heatmap_suppression.png
  - output/charts/_vertical_county/vertical_county_choropleths.png    (small-multiples)
  - output/vertical_county_matrix.xlsx                                (multi-sheet)

Suppression method (residual-constrained imputation):
  palgad.stat.ee suppresses cells <20 workers; this happens per *gender* before
  export. For each (isco4, county) we count `n_hidden` gender-components missing
  (each ∈ [0,19]). For each isco4 we know the national total N from the county=
  "all" row. The residual R = max(N − Σknown_counties, 0) must lie entirely in
  the hidden components, so per-component estimate ĉ = clamp(R / H, 0, 19) where
  H = Σ n_hidden. Cell estimate = known + n_hidden × ĉ. Bounds: lower = known
  floor; upper = known + 19 × n_hidden (theoretical ceiling).

Run: python3 src/build_vertical_matrix.py [--top N] [--no-xlsx] [--no-choropleth]
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import (
    RAW,
    CROSSWALKS,
    SUMMARIES_DIR,
    MATRICES_DIR,
    CHARTS_DIR,
    ROOT,
)


# 15 maakonnad in canonical (employment-descending-ish) order, matching dashboard
COUNTY_ORDER = [
    ("harju",      "Harju maakond"),
    ("tartu",      "Tartu maakond"),
    ("ida_viru",   "Ida-Viru maakond"),
    ("parnu",      "Pärnu maakond"),
    ("laane_viru", "Lääne-Viru maakond"),
    ("viljandi",   "Viljandi maakond"),
    ("rapla",      "Rapla maakond"),
    ("voru",       "Võru maakond"),
    ("jarva",      "Järva maakond"),
    ("saare",      "Saare maakond"),
    ("jogeva",     "Jõgeva maakond"),
    ("valga",      "Valga maakond"),
    ("polva",      "Põlva maakond"),
    ("laane",      "Lääne maakond"),
    ("hiiu",       "Hiiu maakond"),
]
COUNTY_SLUGS = [c for c, _ in COUNTY_ORDER]
COUNTY_NAMES = dict(COUNTY_ORDER)
SUPP_CAP = 19              # each suppressed gender-cell <20 → max 19
SUPP_MID = 9.5             # equal-split midpoint per hidden component (fallback)

# Output paths
LONG_OUT = SUMMARIES_DIR / "vertical_county_matrix_long.csv"
WIDE_EST_OUT = MATRICES_DIR / "matrix_vertical_county_2025q4_palgad.csv"
WIDE_LOWER_OUT = MATRICES_DIR / "matrix_vertical_county_2025q4_palgad_lower.csv"
CHART_DIR = CHARTS_DIR / "_vertical_county"
XLSX_OUT = ROOT / "output" / "vertical_county_matrix.xlsx"

# Matplotlib defaults, matching src/visualize.py
plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "axes.titlesize": 12,
    "axes.labelsize": 10,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "savefig.dpi": 140,
    "savefig.bbox": "tight",
})
C_EXP = "#6A4C93"


# ── Loaders ──────────────────────────────────────────────────────────────────────────

def _load_workers_county() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (cells_df, national_df).

    cells_df: one row per (isco4, county) over the 15 real counties, with columns
        isco4, county, county_name, name_et, known, n_hidden.
    national_df: one row per isco4 with columns
        isco4, name_et, national_known, national_n_hidden.

    `known` sums present numeric M/F counts; `n_hidden` = 2 − (count of present
    numeric M/F rows). A lone `gender="all"` empty row implies both genders hidden
    (n_hidden = 2). Same logic for national rows (county="all").
    """
    path = RAW / "palgad_stat_ee" / "workers_long.csv"
    df = pd.read_csv(path, dtype={"isco4": str})
    df["isco4"] = df["isco4"].str.zfill(4)
    df["count_num"] = pd.to_numeric(df["count"], errors="coerce")
    df["gender"] = df["gender"].astype(str)

    # Per (isco4, county): keep only M/F numeric rows for `known`; count present.
    mf = df[df["gender"].isin(["M", "F"])].copy()
    mf_present = mf[mf["count_num"].notna()]
    known = (mf_present.groupby(["isco4", "county"])["count_num"]
                       .sum().rename("known"))
    n_present = (mf_present.groupby(["isco4", "county"])["gender"]
                           .nunique().rename("n_present"))

    # All (isco4, county) pairs that appear in the raw file (whether suppressed or not)
    all_pairs = df.drop_duplicates(["isco4", "county"])[["isco4", "county"]]
    name_map = (df.drop_duplicates("isco4").set_index("isco4")["name_et"]
                  .astype(str).to_dict())

    cells = all_pairs.merge(known, on=["isco4", "county"], how="left") \
                     .merge(n_present, on=["isco4", "county"], how="left")
    cells["known"] = cells["known"].fillna(0).astype(int)
    cells["n_present"] = cells["n_present"].fillna(0).astype(int)
    cells["n_hidden"] = (2 - cells["n_present"]).clip(lower=0).astype(int)
    cells["name_et"] = cells["isco4"].map(name_map)

    # Split national vs counties
    nat = cells[cells["county"] == "all"].copy()
    nat = nat.rename(columns={"known": "national_known",
                              "n_hidden": "national_n_hidden"})
    nat = nat[["isco4", "name_et", "national_known", "national_n_hidden"]]

    cty = cells[cells["county"] != "all"].copy()
    cty = cty[cty["county"].isin(COUNTY_SLUGS)]
    cty["county_name"] = cty["county"].map(COUNTY_NAMES)
    cty = cty[["isco4", "name_et", "county", "county_name", "known", "n_hidden"]]

    return cty, nat


def _load_vertical_map() -> pd.DataFrame:
    path = CROSSWALKS / "isco4_to_vertical.csv"
    df = pd.read_csv(path, dtype={"from_code": str, "to_code": str})
    df["from_code"] = df["from_code"].str.zfill(4)
    if "weight" not in df.columns:
        df["weight"] = 1.0
    df["weight"] = df["weight"].fillna(1.0).astype(float)
    # First label per vertical wins
    label_first = (df.drop_duplicates("to_code")
                     .set_index("to_code")["vertical_label"].astype(str).to_dict())
    df["vertical_label"] = df["to_code"].map(label_first)
    # Validate weight sums per from_code
    wsum = df.groupby("from_code")["weight"].sum()
    bad = wsum[(wsum - 1.0).abs() > 0.01]
    if len(bad):
        warnings.warn(
            f"{len(bad)} ISCO-4 codes have weights not summing to 1.0; first 5: "
            f"{bad.head().to_dict()}"
        )
    return df.rename(columns={"from_code": "isco4", "to_code": "vertical_id"}) \
             [["isco4", "vertical_id", "vertical_label", "weight"]]


def _load_exposure() -> pd.DataFrame:
    path = SUMMARIES_DIR / "tier_flags_isco4.csv"
    df = pd.read_csv(path, dtype={"isco4_code": str})
    df["isco4_code"] = df["isco4_code"].str.zfill(4)
    cols = ["isco4_code", "ensemble_z_mean", "employment_estonia",
            "tier_label_ensemble", "n_models"]
    return df[cols].rename(columns={"isco4_code": "isco4"})


# ── Imputation ───────────────────────────────────────────────────────────────────────

def _impute_suppressed(cells: pd.DataFrame, national: pd.DataFrame) -> pd.DataFrame:
    """Add per-cell people_lower/estimate/upper using residual-constrained imputation.

    Per isco4:
        N = national_known (lower bound on national; flag if national_n_hidden > 0)
        K = Σ_county known
        H = Σ_county n_hidden
        R = max(N − K, 0)
        ĉ = clamp(R / H, 0, SUPP_CAP)  if H > 0 else 0
    Per cell:
        people_lower    = known
        people_estimate = known + n_hidden × ĉ
        people_upper    = known + SUPP_CAP × n_hidden
    """
    sums = (cells.groupby("isco4")
                 .agg(known_sum=("known", "sum"),
                      hidden_sum=("n_hidden", "sum"))
                 .reset_index())
    sums = sums.merge(national, on="isco4", how="left")
    sums["national_known"] = sums["national_known"].fillna(0).astype(int)
    sums["national_n_hidden"] = sums["national_n_hidden"].fillna(0).astype(int)
    sums["residual"] = (sums["national_known"] - sums["known_sum"]).clip(lower=0)

    # Per-component estimate, capped at SUPP_CAP
    ratio = np.where(sums["hidden_sum"] > 0,
                     sums["residual"] / sums["hidden_sum"].replace(0, np.nan),
                     0.0)
    sums["per_component_raw"] = ratio
    sums["per_component"] = np.clip(np.nan_to_num(ratio, nan=0.0), 0.0, SUPP_CAP)
    # National under-known flag: residual/H > cap means hidden cells can't absorb
    # all the residual → national itself is gender-suppressed somewhere.
    sums["national_under_known"] = (
        (sums["national_n_hidden"] > 0) | (sums["per_component_raw"] > SUPP_CAP + 0.01)
    )

    merged = cells.merge(
        sums[["isco4", "per_component", "national_known",
              "national_n_hidden", "national_under_known"]],
        on="isco4", how="left",
    )
    merged["people_lower"] = merged["known"]
    merged["people_estimate"] = (
        merged["known"] + merged["n_hidden"] * merged["per_component"]
    )
    merged["people_upper"] = merged["known"] + SUPP_CAP * merged["n_hidden"]
    return merged, sums


# ── Aggregation to vertical ──────────────────────────────────────────────────────────

def _aggregate_to_vertical(cells: pd.DataFrame, vmap: pd.DataFrame) -> pd.DataFrame:
    """Sum cells × weights into (vertical × county) rows."""
    j = cells.merge(vmap, on="isco4", how="inner")
    for col in ("people_lower", "people_estimate", "people_upper"):
        j[col] = j[col] * j["weight"]
    j["known_w"] = j["known"] * j["weight"]
    j["n_hidden_w"] = j["n_hidden"] * j["weight"]
    j["has_data"] = (j["known"] > 0).astype(int)

    agg = (j.groupby(["vertical_id", "vertical_label", "county", "county_name"])
            .agg(people_lower=("people_lower", "sum"),
                 people_estimate=("people_estimate", "sum"),
                 people_upper=("people_upper", "sum"),
                 n_hidden=("n_hidden_w", "sum"),
                 n_isco4_total=("isco4", "nunique"),
                 n_isco4_with_data=("has_data", "sum"))
            .reset_index())
    agg["suppression_share"] = np.where(
        agg["people_upper"] > 0,
        (agg["people_upper"] - agg["people_lower"]) / agg["people_upper"],
        0.0,
    )
    return agg


# ── Ranking ──────────────────────────────────────────────────────────────────────────

def _rank_verticals(vmap: pd.DataFrame, exposure: pd.DataFrame) -> pd.DataFrame:
    """Employment-weighted mean of ensemble_z_mean per vertical; sort desc.

    Weight = national employment (`employment_estonia` from tier_flags_isco4).
    Codes missing an ensemble_z_mean are excluded from the weighting (no zero
    imputation), matching build_tier_flags's n_models-aware philosophy.
    """
    j = vmap.merge(exposure, on="isco4", how="left")
    j["w"] = j["employment_estonia"].fillna(0) * j["weight"]
    # Tier dominance
    tier_counts = (j.dropna(subset=["tier_label_ensemble"])
                    .groupby(["vertical_id", "tier_label_ensemble"])["isco4"]
                    .nunique().unstack(fill_value=0))
    tier_counts.columns = [f"n_{c.lower().replace(' ', '_')}"
                           for c in tier_counts.columns]

    # Weighted ensemble z and national employment per vertical
    def _wmean(group: pd.DataFrame) -> float:
        m = group["ensemble_z_mean"]
        w = group["w"].where(m.notna(), 0)
        if w.sum() <= 0:
            return float(m.mean()) if m.notna().any() else np.nan
        return float((m.fillna(0) * w).sum() / w.sum())

    rows = []
    for vid, g in j.groupby("vertical_id"):
        rows.append({
            "vertical_id": vid,
            "vertical_label": g["vertical_label"].iloc[0],
            "vertical_ensemble_z": _wmean(g),
            "vertical_employment_national": int(
                (g["employment_estonia"].fillna(0) * g["weight"]).sum()
            ),
            "n_isco4_in_vertical": g["isco4"].nunique(),
            "n_isco4_with_z": int(g["ensemble_z_mean"].notna().sum()),
        })
    rank = pd.DataFrame(rows)
    rank = rank.join(tier_counts, on="vertical_id")
    rank = rank.fillna({c: 0 for c in tier_counts.columns})

    # Dominant tier label
    if not tier_counts.empty:
        rank["tier_label_dominant"] = tier_counts.idxmax(axis=1).reindex(
            rank["vertical_id"].values).fillna("").values
        rank["tier_label_dominant"] = (
            rank["tier_label_dominant"].str.replace("n_", "", regex=False)
                                       .str.replace("_", " ").str.title()
        )
    else:
        rank["tier_label_dominant"] = ""

    rank = rank.sort_values(
        ["vertical_ensemble_z", "vertical_employment_national"],
        ascending=[False, False],
    ).reset_index(drop=True)
    rank["priority_rank"] = rank.index + 1
    return rank


# ── Output writers ───────────────────────────────────────────────────────────────────

def _write_long_csv(long: pd.DataFrame, rank: pd.DataFrame,
                    national_flags: pd.DataFrame) -> pd.DataFrame:
    out = long.merge(
        rank[["vertical_id", "priority_rank", "vertical_ensemble_z",
              "vertical_employment_national", "tier_label_dominant"]],
        on="vertical_id", how="left",
    )
    # Per-isco4 under-known flag aggregated to vertical (any contributing code flagged)
    flag_per_isco4 = national_flags.set_index("isco4")["national_under_known"]
    # We need it at vertical level: any isco4 in vertical flagged → vertical flagged.
    # Recompute via vmap (long doesn't carry isco4); attach via the rank loader's data
    # — simpler: derive from the cells_with_imp; left to caller — pass through.

    out = out.sort_values(["priority_rank", "county_name"]) \
             .reset_index(drop=True)
    cols = [
        "priority_rank", "vertical_id", "vertical_label", "county", "county_name",
        "people_lower", "people_estimate", "people_upper", "n_hidden",
        "n_isco4_total", "n_isco4_with_data", "suppression_share",
        "vertical_ensemble_z", "vertical_employment_national",
        "tier_label_dominant",
    ]
    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    out[cols].to_csv(LONG_OUT, index=False)
    print(f"Wrote {LONG_OUT}  ({len(out):,} rows)")
    return out[cols]


def _write_wide_csvs(long: pd.DataFrame, rank: pd.DataFrame, top: int):
    top_ids = rank.head(top)["vertical_id"].tolist()
    sub = long[long["vertical_id"].isin(top_ids)]
    meta_cols = ["priority_rank", "vertical_id", "vertical_label",
                 "vertical_ensemble_z", "vertical_employment_national",
                 "tier_label_dominant"]
    meta = rank[meta_cols].copy()
    for value_col, out_path, label in [
        ("people_estimate", WIDE_EST_OUT, "estimate (residual-constrained)"),
        ("people_lower",    WIDE_LOWER_OUT, "known lower bound"),
    ]:
        pv = sub.pivot_table(index="vertical_id", columns="county_name",
                             values=value_col, aggfunc="sum", fill_value=0)
        # Order columns by COUNTY_ORDER
        ordered_cols = [n for _, n in COUNTY_ORDER if n in pv.columns]
        pv = pv.reindex(columns=ordered_cols)
        # National column = sum across counties of the chosen value (estimate or lower)
        pv.insert(0, "Kogu Eesti (15 mk)", pv.sum(axis=1))
        pv = pv.round(0).astype(int)
        # Join metadata in priority order
        wide = meta.merge(pv, left_on="vertical_id", right_index=True, how="left")
        wide = wide.sort_values("priority_rank")
        MATRICES_DIR.mkdir(parents=True, exist_ok=True)
        wide.to_csv(out_path, index=False)
        print(f"Wrote {out_path}  ({len(wide)} verticals × {len(ordered_cols)} maakonnad, value={label})")


def _render_heatmap(long: pd.DataFrame, rank: pd.DataFrame, top: int):
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    top_ids = rank.head(top)["vertical_id"].tolist()
    sub = long[long["vertical_id"].isin(top_ids)]
    ordered_county_names = [n for _, n in COUNTY_ORDER]

    pv_est = sub.pivot_table(index="vertical_id", columns="county_name",
                              values="people_estimate", aggfunc="sum", fill_value=0)
    pv_est = pv_est.reindex(index=top_ids, columns=ordered_county_names, fill_value=0)
    # Re-label rows with priority rank + vertical label
    label_map = (rank.set_index("vertical_id")
                     .loc[top_ids, ["priority_rank", "vertical_label"]]
                     .apply(lambda r: f"{int(r['priority_rank']):2d}. {r['vertical_label']}",
                            axis=1))
    row_labels = label_map.values

    # ── 1. Estimate heatmap ──
    fig, ax = plt.subplots(figsize=(13, max(5, 0.34 * len(top_ids) + 2)))
    im = ax.imshow(pv_est.values, aspect="auto", cmap="Purples")
    ax.set_xticks(range(len(ordered_county_names)))
    ax.set_xticklabels([c.replace(" maakond", "") for c in ordered_county_names],
                       rotation=40, ha="right")
    ax.set_yticks(range(len(top_ids)))
    ax.set_yticklabels(row_labels)
    ax.set_title(
        "AI-mõjutatud ametivertikaalide hõive maakonniti — 2025 Q4\n"
        "(jääk-piirangu meetodiga; lahtri väärtus = inimeste arv, ümardatud)",
        fontsize=12, fontweight="bold",
    )
    # Annotate every cell with integer estimate
    vmax = pv_est.values.max() if pv_est.size else 1
    for i in range(pv_est.shape[0]):
        for j in range(pv_est.shape[1]):
            v = int(round(pv_est.values[i, j]))
            if v > 0:
                color = "white" if v > 0.6 * vmax else "black"
                ax.text(j, i, f"{v:,}", ha="center", va="center",
                        fontsize=7, color=color)
    cbar = plt.colorbar(im, ax=ax, fraction=0.022, pad=0.01)
    cbar.set_label("Hõive (hinnatud)", rotation=270, labelpad=15)
    fig.text(0.01, 0.005,
             "Allikas: palgad.stat.ee 2025 Q4 (suppressiooni jääk jaotatud rahvusvahelisest summast). "
             "AI-ekspositsioon: 3-mudeli konsensus (felten_aei_isco4, ILO WP140, demirev). "
             "Read: AI-konsensuse järjestus.",
             fontsize=7, color="#666")
    plt.savefig(CHART_DIR / "vertical_county_heatmap.png")
    plt.close(fig)
    print(f"  {CHART_DIR / 'vertical_county_heatmap.png'}")

    # ── 2. Suppression-share heatmap ──
    pv_supp = sub.pivot_table(index="vertical_id", columns="county_name",
                              values="suppression_share", aggfunc="mean", fill_value=0)
    pv_supp = pv_supp.reindex(index=top_ids, columns=ordered_county_names, fill_value=0)
    fig, ax = plt.subplots(figsize=(13, max(5, 0.34 * len(top_ids) + 2)))
    im = ax.imshow(pv_supp.values, aspect="auto", cmap="Oranges",
                   vmin=0, vmax=1)
    ax.set_xticks(range(len(ordered_county_names)))
    ax.set_xticklabels([c.replace(" maakond", "") for c in ordered_county_names],
                       rotation=40, ha="right")
    ax.set_yticks(range(len(top_ids)))
    ax.set_yticklabels(row_labels)
    ax.set_title(
        "Suppressiooni osakaal lahtri kohta — kui suur osa on imputeeritud\n"
        "(0 = täiesti teada, 1 = täielikult teoreetiline ülempiir)",
        fontsize=12, fontweight="bold",
    )
    for i in range(pv_supp.shape[0]):
        for j in range(pv_supp.shape[1]):
            v = pv_supp.values[i, j]
            if v > 0.05:
                color = "white" if v > 0.65 else "black"
                ax.text(j, i, f"{v*100:.0f}%", ha="center", va="center",
                        fontsize=7, color=color)
    cbar = plt.colorbar(im, ax=ax, fraction=0.022, pad=0.01)
    cbar.set_label("Suppressiooni osakaal", rotation=270, labelpad=15)
    plt.savefig(CHART_DIR / "vertical_county_heatmap_suppression.png")
    plt.close(fig)
    print(f"  {CHART_DIR / 'vertical_county_heatmap_suppression.png'}")


def _render_choropleths(long: pd.DataFrame, rank: pd.DataFrame, top: int = 12):
    """Render small-multiples maakond choropleth for the top-N verticals."""
    try:
        import geopandas as gpd
    except ImportError:
        print("  (geopandas not installed; skipping choropleth)")
        return
    geo_path = RAW / "maakond.geojson"
    if not geo_path.exists():
        print(f"  (no {geo_path}; skipping choropleth)")
        return
    gdf = gpd.read_file(geo_path)
    gdf["maakond"] = gdf["MNIMI"].str.replace(" maakond", "", regex=False)

    top_ids = rank.head(top)["vertical_id"].tolist()
    top_meta = rank.set_index("vertical_id").loc[top_ids]
    sub = long[long["vertical_id"].isin(top_ids)].copy()
    sub["maakond_short"] = sub["county_name"].str.replace(" maakond", "", regex=False)

    ncols = 3
    nrows = (len(top_ids) + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(4 * ncols, 3.5 * nrows))
    axes = np.atleast_2d(axes).reshape(nrows, ncols)
    for idx, vid in enumerate(top_ids):
        r, c = divmod(idx, ncols)
        ax = axes[r, c]
        cell = sub[sub["vertical_id"] == vid]
        merged = gdf.merge(cell[["maakond_short", "people_estimate"]],
                           left_on="maakond", right_on="maakond_short", how="left")
        merged.plot(column="people_estimate", ax=ax, cmap="Purples",
                    edgecolor="white", linewidth=0.4, legend=True,
                    legend_kwds={"shrink": 0.6})
        meta = top_meta.loc[vid]
        ax.set_title(
            f"{int(meta['priority_rank'])}. {meta['vertical_label']}\n"
            f"(z={meta['vertical_ensemble_z']:.2f}, "
            f"n={int(meta['vertical_employment_national']):,})",
            fontsize=9,
        )
        ax.set_axis_off()
    # Hide unused panels
    for idx in range(len(top_ids), nrows * ncols):
        r, c = divmod(idx, ncols)
        axes[r, c].set_axis_off()
    fig.suptitle(
        f"Top-{len(top_ids)} AI-mõjutatud ametivertikaali — hõive Eesti maakondades (2025 Q4)",
        fontsize=13, fontweight="bold", y=1.0,
    )
    plt.tight_layout()
    out = CHART_DIR / "vertical_county_choropleths.png"
    plt.savefig(out)
    plt.close(fig)
    print(f"  {out}")


def _write_xlsx(long: pd.DataFrame, rank: pd.DataFrame, vmap: pd.DataFrame,
                imputation_audit: pd.DataFrame, top: int):
    XLSX_OUT.parent.mkdir(parents=True, exist_ok=True)
    top_ids = rank.head(top)["vertical_id"].tolist()
    sub = long[long["vertical_id"].isin(top_ids)]

    def _pivot(value_col: str) -> pd.DataFrame:
        pv = sub.pivot_table(index="vertical_id", columns="county_name",
                             values=value_col, aggfunc="sum", fill_value=0)
        ordered_cols = [n for _, n in COUNTY_ORDER if n in pv.columns]
        pv = pv.reindex(index=top_ids, columns=ordered_cols).round(0).astype(int)
        meta = rank.set_index("vertical_id").loc[top_ids,
            ["priority_rank", "vertical_label", "vertical_ensemble_z",
             "vertical_employment_national", "tier_label_dominant"]]
        return meta.join(pv).reset_index()

    readme = pd.DataFrame({"info": [
        "Estonia AI-mõjutatud ametivertikaalide × maakonna hõive maatriks",
        "Allikas: palgad.stat.ee 2025 Q4 (ISCO-4 × maakond) + tier_flags_isco4 konsensus",
        "Suppressioon: <20 lahtrid jaotatud rahvusvahelise jäägi pealt (residual-constrained imputation).",
        "Lehed:",
        "  long                 — pikk vorm, kõik vertikaalid × kõik maakonnad",
        "  wide_estimate        — laia vorm, hinnatud (residual-constrained), top-N vertikaali",
        "  wide_lower           — laia vorm, teadaolev alampiir (konservatiivne)",
        "  ranking              — vertikaalide pingerida koos AI-ekspositsiooni ja koguarvuga",
        "  vertical_map         — ISCO-4 → vertikaal kaardistus (toimetatav data/crosswalks/isco4_to_vertical.csv)",
        "  imputation_audit     — per-ISCO-4 jääk, hinnang lahtri kohta, riigi-tase teadmatuse lipp",
        "",
        f"Top N kuvatav: {top}.  Maakondade arv: {len(COUNTY_ORDER)}.",
        f"Generated: pandas.to_datetime('now').isoformat()",
    ]})

    with pd.ExcelWriter(XLSX_OUT, engine="openpyxl") as xl:
        readme.to_excel(xl, sheet_name="README", index=False)
        long.to_excel(xl, sheet_name="long", index=False)
        _pivot("people_estimate").to_excel(xl, sheet_name="wide_estimate", index=False)
        _pivot("people_lower").to_excel(xl, sheet_name="wide_lower", index=False)
        rank.to_excel(xl, sheet_name="ranking", index=False)
        vmap.to_excel(xl, sheet_name="vertical_map", index=False)
        imputation_audit.to_excel(xl, sheet_name="imputation_audit", index=False)
    print(f"Wrote {XLSX_OUT}")


# ── Driver ───────────────────────────────────────────────────────────────────────────

def build(top: int = 50, xlsx: bool = True, choropleth: bool = True):
    cells, national = _load_workers_county()
    vmap = _load_vertical_map()
    exposure = _load_exposure()

    # Sanity: vertical map should cover (almost) every isco4 in the worker data
    missing = set(cells["isco4"]) - set(vmap["isco4"])
    if missing:
        warnings.warn(f"{len(missing)} ISCO-4 codes in workers but not in vertical map; "
                      f"they will be dropped. First 5: {sorted(missing)[:5]}")

    cells_imp, audit = _impute_suppressed(cells, national)
    long_raw = _aggregate_to_vertical(cells_imp, vmap)
    rank = _rank_verticals(vmap, exposure)
    long_out = _write_long_csv(long_raw, rank, audit)
    _write_wide_csvs(long_out, rank, top)
    print("\nCharts:")
    _render_heatmap(long_out, rank, top)
    if choropleth:
        _render_choropleths(long_out, rank, top=min(12, top))

    if xlsx:
        _write_xlsx(long_out, rank, vmap, audit, top)

    # ── Console summary ──
    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"Verticals: {len(rank)} total, top {top} shown in wide CSVs / heatmap")
    print(f"Counties:  {len(COUNTY_ORDER)} maakonnad")
    print(f"ISCO-4 codes mapped: {vmap['isco4'].nunique()}")
    print(f"National-under-known codes (residual exceeds 19×hidden): "
          f"{int(audit['national_under_known'].sum())}")
    nat_known_total = int(audit["national_known"].sum())
    cty_known_total = int(audit["known_sum"].sum())
    cty_upper_total = int(audit["known_sum"].sum()
                          + SUPP_CAP * audit["hidden_sum"].sum())
    cty_est_total = int(long_out["people_estimate"].sum())
    print(f"\nNational known (Σ all ISCO-4):     {nat_known_total:>10,d}")
    print(f"County known (Σ all ISCO-4 × 15):  {cty_known_total:>10,d}")
    print(f"County estimate (residual-constr): {cty_est_total:>10,d}")
    print(f"County upper bound (each hidden=19): {cty_upper_total:>10,d}")
    band = cty_upper_total - cty_known_total
    print(f"Suppression band (upper − lower):  {band:>10,d}  "
          f"({band / max(cty_upper_total, 1) * 100:.1f}% of upper)")

    # Top 10 verticals by AI-exposure
    print("\nTop 10 verticals by AI-exposure (consensus z):")
    for _, r in rank.head(10).iterrows():
        print(f"  {int(r['priority_rank']):2d}. {r['vertical_id']:30s} "
              f"z={r['vertical_ensemble_z']:+.2f}  "
              f"n_nat={int(r['vertical_employment_national']):>7,d}  "
              f"({r['vertical_label']})")

    print("\nTop 5 verticals by people affected (national known):")
    for _, r in rank.sort_values("vertical_employment_national",
                                 ascending=False).head(5).iterrows():
        print(f"  {int(r['priority_rank']):2d}. {r['vertical_id']:30s} "
              f"n_nat={int(r['vertical_employment_national']):>7,d}  "
              f"z={r['vertical_ensemble_z']:+.2f}  "
              f"({r['vertical_label']})")

    # Bounds invariants
    bad = long_out[(long_out["people_lower"] > long_out["people_estimate"] + 1e-6) |
                   (long_out["people_estimate"] > long_out["people_upper"] + 1e-6)]
    if len(bad):
        print(f"\n!! {len(bad)} cells violate lower ≤ estimate ≤ upper invariant")
    else:
        print("\nBounds invariant (lower ≤ estimate ≤ upper): OK")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--top", type=int, default=50,
                   help="Max verticals to include in wide CSVs and heatmap (default 50)")
    p.add_argument("--no-xlsx", action="store_true",
                   help="Skip writing the Excel workbook")
    p.add_argument("--no-choropleth", action="store_true",
                   help="Skip rendering the choropleth small-multiples PNG")
    args = p.parse_args()
    build(top=args.top, xlsx=not args.no_xlsx,
          choropleth=not args.no_choropleth)
