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
    """Download any missing AEI raw files. Idempotent: no-op if files already exist."""
    for path, url in AEI_DOWNLOADS.items():
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        size_mb = 44  # known approx for the 1P API file
        print(f"  fetching {path.name} (~{size_mb} MB) from Hugging Face...")
        urllib.request.urlretrieve(url, path)
        print(f"    -> {path}")


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


def _aggregate_aioe_to_isco2(aioe, crosswalk):
    """Felten AIOE at SOC-6 → ISCO-2 by simple mean over (soc6, isco4) pairs.

    A SOC-6 may map to multiple ISCO-4 codes; each pair contributes the SOC's AIOE
    value to that ISCO-2 bucket. This is Felten's published convention.
    """
    joined = aioe.merge(crosswalk[["soc6", "isco4", "isco2"]], on="soc6", how="inner")
    return joined.groupby("isco2")["aioe"].mean().reset_index()


def _aggregate_aei_to_isco2(task_shares, task_to_soc, crosswalk):
    """AEI per-task shares → ISCO-2 weighted by classified_total."""
    task_shares = task_shares.copy()
    task_shares["task_text"] = task_shares["task_text"].str.strip().str.lower()
    joined = task_shares.merge(task_to_soc, on="task_text", how="inner")
    joined = joined.merge(crosswalk[["soc6", "isco4", "isco2"]], on="soc6", how="inner")

    def weighted_mean(g, col):
        w = g["classified_total"]
        return (g[col] * w).sum() / w.sum()

    rows = []
    for isco2, g in joined.groupby("isco2"):
        rows.append({
            "isco2": isco2,
            "augmentation_share": weighted_mean(g, "augmentation_share"),
            "automation_share": weighted_mean(g, "automation_share"),
            "n_tasks_matched": len(g),
        })
    return pd.DataFrame(rows)


def aggregate_felten_aei():
    """Return long-format DataFrame with the felten_aei model's ISCO-2 scores.

    Columns: model, taxonomy, code, metric, value, source, notes.
    Output: 40 ISCO-2 codes × 3 metrics = 120 rows.
    """
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
# Registry
# =====================================================================================
MODELS = {
    "felten_aei": aggregate_felten_aei,
}


# =====================================================================================
# Registry doc (MODELS.md)
# =====================================================================================
_MODELS_MD = """# Score models registry

| model | taxonomy | exposure source | aug/auto source | added | notes |
|---|---|---|---|---|---|
| felten_aei | isco2 | Felten et al. AIOE (Appendix A) | Anthropic Economic Index March 2026 (1P API) | 2026-05-15 | v1 baseline; collaboration patterns per AEI Feb 2025 paper |

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

    if not frames:
        print("No model frames produced; aborting.")
        return

    long_df = pd.concat(frames, ignore_index=True)
    long_df = long_df[["model", "taxonomy", "code", "metric", "value", "source", "notes"]]
    out_path = SCORES_DIR / "scores_long.csv"
    long_df.to_csv(out_path, index=False)
    print(f"\nWrote {out_path}  ({len(long_df):,} rows)")

    for name in MODELS:
        _print_sanity_block(name, long_df[long_df["model"] == name])

    # Write MODELS.md if it doesn't already exist (idempotent — don't clobber edits)
    models_md_path = SCORES_DIR / "MODELS.md"
    if not models_md_path.exists():
        models_md_path.write_text(_MODELS_MD)
        print(f"\nWrote {models_md_path}")
    else:
        print(f"\n{models_md_path} already exists; leaving in place")


if __name__ == "__main__":
    main()
