"""Generate static charts for every (model × scenario) matrix.

Discovers data/processed/matrices/matrix_<model>_<scenario>.csv files. For each:
  - Loads matrix + corresponding maakond summary.
  - Reads combined municipality geometry from data/processed/geometry/.
  - Renders the 8 PNG charts into output/charts/<model>_<scenario>/.

Chart names, titles, colours, and layouts are identical to v1.
"""

import re
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import (
    CHARTS_DIR, GEOMETRY_DIR, MATRICES_DIR, OMAV_REMAP, RAW, SCORES_DIR,
    SUMMARIES_DIR, load_isco_labels,
)


plt.rcParams.update({
    "font.family": "sans-serif",
    "figure.dpi": 120,
    "savefig.dpi": 140,
    "savefig.bbox": "tight",
})

# Color palette
C_OPP = "#2E86AB"
C_RISK = "#D62828"
C_EXP = "#6A4C93"
C_NEUTRAL = "#808080"

ISCO1_COLORS = {
    "1": "#1f77b4", "2": "#ff7f0e", "3": "#2ca02c", "4": "#d62728",
    "5": "#9467bd", "6": "#8c564b", "7": "#e377c2", "8": "#7f7f7f",
    "9": "#bcbd22",
}
ISCO1_LABELS = {
    "1": "Managers", "2": "Professionals", "3": "Technicians",
    "4": "Clerical", "5": "Service & Sales", "6": "Skilled Agric",
    "7": "Skilled Trades", "8": "Plant Operators", "9": "Elementary",
}


def _parse_matrix_filename(path: Path):
    """matrix_<model>_<scenario>.csv → (model, scenario)."""
    m = re.match(r"^matrix_(.+)_(.+)\.csv$", path.name)
    if not m:
        return None, None
    # The split is ambiguous (model and scenario can both contain underscores);
    # we read the actual values from the file itself to be safe.
    return m.group(1), m.group(2)


def _read_combo(matrix_path: Path):
    """Load matrix CSV + return (matrix, summary, model, scenario, taxonomy)."""
    matrix = pd.read_csv(matrix_path, dtype={"code": str, "location_code": str})
    # Derive isco1 from code if taxonomy is isco* and the code has at least one digit
    taxonomy = matrix["taxonomy"].iloc[0] if len(matrix) else "isco2"
    if taxonomy.startswith("isco") and matrix["code"].str.len().min() >= 1:
        matrix["isco1"] = matrix["code"].astype(str).str[0]
    else:
        matrix["isco1"] = ""
    model = matrix["model"].iloc[0]
    scenario = matrix["scenario"].iloc[0]
    summary_path = SUMMARIES_DIR / f"maakond_summary_{model}_{scenario}.csv"
    summary = pd.read_csv(summary_path)
    return matrix, summary, model, scenario, taxonomy


def _render(matrix: pd.DataFrame, summary: pd.DataFrame, out_dir: Path):
    """Render the 8 charts to out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = summary.copy()
    summary["maakond"] = summary["location_name"].str.title() \
        .str.replace(" Maakond", "", regex=False)

    # =================================================================================
    # 01 Employment by maakond
    # =================================================================================
    fig, ax = plt.subplots(figsize=(10, 6))
    s1 = summary.sort_values("total_employed", ascending=True)
    ax.barh(s1["maakond"], s1["total_employed"], color=C_NEUTRAL, edgecolor="white")
    ax.set_xlabel("Employed persons (Dec 2021 Census)")
    ax.set_title("Total employment by maakond — Estonia (n ≈ 642,000)",
                 fontsize=13, weight="bold")
    for i, v in enumerate(s1["total_employed"]):
        ax.text(v + 2000, i, f"{v:,}", va="center", fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    plt.savefig(out_dir / "01_employment_by_maakond.png")
    plt.close()
    print("  01_employment_by_maakond.png")

    # =================================================================================
    # 02 AI exposure (employment-weighted) by maakond
    # =================================================================================
    fig, ax = plt.subplots(figsize=(10, 6))
    s2 = summary.sort_values("exposure_avg", ascending=True)
    ax.barh(s2["maakond"], s2["exposure_avg"], color=C_EXP, edgecolor="white")
    ax.set_xlabel("Employment-weighted AI exposure score (0–1)")
    ax.set_title("AI exposure by maakond — employment-weighted",
                 fontsize=13, weight="bold")
    ax.set_xlim(0, max(s2["exposure_avg"]) * 1.15)
    for i, v in enumerate(s2["exposure_avg"]):
        ax.text(v + 0.005, i, f"{v:.2f}", va="center", fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.text(0.5, -0.02,
             "Source: REL2021 RL21154 (Statistics Estonia) × Felten LM-AIOE (prototype mapping)",
             ha="center", fontsize=7, color="gray")
    plt.savefig(out_dir / "02_exposure_by_maakond.png")
    plt.close()
    print("  02_exposure_by_maakond.png")

    # =================================================================================
    # 03 Opportunity vs Risk per maakond
    # =================================================================================
    fig, ax = plt.subplots(figsize=(11, 7))
    s3 = summary.sort_values("opportunity_avg", ascending=True)
    y = np.arange(len(s3))
    h = 0.4
    ax.barh(y - h/2, s3["opportunity_avg"], h, color=C_OPP,
            label="Opportunity (augmentation)", edgecolor="white")
    ax.barh(y + h/2, s3["risk_avg"], h, color=C_RISK,
            label="Risk (automation)", edgecolor="white")
    ax.set_yticks(y)
    ax.set_yticklabels(s3["maakond"])
    ax.set_xlabel("Employment-weighted score (0–1)")
    ax.set_title("AI Opportunity vs Risk by maakond — Estonia",
                 fontsize=13, weight="bold")
    ax.legend(loc="lower right", frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.text(0.5, -0.02,
             "Opportunity = exposure × augmentation share; Risk = exposure × automation share. "
             "Source: REL2021 RL21154 × Felten LM-AIOE × AEI broad pattern (prototype).",
             ha="center", fontsize=7, color="gray")
    plt.savefig(out_dir / "03_opportunity_vs_risk_by_maakond.png")
    plt.close()
    print("  03_opportunity_vs_risk_by_maakond.png")

    # =================================================================================
    # 04 Opportunity × Risk scatter of ISCO 2-digit groups (national)
    # =================================================================================
    nat = matrix[matrix["location_name"] == "Kogu Eesti"].copy()
    nat = nat.dropna(subset=["code"])

    fig, ax = plt.subplots(figsize=(11, 7.5))
    for isco1 in sorted(nat["isco1"].unique()):
        sub = nat[nat["isco1"] == isco1]
        if isco1 in ISCO1_COLORS:
            ax.scatter(sub["opportunity"], sub["risk"],
                       s=sub["employed"] / nat["employed"].max() * 1800 + 20,
                       c=ISCO1_COLORS[isco1], alpha=0.7,
                       edgecolor="white", linewidth=1.0,
                       label=f"{isco1} {ISCO1_LABELS[isco1]}")
    top = nat.nlargest(8, "employed")
    for _, r in top.iterrows():
        label = str(r["code_label"]).lstrip(".").strip()[:35]
        ax.annotate(label, (r["opportunity"], r["risk"]),
                    xytext=(5, 5), textcoords="offset points",
                    fontsize=7.5, color="#333")
    ax.set_xlabel("Opportunity (augmentation-weighted exposure)")
    ax.set_ylabel("Risk (automation-weighted exposure)")
    ax.set_title("ISCO 2-digit groups: Opportunity × Risk, sized by national employment",
                 fontsize=13, weight="bold")
    ax.set_xlim(-0.02, max(nat["opportunity"]) * 1.18)
    ax.set_ylim(-0.02, max(nat["risk"]) * 1.20)
    ax.grid(True, alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="upper left", fontsize=8, frameon=False,
              title="ISCO Major Group", title_fontsize=9)
    fig.text(0.5, -0.02,
             "Bubble size ∝ national employment. Source: REL2021 RL21154 (n≈642k) × "
             "Felten LM-AIOE × AEI broad pattern (prototype).",
             ha="center", fontsize=7, color="gray")
    plt.savefig(out_dir / "04_opportunity_risk_scatter.png")
    plt.close()
    print("  04_opportunity_risk_scatter.png")

    # =================================================================================
    # 05 Top 15 ISCO groups nationally by people-affected
    # =================================================================================
    nat["people_affected"] = nat["employed"] * nat["exposure"]
    nat["people_opportunity"] = nat["employed"] * nat["opportunity"]
    nat["people_risk"] = nat["employed"] * nat["risk"]

    top15 = nat.nlargest(15, "people_affected").copy()
    top15["label"] = top15["code_label"].astype(str).str.lstrip(".").str.strip()
    top15 = top15.sort_values("people_affected", ascending=True)

    fig, ax = plt.subplots(figsize=(11, 8))
    y = np.arange(len(top15))
    ax.barh(y, top15["people_opportunity"], color=C_OPP,
            label="Opportunity", edgecolor="white")
    ax.barh(y, top15["people_risk"], left=top15["people_opportunity"],
            color=C_RISK, label="Risk", edgecolor="white")
    ax.set_yticks(y)
    ax.set_yticklabels(top15["label"], fontsize=9)
    ax.set_xlabel("People affected (employed × exposure)")
    ax.set_title("Top 15 occupational groups by people-affected — Estonia, national",
                 fontsize=13, weight="bold")
    ax.legend(loc="lower right", frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    for i, (opp, risk, emp) in enumerate(zip(
            top15["people_opportunity"], top15["people_risk"], top15["employed"])):
        total = opp + risk
        ax.text(total + 600, i, f"{int(total):,} (of {int(emp):,})",
                va="center", fontsize=7.5, color="#333")
    fig.text(0.5, -0.02,
             "Bars split into Opportunity (augmentation) and Risk (automation) per group. "
             "Total exposure-weighted headcount labelled to the right.",
             ha="center", fontsize=7, color="gray")
    plt.savefig(out_dir / "05_top15_people_affected.png")
    plt.close()
    print("  05_top15_people_affected.png")

    # =================================================================================
    # 06 Maakond-level 3-panel choropleth
    # =================================================================================
    gdf = gpd.read_file(RAW / "maakond.geojson")
    gdf["maakond"] = gdf["MNIMI"].str.replace(" maakond", "", regex=False).str.title()
    merged = gdf.merge(summary, on="maakond", how="left")
    unmatched = merged[merged["total_employed"].isna()]
    if len(unmatched):
        print(f"WARNING: unmatched in maakond map: {unmatched['MNIMI'].tolist()}")

    fig, axes = plt.subplots(1, 3, figsize=(18, 6.5))
    panels = [
        ("exposure_avg", "AI Exposure", "Purples"),
        ("opportunity_avg", "Opportunity (augmentation)", "Blues"),
        ("risk_avg", "Risk (automation)", "Reds"),
    ]
    for ax, (col, title, cmap) in zip(axes, panels):
        merged.plot(column=col, ax=ax, cmap=cmap, edgecolor="white",
                    linewidth=0.8, legend=True,
                    legend_kwds={"shrink": 0.6, "label": "score (0–1)"})
        ax.set_title(title, fontsize=12, weight="bold")
        ax.set_axis_off()
    fig.suptitle("AI exposure, Opportunity, Risk by maakond — employment-weighted",
                 fontsize=14, weight="bold", y=1.02)
    fig.text(0.5, 0.02,
             "Each maakond shaded by employment-weighted score. Source: REL2021 RL21154 × "
             "Felten AIOE × Anthropic Economic Index (March 2026).",
             ha="center", fontsize=8, color="gray")
    plt.savefig(out_dir / "06_estonia_choropleth.png", bbox_inches="tight")
    plt.close()
    print("  06_estonia_choropleth.png")

    # =================================================================================
    # 07 & 08 Municipality + linnaosa choropleths
    # =================================================================================
    muni_summary = _build_municipality_summary(matrix)
    combined_geo = gpd.read_file(GEOMETRY_DIR / "estonia_municipalities_combined.geojson")

    muni_summary["join_code"] = ""
    mask_vald = muni_summary["type_suffix"].isin(["01", "L4", "M4"])
    muni_summary.loc[mask_vald, "join_code"] = muni_summary.loc[mask_vald, "omav_code"]
    mask_linnaosa = muni_summary["type_suffix"] == "L6"
    muni_summary.loc[mask_linnaosa, "join_code"] = muni_summary.loc[mask_linnaosa, "asust_code"]

    # Drop Tallinn/Kohtla-Järve aggregates; use linnaosa instead
    muni_summary = muni_summary[~muni_summary["omav_code"].isin(["0784", "0321"])
                                | muni_summary["type_suffix"].eq("L6")]

    merged_muni = combined_geo.merge(
        muni_summary[["join_code", "total_employed", "exposure_avg",
                      "opportunity_avg", "risk_avg", "people_affected", "label"]],
        on="join_code", how="left", suffixes=("_geo", ""),
    )

    n_total = len(combined_geo)
    n_matched = merged_muni["total_employed"].notna().sum()
    print(f"  Municipality join: matched {n_matched} of {n_total} polygons")
    unmatched = merged_muni[merged_muni["total_employed"].isna()]
    if len(unmatched):
        print(f"    Unmatched: {unmatched['label_geo'].tolist()}")

    # --- 07 ---
    fig, axes = plt.subplots(1, 3, figsize=(20, 7.5))
    panels = [
        ("exposure_avg", "AI Exposure", "Purples"),
        ("opportunity_avg", "Opportunity (augmentation)", "Blues"),
        ("risk_avg", "Risk (automation)", "Reds"),
    ]
    for ax, (col, title, cmap) in zip(axes, panels):
        merged_muni.plot(column=col, ax=ax, cmap=cmap, edgecolor="white",
                         linewidth=0.3, legend=True,
                         legend_kwds={"shrink": 0.55, "label": "score (0–1)"},
                         missing_kwds={"color": "#dddddd", "edgecolor": "white",
                                       "linewidth": 0.3})
        ax.set_title(title, fontsize=12, weight="bold")
        ax.set_axis_off()
    fig.suptitle("AI exposure, Opportunity, Risk by municipality + Tallinn/Kohtla-Järve district",
                 fontsize=14, weight="bold", y=1.02)
    fig.text(0.5, 0.02,
             f"~{n_matched} polygons (78 municipalities + 8 Tallinn linnaosa + "
             "5 Kohtla-Järve linnaosa). "
             "Source: REL2021 RL21154 × Felten AIOE × Anthropic Economic Index (March 2026).",
             ha="center", fontsize=8, color="gray")
    plt.savefig(out_dir / "07_estonia_municipality_choropleth.png",
                bbox_inches="tight", dpi=150)
    plt.close()
    print("  07_estonia_municipality_choropleth.png")

    # --- 08 ---
    fig, ax = plt.subplots(figsize=(13, 10))
    merged_muni.plot(column="people_affected", ax=ax, cmap="Reds",
                     edgecolor="white", linewidth=0.3, legend=True,
                     legend_kwds={"shrink": 0.55,
                                  "label": "People affected (employed × exposure)"},
                     missing_kwds={"color": "#dddddd", "edgecolor": "white",
                                   "linewidth": 0.3})
    ax.set_title("People affected by AI per locality — absolute headcount",
                 fontsize=14, weight="bold")
    ax.set_axis_off()

    top8 = merged_muni.nlargest(8, "people_affected").copy()
    top8 = top8[top8["geometry"].notna() & top8["people_affected"].notna()]
    tallinn_mask = top8["MNIMI"] == "Harju maakond"
    tallinn_rows = top8[tallinn_mask & (top8["join_type"] == "linnaosa")] \
        .sort_values("people_affected", ascending=False)
    others = top8[~(tallinn_mask & (top8["join_type"] == "linnaosa"))]

    for _, r in others.iterrows():
        c = r.geometry.centroid
        ax.annotate(f"{r['label_geo']}\n{int(r['people_affected']):,}",
                    (c.x, c.y), fontsize=8, ha="center", va="center", color="white",
                    weight="bold",
                    bbox=dict(boxstyle="round,pad=0.3", fc="black",
                              alpha=0.65, ec="none"))

    if len(tallinn_rows):
        tallinn_text = "Tallinn linnaosa (top):\n" + "\n".join(
            f"  {r['label_geo'].replace(' linnaosa', '')}: {int(r['people_affected']):,}"
            for _, r in tallinn_rows.head(5).iterrows()
        )
        ax.text(0.02, 0.98, tallinn_text, transform=ax.transAxes,
                fontsize=8.5, va="top", ha="left", color="white", weight="bold",
                bbox=dict(boxstyle="round,pad=0.5", fc="black", alpha=0.75, ec="none"))
        kesk = merged_muni[merged_muni["label_geo"].str.contains("Kesklinna", na=False)]
        if len(kesk):
            c = kesk.iloc[0].geometry.centroid
            ax.annotate("", xy=(c.x, c.y),
                        xytext=(0.20, 0.85), textcoords=("axes fraction"),
                        arrowprops=dict(arrowstyle="->", color="black", lw=1.2))

    fig.text(0.5, 0.04,
             f"Top {len(top8)} localities labelled. Tallinn districts dominate "
             "(capital captures 49% of national employment). "
             "Source: REL2021 RL21154 × Felten AIOE × Anthropic Economic Index (March 2026).",
             ha="center", fontsize=8, color="gray")
    plt.savefig(out_dir / "08_municipality_people_affected.png",
                bbox_inches="tight", dpi=150)
    plt.close()
    print("  08_municipality_people_affected.png")


def _build_municipality_summary(matrix: pd.DataFrame) -> pd.DataFrame:
    df = matrix.copy()
    df["code_str"] = df["location_code"].astype(str)
    df["code_len"] = df["code_str"].str.len()
    df = df[df["code_len"] == 14].copy()
    df["maakond_code"] = df["code_str"].str[:4]
    df["omav_code"] = df["code_str"].str[4:8]
    df["asust_code"] = df["code_str"].str[8:12]
    df["type_suffix"] = df["code_str"].str[12:14]
    muni = df[df["type_suffix"].isin(["01", "L4", "M4", "L6"])].copy()
    muni["omav_code"] = muni["omav_code"].replace(OMAV_REMAP)
    muni["opp_w"] = muni["opportunity"] * muni["employed"]
    muni["risk_w"] = muni["risk"] * muni["employed"]
    muni["exp_w"] = muni["exposure"] * muni["employed"]
    grouped = muni.groupby(
        ["maakond_code", "omav_code", "asust_code", "type_suffix", "location_name"]
    ).agg(
        total_employed=("employed", "sum"),
        opp_w=("opp_w", "sum"),
        risk_w=("risk_w", "sum"),
        exp_w=("exp_w", "sum"),
    ).reset_index()
    grouped["opportunity_avg"] = grouped["opp_w"] / grouped["total_employed"]
    grouped["risk_avg"] = grouped["risk_w"] / grouped["total_employed"]
    grouped["exposure_avg"] = grouped["exp_w"] / grouped["total_employed"]
    grouped["people_affected"] = grouped["exp_w"]
    grouped["label"] = grouped["location_name"].str.lstrip(".").str.strip()
    return grouped


def _render_top_isco4_per_model(scores_long: pd.DataFrame, model: str,
                                  out_dir: Path, top_n: int = 30):
    """Chart 09 — top-N detailed ISCO-3/4 occupations by exposure for one model.

    No-op for models whose taxonomy is ISCO-2 (no extra detail to show).
    """
    sub = scores_long[(scores_long["model"] == model)
                      & (scores_long["metric"] == "exposure")].copy()
    if sub.empty:
        return
    taxonomy = sub["taxonomy"].iloc[0]
    if taxonomy not in ("isco3", "isco4"):
        return  # ISCO-2 detail already covered by chart 05

    labels = load_isco_labels()
    level = 4 if taxonomy == "isco4" else 3
    sub["label"] = sub["code"].map(labels[level]).fillna(sub["code"])
    sub["isco1"] = sub["code"].astype(str).str[0]
    sub = sub.nlargest(top_n, "value").sort_values("value", ascending=True)

    fig, ax = plt.subplots(figsize=(12, max(7, top_n * 0.3)))
    colors = sub["isco1"].map(ISCO1_COLORS).fillna(C_NEUTRAL)
    ax.barh(range(len(sub)), sub["value"], color=colors, edgecolor="white")
    ax.set_yticks(range(len(sub)))
    ax.set_yticklabels([f"{c} — {lbl[:55]}" for c, lbl in zip(sub["code"], sub["label"])],
                       fontsize=8)
    ax.set_xlabel(f"Exposure score (0–1, native at {taxonomy.upper()})")
    ax.set_title(f"Top {top_n} detailed occupations by exposure — model: {model}",
                 fontsize=13, weight="bold")
    ax.set_xlim(0, max(sub["value"]) * 1.08)
    ax.spines[["top", "right"]].set_visible(False)
    # ISCO major-group legend (only those present)
    present = sorted(sub["isco1"].unique())
    handles = [plt.Rectangle((0, 0), 1, 1, color=ISCO1_COLORS.get(i, C_NEUTRAL))
               for i in present]
    legend_labels = [f"{i} {ISCO1_LABELS.get(i, '?')}" for i in present]
    ax.legend(handles, legend_labels, loc="lower right", fontsize=8, frameon=False,
              title="ISCO Major Group", title_fontsize=9)
    plt.savefig(out_dir / "09_top_isco4_detailed_occupations.png")
    plt.close()
    print("  09_top_isco4_detailed_occupations.png")


def _render_cross_model_rank_correlation(scores_long: pd.DataFrame, out_root: Path):
    """Chart 10 — Spearman rank correlation of ISCO-4 exposure across ISCO-4 models.

    JRC Casas is excluded if present (it's ISCO-3 native — would need separate panel).
    """
    out_dir = out_root / "_cross_model"
    out_dir.mkdir(parents=True, exist_ok=True)

    sub = scores_long[(scores_long["metric"] == "exposure")
                      & (scores_long["taxonomy"] == "isco4")].copy()
    if sub["model"].nunique() < 2:
        print("  [cross-model] skipping rank correlation: need ≥2 ISCO-4 models")
        return

    wide = sub.pivot_table(index="code", columns="model", values="value")
    corr = wide.corr(method="spearman")
    fig, ax = plt.subplots(figsize=(1.7 + 1.2 * len(corr), 1.2 + 1.0 * len(corr)))
    im = ax.imshow(corr, cmap="RdYlBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(corr))); ax.set_yticks(range(len(corr)))
    ax.set_xticklabels(corr.columns, rotation=30, ha="right", fontsize=9)
    ax.set_yticklabels(corr.index, fontsize=9)
    for i in range(len(corr)):
        for j in range(len(corr)):
            v = corr.iloc[i, j]
            ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                    color="white" if abs(v) > 0.5 else "black", fontsize=9)
    ax.set_title("Spearman rank correlation, ISCO-4 exposure across models",
                 fontsize=12, weight="bold")
    fig.colorbar(im, ax=ax, shrink=0.7, label="ρ")
    fig.text(0.5, -0.02,
             f"Codes in common: ~{len(wide.dropna()):,} of {len(wide):,} ISCO-4. "
             "Pairwise correlation uses available overlap.",
             ha="center", fontsize=8, color="gray")
    plt.savefig(out_dir / "10_isco4_rank_correlation.png", bbox_inches="tight")
    plt.close()
    print(f"  10_isco4_rank_correlation.png  ({len(corr)}×{len(corr)} matrix)")


def main():
    matrix_files = sorted(MATRICES_DIR.glob("matrix_*.csv"))
    if not matrix_files:
        print(f"No matrix files found under {MATRICES_DIR}")
        return

    print(f"Found {len(matrix_files)} matrix file(s):")
    for p in matrix_files:
        print(f"  {p.name}")

    scores_long = pd.read_csv(SCORES_DIR / "scores_long.csv",
                              dtype={"taxonomy": str, "code": str})

    for matrix_path in matrix_files:
        matrix, summary, model, scenario, taxonomy = _read_combo(matrix_path)
        out_dir = CHARTS_DIR / f"{model}_{scenario}"
        print(f"\n[{model} × {scenario}] taxonomy={taxonomy} → {out_dir}")
        _render(matrix, summary, out_dir)
        _render_top_isco4_per_model(scores_long, model, out_dir)

    print(f"\n[cross-model] → {CHARTS_DIR}/_cross_model")
    _render_cross_model_rank_correlation(scores_long, CHARTS_DIR)

    print(f"\nAll charts written under {CHARTS_DIR}")


if __name__ == "__main__":
    main()
