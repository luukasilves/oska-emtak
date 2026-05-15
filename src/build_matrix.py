"""Build per-(model, scenario) AI-exposure matrices and maakond summaries.

Inputs:
  data/processed/scores/scores_long.csv      (from src/fetch_ai_scores.py)
  data/processed/weights/weights_long.csv    (from src/build_weights.py)
  data/crosswalks/<from>_to_<to>.csv         (optional; bridges differing taxonomies)

For each (model, scenario) combination:
  - If scores and weights share a taxonomy → direct join on (taxonomy, code).
  - If they differ → look up data/crosswalks/<from>_to_<to>.csv. Distribute scores
    across mapped weight codes using the `weight` column. Skip the combo with a
    warning if the crosswalk file is missing.

Outputs (one per viable combo):
  data/processed/matrices/matrix_<model>_<scenario>.csv
  data/processed/summaries/maakond_summary_<model>_<scenario>.csv

Also writes the combined municipality geometry once (idempotent):
  data/processed/geometry/estonia_municipalities_combined.geojson
"""

import pandas as pd

from common import (
    GEOMETRY_DIR, MATRICES_DIR, SCORES_DIR, SUMMARIES_DIR, WEIGHTS_DIR,
    build_combined_municipality_geo, load_crosswalk,
)


def _ensure_combined_geometry():
    """Write the combined municipality geometry once. No-op if already present."""
    GEOMETRY_DIR.mkdir(parents=True, exist_ok=True)
    out_path = GEOMETRY_DIR / "estonia_municipalities_combined.geojson"
    if out_path.exists():
        print(f"  geometry already exists: {out_path}")
        return
    gdf = build_combined_municipality_geo()
    gdf.to_file(out_path, driver="GeoJSON")
    print(f"  wrote {out_path} ({len(gdf)} polygons)")


def _pivot_scores(scores_long: pd.DataFrame, model: str) -> pd.DataFrame:
    """Wide DataFrame: one row per (taxonomy, code) with columns exposure /
    augmentation_share / automation_share / score_source.
    """
    sub = scores_long[scores_long["model"] == model].copy()
    if sub.empty:
        return pd.DataFrame()
    wide = sub.pivot_table(index=["taxonomy", "code"], columns="metric",
                           values="value", aggfunc="first").reset_index()
    # Carry one source flag per (taxonomy, code) — pick the first non-null value
    src = (sub.sort_values("metric")
              .groupby(["taxonomy", "code"])["source"]
              .first()
              .reset_index()
              .rename(columns={"source": "score_source"}))
    wide = wide.merge(src, on=["taxonomy", "code"], how="left")
    # Ensure all three metric columns exist
    for col in ("exposure", "augmentation_share", "automation_share"):
        if col not in wide.columns:
            wide[col] = None
    return wide[["taxonomy", "code", "exposure",
                 "augmentation_share", "automation_share", "score_source"]]


def _build_combo(model: str, scores_wide: pd.DataFrame, scenario: str,
                 weights: pd.DataFrame, scores_taxonomy: str,
                 weights_taxonomy: str):
    """Return (matrix_df, summary_df, crosswalk_label) or (None, None, None) if
    the combo is unbuildable (taxonomy mismatch with no crosswalk on disk).
    """
    if scores_taxonomy == weights_taxonomy:
        # Direct join on code
        scores_join = scores_wide[scores_wide["taxonomy"] == scores_taxonomy] \
            .drop(columns="taxonomy") \
            .rename(columns={"code": "_code"})
        joined = weights.merge(scores_join, left_on="code", right_on="_code",
                               how="inner").drop(columns=["_code"])
        crosswalk_label = "direct"
    else:
        crosswalk_df = load_crosswalk(scores_taxonomy, weights_taxonomy)
        if crosswalk_df is None:
            print(f"  SKIP ({model} × {scenario}): no crosswalk "
                  f"{scores_taxonomy}_to_{weights_taxonomy}.csv on disk")
            return None, None, None
        # Distribute each score across its target codes with the given weight, then
        # collapse (in case multiple from_codes feed the same to_code).
        s_sub = scores_wide[scores_wide["taxonomy"] == scores_taxonomy] \
            .drop(columns="taxonomy")
        dist = s_sub.merge(crosswalk_df, left_on="code", right_on="from_code",
                           how="inner")
        for col in ("exposure", "augmentation_share", "automation_share"):
            dist[col] = dist[col] * dist["weight"]
        agg = dist.groupby("to_code", as_index=False).agg(
            exposure=("exposure", "sum"),
            augmentation_share=("augmentation_share", "sum"),
            automation_share=("automation_share", "sum"),
            score_source=("score_source", "first"),
        )
        joined = weights.merge(agg, left_on="code", right_on="to_code",
                               how="inner").drop(columns=["to_code"])
        crosswalk_label = f"{scores_taxonomy}_to_{weights_taxonomy}.csv"

    if joined.empty:
        print(f"  SKIP ({model} × {scenario}): join produced 0 rows")
        return None, None, None

    joined["model"] = model
    joined["scenario"] = scenario
    joined["crosswalk"] = crosswalk_label
    joined["opportunity"] = joined["exposure"] * joined["augmentation_share"]
    joined["risk"] = joined["exposure"] * joined["automation_share"]
    joined = joined.rename(columns={"source": "weight_source"})

    matrix_cols = [
        "model", "scenario", "taxonomy", "location_code", "location_name",
        "code", "code_label", "employed",
        "exposure", "augmentation_share", "automation_share",
        "opportunity", "risk",
        "score_source", "weight_source", "crosswalk",
    ]
    matrix = joined[matrix_cols].copy()

    # Maakond summary: filter to MAAKOND rows and roll up
    mk = matrix[matrix["location_name"].str.endswith("MAAKOND", na=False)].copy()
    mk["opp_w"] = mk["opportunity"] * mk["employed"]
    mk["risk_w"] = mk["risk"] * mk["employed"]
    mk["exp_w"] = mk["exposure"] * mk["employed"]
    summary = mk.groupby("location_name", as_index=False).agg(
        total_employed=("employed", "sum"),
        opportunity_weighted=("opp_w", "sum"),
        risk_weighted=("risk_w", "sum"),
        exposure_weighted=("exp_w", "sum"),
    )
    summary["opportunity_avg"] = summary["opportunity_weighted"] / summary["total_employed"]
    summary["risk_avg"] = summary["risk_weighted"] / summary["total_employed"]
    summary["exposure_avg"] = summary["exposure_weighted"] / summary["total_employed"]
    summary["model"] = model
    summary["scenario"] = scenario
    summary = summary[[
        "model", "scenario", "location_name", "total_employed",
        "exposure_avg", "opportunity_avg", "risk_avg",
        "exposure_weighted", "opportunity_weighted", "risk_weighted",
    ]].sort_values("total_employed", ascending=False).reset_index(drop=True)

    return matrix, summary, crosswalk_label


def main():
    MATRICES_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading inputs...")
    scores_long = pd.read_csv(SCORES_DIR / "scores_long.csv",
                              dtype={"taxonomy": str, "code": str})
    weights_long = pd.read_csv(WEIGHTS_DIR / "weights_long.csv",
                               dtype={"taxonomy": str, "code": str,
                                      "location_code": str})
    print(f"  scores_long: {len(scores_long):,} rows")
    print(f"  weights_long: {len(weights_long):,} rows")

    print("\nEnsuring combined geometry...")
    _ensure_combined_geometry()

    # Map model → taxonomy and scenario → taxonomy. Each model/scenario should be
    # single-taxonomy per the v2 spec; if not, take the most common.
    model_taxonomy = (scores_long.groupby("model")["taxonomy"]
                      .agg(lambda s: s.mode().iloc[0]).to_dict())
    scenario_taxonomy = (weights_long.groupby("scenario")["taxonomy"]
                         .agg(lambda s: s.mode().iloc[0]).to_dict())

    models = sorted(model_taxonomy)
    scenarios = sorted(scenario_taxonomy)
    print(f"\nModels: {models}")
    print(f"Scenarios: {scenarios}")

    # Pre-pivot scores wide for each model
    pivots = {m: _pivot_scores(scores_long, m) for m in models}

    print("\nBuilding (model × scenario) combos:")
    n_built = 0
    n_skipped = 0
    for m in models:
        for s in scenarios:
            print(f"\n[{m} × {s}]")
            scores_tax = model_taxonomy[m]
            weights_tax = scenario_taxonomy[s]
            weights_sub = weights_long[weights_long["scenario"] == s].copy()
            matrix, summary, crosswalk_label = _build_combo(
                m, pivots[m], s, weights_sub, scores_tax, weights_tax,
            )
            if matrix is None:
                n_skipped += 1
                continue

            matrix_path = MATRICES_DIR / f"matrix_{m}_{s}.csv"
            summary_path = SUMMARIES_DIR / f"maakond_summary_{m}_{s}.csv"
            matrix.to_csv(matrix_path, index=False)
            summary.to_csv(summary_path, index=False)
            n_built += 1

            taxonomy_used = matrix["taxonomy"].iloc[0]
            top3 = summary.nlargest(3, "exposure_weighted")[
                ["location_name", "total_employed", "exposure_weighted"]
            ]
            print(f"  crosswalk: {crosswalk_label}   taxonomy used: {taxonomy_used}")
            print(f"  matrix rows: {len(matrix):,}  total employed: "
                  f"{int(matrix['employed'].sum()):,}")
            print(f"  top3 maakond by total exposure:")
            for _, r in top3.iterrows():
                print(f"    {r['location_name']:<20s} "
                      f"emp={int(r['total_employed']):>8,}  "
                      f"exp_w={r['exposure_weighted']:>12,.2f}")
            print(f"  wrote {matrix_path.name}, {summary_path.name}")

    print(f"\nDone. Built {n_built} combo(s); skipped {n_skipped}.")


if __name__ == "__main__":
    main()
