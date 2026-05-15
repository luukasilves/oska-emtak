"""Build long-format employment weights per (scenario, taxonomy, code, location).

Each registered scenario emits a long-format DataFrame with columns:
  scenario | taxonomy | code | location_code | location_name | code_label | employed | source

All registered scenarios are concatenated and written to
  data/processed/weights/weights_long.csv

Also writes:
  - data/processed/weights/SCENARIOS.md  (registry of available scenarios)
  - data/crosswalks/CROSSWALKS.md        (initial stub — no crosswalks registered)

To add a new scenario, write a builder returning a DataFrame in the above format
and wire it into the SCENARIOS dict below.
"""

import pandas as pd

from common import (
    AMET_TO_ISCO, CROSSWALKS, RAW, WEIGHTS_DIR,
)


def build_2021_census():
    """Build employment weights from RL21154 (Statistics Estonia REL2021 census).

    Filters Sugu=1 (both sexes) and keeps only sub-group rows (ISCO 2-digit). Emits
    one row per (location, isco2) at taxonomy=isco2.
    """
    df = pd.read_csv(RAW / "RL21154_long.csv")
    # Both sexes only
    df = df[df["Sugu"] == 1].copy()
    # Tag with ISCO codes
    df["isco2"] = df["Amet"].map(lambda c: AMET_TO_ISCO.get(c, (None, None))[1])
    # Sub-group rows only
    sub = df[df["isco2"].notna()].copy()

    out = pd.DataFrame({
        "scenario": "2021_census",
        "taxonomy": "isco2",
        "code": sub["isco2"].astype(str),
        "location_code": sub["Elukoht"].astype(str),
        "location_name": sub["Elukoht_label"].astype(str),
        "code_label": sub["Amet_label"].astype(str),
        "employed": sub["value"].astype(int),
        "source": "rl21154_census2021",
    })
    return out.reset_index(drop=True)


# =====================================================================================
# Registry
# =====================================================================================
SCENARIOS = {
    "2021_census": build_2021_census,
}


_SCENARIOS_MD = """# Weight scenarios registry

| scenario | taxonomy | basis | added | notes |
|---|---|---|---|---|
| 2021_census | isco2 | REL2021 RL21154 raw counts | 2026-05-15 | v1 baseline; register-based, no sampling |

## How to add a new scenario
1. Implement a builder function in `src/build_weights.py` that emits rows with `scenario = <new_id>` and `taxonomy = <one of KNOWN_TAXONOMIES>`.
2. Wire it into the `SCENARIOS = {...}` dict.
3. Re-run `python3 src/build_weights.py`.
4. Add a row to this table.
"""


_CROSSWALKS_MD = """# Inter-taxonomy crosswalks registry

No crosswalks registered yet. v2 scaffolding only uses `taxonomy=isco2` on both scores and weights, so no bridging is needed.

## How to add a new crosswalk
1. Create a file `<from_taxonomy>_to_<to_taxonomy>.csv` in this directory with columns `from_code, to_code, weight`. The `weight` column distributes a from_code's value across multiple to_codes; weights for the same from_code should sum to 1.0 for a clean split (or use 1.0 for one-to-one mappings).
2. Add a row to the table below describing the crosswalk source and methodology.
3. Re-run `python3 src/build_matrix.py` — combos that previously couldn't be built due to taxonomy mismatch will now succeed.

| crosswalk file | from | to | source | added | notes |
|---|---|---|---|---|---|
| (none yet) | | | | | |
"""


def main():
    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    CROSSWALKS.mkdir(parents=True, exist_ok=True)

    frames = []
    print("Building registered scenarios:")
    for name, fn in SCENARIOS.items():
        print(f"  - {name} ...")
        df = fn()
        if df.empty:
            print(f"    WARNING: {name} produced no rows")
            continue
        print(f"    {len(df):,} rows; unique locations: {df['location_code'].nunique()}; "
              f"unique codes: {df['code'].nunique()}")
        frames.append(df)

    if not frames:
        print("No scenario frames produced; aborting.")
        return

    long_df = pd.concat(frames, ignore_index=True)
    cols = ["scenario", "taxonomy", "code", "location_code",
            "location_name", "code_label", "employed", "source"]
    long_df = long_df[cols]
    out_path = WEIGHTS_DIR / "weights_long.csv"
    long_df.to_csv(out_path, index=False)
    print(f"\nWrote {out_path}  ({len(long_df):,} rows)")

    # Write SCENARIOS.md and CROSSWALKS.md if they don't exist
    scenarios_md_path = WEIGHTS_DIR / "SCENARIOS.md"
    if not scenarios_md_path.exists():
        scenarios_md_path.write_text(_SCENARIOS_MD)
        print(f"Wrote {scenarios_md_path}")
    else:
        print(f"{scenarios_md_path} already exists; leaving in place")

    crosswalks_md_path = CROSSWALKS / "CROSSWALKS.md"
    if not crosswalks_md_path.exists():
        crosswalks_md_path.write_text(_CROSSWALKS_MD)
        print(f"Wrote {crosswalks_md_path}")
    else:
        print(f"{crosswalks_md_path} already exists; leaving in place")


if __name__ == "__main__":
    main()
