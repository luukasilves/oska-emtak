"""Derive AI exposure + augmentation/automation share scores per (model, taxonomy).

Each registered model emits a long-format DataFrame with columns:
  model | taxonomy | code | metric | value | source | notes

Metrics emitted per code: exposure, augmentation_share, automation_share.
Source flags: derived | derived_aug_fallback | prototype | missing.

All registered models are concatenated and written to
  data/processed/scores/scores_long.csv

Also writes data/processed/scores/MODELS.md (the registry) if it doesn't exist.

To add a new model, write an aggregator returning a DataFrame in the above format
and wire it into the MODELS dict below.
"""

from datetime import date
import json
from pathlib import Path
import urllib.request

import numpy as np
import pandas as pd

from common import (
    RAW, SCORES_DIR, TARGET_ISCO2, load_bls_crosswalk,
)


# Heavy raw AEI files are gitignored. On fresh clones the pipeline re-fetches them
# from Hugging Face on demand. CC-BY licensed.
AEI_DOWNLOADS = {
    RAW / "anthropic_aei" / "aei_raw_1p_api_2026-02-05_to_2026-02-12.csv":
        "https://huggingface.co/datasets/Anthropic/EconomicIndex/resolve/main/release_2026_03_24/data/aei_raw_1p_api_2026-02-05_to_2026-02-12.csv",
}


def ensure_aei_raw_downloaded():
    """Download any missing AEI raw files. Idempotent: no-op if files already exist.

    Raises a clear message if the file is missing AND the host is unreachable so
    the rest of the pipeline can continue (other models don't depend on this file).
    """
    for path, url in AEI_DOWNLOADS.items():
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        size_mb = 44  # known approx for the 1P API file
        print(f"  fetching {path.name} (~{size_mb} MB) from Hugging Face...")
        try:
            urllib.request.urlretrieve(url, path)
            print(f"    -> {path}")
        except Exception as e:
            print(f"    WARNING: download failed ({e}); felten_aei + felten_aei_isco4 "
                  f"will be skipped this run. Drop the file in place to enable.")
            if path.exists() and path.stat().st_size < 1024:
                path.unlink()


# Native ISCO levels for ISCO-4 truncation in aggregators below.
ISCO4_LEVEL = "isco4"
ISCO3_LEVEL = "isco3"
ISCO2_LEVEL = "isco2"


# =====================================================================================
# Model: felten_aei
# Combines Felten et al. AIOE (SOC-6) with Anthropic Economic Index task-collaboration
# data (O*NET tasks → SOC) to produce ISCO-2 exposure + aug/auto shares.
# =====================================================================================

def _load_felten_aioe():
    """Felten AIOE Appendix A → DataFrame[soc6, aioe]."""
    df = pd.read_excel(RAW / "AIOE_DataAppendix.xlsx", "Appendix A")
    df = df.rename(columns={"SOC Code": "soc6", "AIOE": "aioe"})
    df["soc6"] = df["soc6"].astype(str).str.strip()
    return df[["soc6", "aioe"]]


def _load_aei_collaboration():
    """AEI 1P-API March 2026 collaboration counts → per-task aug/auto shares."""
    df = pd.read_csv(RAW / "anthropic_aei/aei_raw_1p_api_2026-02-05_to_2026-02-12.csv")
    sub = df[
        (df["facet"] == "onet_task::collaboration")
        & (df["variable"] == "onet_task_collaboration_count")
        & (df["level"] == 0)
    ].copy()
    splits = sub["cluster_name"].str.rsplit("::", n=1, expand=True)
    sub["task_text"] = splits[0]
    sub["pattern"] = splits[1]
    pivot = sub.pivot_table(index="task_text", columns="pattern",
                            values="value", aggfunc="sum", fill_value=0)
    AUTO = ["directive", "feedback loop"]
    AUG = ["task iteration", "learning", "validation"]
    for col in AUTO + AUG:
        if col not in pivot.columns:
            pivot[col] = 0
    pivot["automation_count"] = pivot[AUTO].sum(axis=1)
    pivot["augmentation_count"] = pivot[AUG].sum(axis=1)
    pivot["classified_total"] = pivot["automation_count"] + pivot["augmentation_count"]
    pivot = pivot[pivot["classified_total"] >= 20].copy()
    pivot["augmentation_share"] = pivot["augmentation_count"] / pivot["classified_total"]
    pivot["automation_share"] = pivot["automation_count"] / pivot["classified_total"]
    return pivot.reset_index()[
        ["task_text", "augmentation_share", "automation_share", "classified_total"]
    ]


def _load_onet_task_to_soc():
    """O*NET task-statements → DataFrame[task_text, soc6]. Strip .NN suffix to SOC-6."""
    df = pd.read_csv(RAW / "anthropic_aei/aei_2025_02_onet_task_statements.csv")
    df = df.rename(columns={"O*NET-SOC Code": "onet_soc", "Task": "task_text"})
    df["soc6"] = df["onet_soc"].astype(str).str.split(".").str[0]
    df["task_text"] = df["task_text"].astype(str).str.strip().str.lower()
    return df[["task_text", "soc6"]].drop_duplicates()


def _aggregate_aioe_to_isco_level(aioe, crosswalk, level: str):
    """Felten AIOE at SOC-6 → ISCO-`level` by simple mean over (soc6, isco4) pairs.

    `level` ∈ {"isco4", "isco2"}. A SOC-6 may map to multiple ISCO-4 codes; each
    pair contributes the SOC's AIOE value to that bucket. This is Felten's
    published convention.
    """
    assert level in {"isco4", "isco2"}, level
    joined = aioe.merge(crosswalk[["soc6", "isco4", "isco2"]], on="soc6", how="inner")
    grouped = joined.groupby(level)["aioe"].mean().reset_index()
    return grouped.rename(columns={level: "code"})


def _aggregate_aei_to_isco_level(task_shares, task_to_soc, crosswalk, level: str):
    """AEI per-task shares → ISCO-`level` weighted by classified_total.

    `level` ∈ {"isco4", "isco2"}.
    """
    assert level in {"isco4", "isco2"}, level
    task_shares = task_shares.copy()
    task_shares["task_text"] = task_shares["task_text"].str.strip().str.lower()
    joined = task_shares.merge(task_to_soc, on="task_text", how="inner")
    joined = joined.merge(crosswalk[["soc6", "isco4", "isco2"]], on="soc6", how="inner")

    def weighted_mean(g, col):
        w = g["classified_total"]
        return (g[col] * w).sum() / w.sum()

    rows = []
    for grp, g in joined.groupby(level):
        rows.append({
            "code": grp,
            "augmentation_share": weighted_mean(g, "augmentation_share"),
            "automation_share": weighted_mean(g, "automation_share"),
            "n_tasks_matched": len(g),
        })
    return pd.DataFrame(rows)


def _aggregate_aioe_to_isco2(aioe, crosswalk):
    """Backward-compat wrapper used by aggregate_felten_aei (renames code→isco2)."""
    df = _aggregate_aioe_to_isco_level(aioe, crosswalk, "isco2")
    return df.rename(columns={"code": "isco2"})


def _aggregate_aei_to_isco2(task_shares, task_to_soc, crosswalk):
    """Backward-compat wrapper used by aggregate_felten_aei."""
    df = _aggregate_aei_to_isco_level(task_shares, task_to_soc, crosswalk, "isco2")
    return df.rename(columns={"code": "isco2"})


def aggregate_felten_aei():
    """Return long-format DataFrame with the felten_aei model's ISCO-2 scores.

    Columns: model, taxonomy, code, metric, value, source, notes.
    Output: 40 ISCO-2 codes × 3 metrics = 120 rows.
    """
    if not (RAW / "anthropic_aei" / "aei_raw_1p_api_2026-02-05_to_2026-02-12.csv").exists():
        print("    [felten_aei] skipping: AEI 1P-API raw file not present")
        return pd.DataFrame()

    crosswalk = load_bls_crosswalk()
    aioe = _load_felten_aioe()
    aei_tasks = _load_aei_collaboration()
    task_to_soc = _load_onet_task_to_soc()

    aioe_isco2 = _aggregate_aioe_to_isco2(aioe, crosswalk)
    aei_isco2 = _aggregate_aei_to_isco2(aei_tasks, task_to_soc, crosswalk)

    combined = pd.DataFrame({"isco2": TARGET_ISCO2})
    combined = combined.merge(aioe_isco2, on="isco2", how="left")
    combined = combined.merge(aei_isco2, on="isco2", how="left")

    # Min-max rescale exposure across all 40 codes
    a_min, a_max = combined["aioe"].min(), combined["aioe"].max()
    combined["exposure"] = (combined["aioe"] - a_min) / (a_max - a_min)
    combined["aioe_raw"] = combined["aioe"]

    # Source flag + low-confidence fallback for aug/auto shares
    combined["source"] = "derived"
    combined.loc[combined["aioe_raw"].isna(), "source"] = "missing"
    combined["aug_low_conf"] = (
        (combined["n_tasks_matched"].fillna(0) < 10)
        | combined["augmentation_share"].isna()
    )
    if combined["aug_low_conf"].any():
        combined["isco1"] = combined["isco2"].str[0]
        good = combined[~combined["aug_low_conf"]].copy()
        isco1_means = good.groupby("isco1").agg(
            aug_isco1=("augmentation_share", "mean"),
            auto_isco1=("automation_share", "mean"),
        ).reset_index()
        global_aug = good["augmentation_share"].mean()
        global_auto = good["automation_share"].mean()
        combined = combined.merge(isco1_means, on="isco1", how="left")
        combined["aug_isco1"] = combined["aug_isco1"].fillna(global_aug)
        combined["auto_isco1"] = combined["auto_isco1"].fillna(global_auto)
        mask = combined["aug_low_conf"]
        combined.loc[mask, "augmentation_share"] = combined.loc[mask, "aug_isco1"]
        combined.loc[mask, "automation_share"] = combined.loc[mask, "auto_isco1"]
        combined.loc[mask, "source"] = "derived_aug_fallback"
        combined = combined.drop(columns=["isco1", "aug_isco1", "auto_isco1"])

    # Round to 4 decimals to match the v1 stored values exactly (which were written
    # with float_format="%.4f"). This protects numerical equivalence checks against
    # tiny binary-precision drift between runs.
    for col in ("exposure", "augmentation_share", "automation_share"):
        combined[col] = combined[col].round(4)

    # Build long-format rows
    rows = []
    for _, r in combined.iterrows():
        n = r["n_tasks_matched"]
        notes_n = f"n={int(n)} tasks" if pd.notna(n) else "n=0 tasks"
        if r["source"] == "derived_aug_fallback":
            notes_aug = f"{notes_n}; isco1-mean fallback"
            notes_auto = f"{notes_n}; isco1-mean fallback"
        else:
            notes_aug = notes_n
            notes_auto = notes_n
        notes_exp = "Felten AIOE × BLS crosswalk; min-max rescaled"
        rows.append({"model": "felten_aei", "taxonomy": "isco2",
                     "code": r["isco2"], "metric": "exposure",
                     "value": r["exposure"], "source": r["source"],
                     "notes": notes_exp})
        rows.append({"model": "felten_aei", "taxonomy": "isco2",
                     "code": r["isco2"], "metric": "augmentation_share",
                     "value": r["augmentation_share"], "source": r["source"],
                     "notes": notes_aug})
        rows.append({"model": "felten_aei", "taxonomy": "isco2",
                     "code": r["isco2"], "metric": "automation_share",
                     "value": r["automation_share"], "source": r["source"],
                     "notes": notes_auto})
    return pd.DataFrame(rows)


# =====================================================================================
# Model: felten_aei_isco4
# Same recipe as felten_aei but holds the ISCO-4 granularity (no collapse to ISCO-2).
# =====================================================================================

def aggregate_felten_aei_isco4():
    """Long-format ISCO-4 scores from Felten AIOE + AEI collaboration patterns.

    ~438 ISCO-4 codes × 3 metrics. Same min-max rescaling and ISCO-1-mean fallback
    as the ISCO-2 model, but applied at ISCO-4. Note: ISCO-2 fallback (vs ISCO-1)
    is added here because many ISCO-4 codes have <10 matched O*NET tasks and the
    ISCO-2 mean is a much sharper prior than the ISCO-1 mean for them.
    """
    if not (RAW / "anthropic_aei" / "aei_raw_1p_api_2026-02-05_to_2026-02-12.csv").exists():
        print("    [felten_aei_isco4] skipping: AEI 1P-API raw file not present")
        return pd.DataFrame()

    crosswalk = load_bls_crosswalk()
    aioe = _load_felten_aioe()
    aei_tasks = _load_aei_collaboration()
    task_to_soc = _load_onet_task_to_soc()

    aioe_isco4 = _aggregate_aioe_to_isco_level(aioe, crosswalk, "isco4")
    aei_isco4 = _aggregate_aei_to_isco_level(aei_tasks, task_to_soc, crosswalk, "isco4")

    # Universe = all ISCO-4 codes that appear in the BLS crosswalk
    universe = sorted(crosswalk["isco4"].unique())
    combined = pd.DataFrame({"code": universe})
    combined = combined.merge(aioe_isco4, on="code", how="left")
    combined = combined.merge(aei_isco4, on="code", how="left")

    # Min-max rescale exposure across all ISCO-4 codes with a valid AIOE value
    a_min, a_max = combined["aioe"].min(), combined["aioe"].max()
    combined["exposure"] = (combined["aioe"] - a_min) / (a_max - a_min)
    combined["aioe_raw"] = combined["aioe"]

    # Two-stage fallback: ISCO-2 mean → ISCO-1 mean → global mean
    combined["isco2"] = combined["code"].str[:2]
    combined["isco1"] = combined["code"].str[0]
    combined["source"] = "derived"
    combined.loc[combined["aioe_raw"].isna(), "source"] = "missing"
    low_conf = (
        (combined["n_tasks_matched"].fillna(0) < 10)
        | combined["augmentation_share"].isna()
    )

    good = combined[~low_conf]
    isco2_means = good.groupby("isco2").agg(
        aug_isco2=("augmentation_share", "mean"),
        auto_isco2=("automation_share", "mean"),
    ).reset_index()
    isco1_means = good.groupby("isco1").agg(
        aug_isco1=("augmentation_share", "mean"),
        auto_isco1=("automation_share", "mean"),
    ).reset_index()
    global_aug = good["augmentation_share"].mean()
    global_auto = good["automation_share"].mean()

    combined = combined.merge(isco2_means, on="isco2", how="left")
    combined = combined.merge(isco1_means, on="isco1", how="left")
    fill_aug = combined["aug_isco2"].fillna(combined["aug_isco1"]).fillna(global_aug)
    fill_auto = combined["auto_isco2"].fillna(combined["auto_isco1"]).fillna(global_auto)
    combined.loc[low_conf, "augmentation_share"] = fill_aug[low_conf]
    combined.loc[low_conf, "automation_share"] = fill_auto[low_conf]
    combined.loc[low_conf & (combined["source"] != "missing"), "source"] = "derived_aug_fallback"
    combined = combined.drop(columns=["aug_isco2", "auto_isco2", "aug_isco1", "auto_isco1",
                                       "isco2", "isco1"])

    for col in ("exposure", "augmentation_share", "automation_share"):
        combined[col] = combined[col].round(4)

    rows = []
    for _, r in combined.iterrows():
        n = r["n_tasks_matched"]
        notes_n = f"n={int(n)} tasks" if pd.notna(n) else "n=0 tasks"
        notes_exp = "Felten AIOE × BLS crosswalk; min-max rescaled at ISCO-4"
        notes_aug_auto = (f"{notes_n}; isco2/1-mean fallback"
                          if r["source"] == "derived_aug_fallback" else notes_n)
        for metric, val, note in [
            ("exposure", r["exposure"], notes_exp),
            ("augmentation_share", r["augmentation_share"], notes_aug_auto),
            ("automation_share", r["automation_share"], notes_aug_auto),
        ]:
            if pd.isna(val):
                continue
            rows.append({
                "model": "felten_aei_isco4", "taxonomy": "isco4",
                "code": r["code"], "metric": metric, "value": val,
                "source": r["source"], "notes": note,
            })
    return pd.DataFrame(rows)


# =====================================================================================
# Model: ilo_wp140
# ILO Working Paper 140 (Gmyrek et al., 2025) — categorical 4-class GenAI exposure
# at ISCO-08 4-digit. Source: github.com/pgmyrek/GenAI_Exposure_Tree_Plot
# Classes: "Not Affected" (271), "The Big Unknown" (82), "Augmentation Potential" (63),
# "Automation Potential" (20). Mapped to numeric [0, 1] exposure + aug/auto shares.
# =====================================================================================

WP140_CLASS_TO_EXPOSURE = {
    "Not Affected": 0.0,
    "The Big Unknown": 0.33,
    "Augmentation Potential": 0.66,
    "Automation Potential": 1.0,
}
WP140_CLASS_TO_AUG = {
    "Not Affected": 0.0,
    "The Big Unknown": 0.5,
    "Augmentation Potential": 1.0,
    "Automation Potential": 0.0,
}
WP140_CLASS_TO_AUTO = {
    "Not Affected": 0.0,
    "The Big Unknown": 0.5,
    "Augmentation Potential": 0.0,
    "Automation Potential": 1.0,
}


def _walk_wp140_tree(node, out):
    if "children" in node:
        for c in node["children"]:
            _walk_wp140_tree(c, out)
    else:
        out.append(node)


def aggregate_ilo_wp140():
    path = RAW / "ilo_wp140" / "wp140_isco4_categorical.json"
    if not path.exists():
        print("    [ilo_wp140] skipping: wp140_isco4_categorical.json not present")
        return pd.DataFrame()
    with open(path) as f:
        tree = json.load(f)
    leaves = []
    _walk_wp140_tree(tree, leaves)

    rows = []
    for leaf in leaves:
        # name format: "0110 - Commissioned armed forces officers"
        name = leaf.get("name", "")
        code = name.split(" - ")[0].strip().zfill(4)
        if len(code) != 4 or not code.isdigit():
            continue
        risk_class = leaf.get("risk")
        if risk_class not in WP140_CLASS_TO_EXPOSURE:
            continue
        exposure = WP140_CLASS_TO_EXPOSURE[risk_class]
        aug = WP140_CLASS_TO_AUG[risk_class]
        auto = WP140_CLASS_TO_AUTO[risk_class]
        note = f"WP140 class: {risk_class}"
        for metric, val in [("exposure", exposure),
                            ("augmentation_share", aug),
                            ("automation_share", auto)]:
            rows.append({
                "model": "ilo_wp140", "taxonomy": "isco4",
                "code": code, "metric": metric, "value": round(val, 4),
                "source": "derived", "notes": note,
            })
    return pd.DataFrame(rows)


# =====================================================================================
# Model: demirev_ai_products
# Demirev (2026, Industry and Innovation) — AI-product-derived exposure at ISCO-4
# with explicit aug/auto decomposition. ESCO-mapped, aggregated by Demirev to
# ISCO-4 via cosine similarity of ESCO skills × AI capabilities. Used here as the
# continuous-with-decomposition slot originally planned for Cazzaniga (IMF SDN
# 2024/001), which is PDF-only and not accessible from the build environment.
# Source: github.com/demirev/ai-products
# =====================================================================================

def aggregate_demirev_ai_products():
    path = RAW / "demirev_ai_products" / "scored_isco_4_digit.csv"
    esco_path = RAW / "demirev_ai_products" / "scored_esco_occupations.csv"
    if not path.exists() or not esco_path.exists():
        print("    [demirev_ai_products] skipping: raw files not present")
        return pd.DataFrame()
    isco4 = pd.read_csv(path, dtype={"isco_level_4": str})
    isco4["code"] = isco4["isco_level_4"].str.zfill(4)
    isco4 = isco4.rename(columns={"ai_product_exposure_score": "exposure_raw"})

    # Aggregate ESCO-level aug/auto to ISCO-4 by simple mean (Demirev's published
    # ISCO-4 file only carries the headline exposure; aug/auto live at ESCO level).
    esco = pd.read_csv(esco_path, dtype={"isco_group": str})
    esco["isco4"] = esco["isco_group"].str.zfill(4)
    aug_auto = (esco.groupby("isco4")
                    .agg(augmentation_share=("ai_product_augmentation_score", "mean"),
                         automation_share=("ai_product_automation_score", "mean"))
                    .reset_index()
                    .rename(columns={"isco4": "code"}))

    combined = isco4[["code", "exposure_raw"]].merge(aug_auto, on="code", how="left")

    # Min-max rescale exposure to [0, 1] across the available ISCO-4 codes
    e_min, e_max = combined["exposure_raw"].min(), combined["exposure_raw"].max()
    combined["exposure"] = (combined["exposure_raw"] - e_min) / (e_max - e_min)

    # Renormalise aug + auto shares to sum to 1 where both are present (Demirev's
    # raw scores are independent 0-1 quantities, not a probability split).
    tot = combined["augmentation_share"] + combined["automation_share"]
    mask = tot.fillna(0) > 0
    combined.loc[mask, "augmentation_share"] = combined.loc[mask, "augmentation_share"] / tot[mask]
    combined.loc[mask, "automation_share"] = combined.loc[mask, "automation_share"] / tot[mask]

    for col in ("exposure", "augmentation_share", "automation_share"):
        combined[col] = combined[col].round(4)

    rows = []
    for _, r in combined.iterrows():
        for metric, val in [("exposure", r["exposure"]),
                            ("augmentation_share", r["augmentation_share"]),
                            ("automation_share", r["automation_share"])]:
            if pd.isna(val):
                continue
            rows.append({
                "model": "demirev_ai_products", "taxonomy": "isco4",
                "code": r["code"], "metric": metric, "value": val,
                "source": "derived",
                "notes": "Demirev 2026 AI-products method; min-max rescaled at ISCO-4",
            })
    return pd.DataFrame(rows)


# =====================================================================================
# Model: jrc_casas (stub — needs manual data drop, see data/raw/jrc_casas/README.md)
# =====================================================================================

def aggregate_jrc_casas():
    path = RAW / "jrc_casas" / "jrc_casas_isco3.csv"
    if not path.exists():
        print("    [jrc_casas] skipping: jrc_casas_isco3.csv not present "
              "(see data/raw/jrc_casas/README.md)")
        return pd.DataFrame()
    df = pd.read_csv(path, dtype={"isco3": str})
    df["code"] = df["isco3"].str.zfill(3)
    e_min, e_max = df["exposure_raw"].min(), df["exposure_raw"].max()
    df["exposure"] = ((df["exposure_raw"] - e_min) / (e_max - e_min)).round(4)
    return pd.DataFrame([
        {"model": "jrc_casas", "taxonomy": "isco3", "code": r["code"],
         "metric": "exposure", "value": r["exposure"],
         "source": "derived", "notes": "JRC Casas 2025/26; min-max rescaled at ISCO-3"}
        for _, r in df.iterrows()
    ])


# =====================================================================================
# Registry
# =====================================================================================
MODELS = {
    "felten_aei": aggregate_felten_aei,
    "felten_aei_isco4": aggregate_felten_aei_isco4,
    "ilo_wp140": aggregate_ilo_wp140,
    "demirev_ai_products": aggregate_demirev_ai_products,
    "jrc_casas": aggregate_jrc_casas,
}


# =====================================================================================
# Registry doc (MODELS.md)
# =====================================================================================
_MODELS_MD = """# Score models registry

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
"""


def _print_sanity_block(name: str, df: pd.DataFrame):
    """Print a one-block sanity summary per model."""
    if df.empty:
        print(f"  [{name}] no rows produced")
        return
    wide = df.pivot_table(index=["taxonomy", "code"], columns="metric",
                          values="value", aggfunc="first").reset_index()
    print(f"\n  --- model: {name} ---")
    print(f"    rows: {len(df)} ({len(wide)} unique codes × "
          f"{df['metric'].nunique()} metrics)")
    if "exposure" in wide.columns:
        top5 = wide.nlargest(5, "exposure")[["code", "exposure"]]
        print(f"    top5 exposure: {top5.values.tolist()}")
    if "augmentation_share" in wide.columns:
        top5a = wide.nlargest(5, "augmentation_share")[["code", "augmentation_share"]]
        print(f"    top5 augmentation_share: {top5a.values.tolist()}")
    if "automation_share" in wide.columns:
        top5b = wide.nlargest(5, "automation_share")[["code", "automation_share"]]
        print(f"    top5 automation_share: {top5b.values.tolist()}")
    fallback = df[df["source"] == "derived_aug_fallback"]
    fallback_codes = sorted(set(fallback["code"]))
    print(f"    fallback cells: {len(fallback_codes)} codes: {fallback_codes}")


def main():
    SCORES_DIR.mkdir(parents=True, exist_ok=True)

    print("Ensuring raw AEI files are present:")
    ensure_aei_raw_downloaded()

    frames = []
    print("\nAggregating registered models:")
    for name, fn in MODELS.items():
        print(f"  - {name} ...")
        df = fn()
        if df.empty:
            print(f"    WARNING: {name} produced no rows")
            continue
        frames.append(df)

    out_path = SCORES_DIR / "scores_long.csv"

    # Preserve previously-stored rows for any registered model that produced no
    # rows this run (e.g. because its raw input file is locally unavailable in
    # this build environment). This keeps `scores_long.csv` consistent with the
    # registry across partial-input runs.
    if out_path.exists():
        prev = pd.read_csv(out_path, dtype={"taxonomy": str, "code": str})
        produced = {df["model"].iloc[0] for df in frames if not df.empty}
        retain_models = [m for m in MODELS if m not in produced
                         and m in set(prev["model"].unique())]
        if retain_models:
            print(f"\nRetaining prior rows for unchanged models: {retain_models}")
            frames.append(prev[prev["model"].isin(retain_models)])

    if not frames:
        print("No model frames produced; aborting.")
        return

    long_df = pd.concat(frames, ignore_index=True)
    long_df = long_df[["model", "taxonomy", "code", "metric", "value", "source", "notes"]]
    long_df.to_csv(out_path, index=False)
    print(f"\nWrote {out_path}  ({len(long_df):,} rows)")

    for name in MODELS:
        _print_sanity_block(name, long_df[long_df["model"] == name])

    models_md_path = SCORES_DIR / "MODELS.md"
    models_md_path.write_text(_MODELS_MD)
    print(f"\nWrote {models_md_path}")


if __name__ == "__main__":
    main()
