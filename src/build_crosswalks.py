"""Build ISCO-level truncation crosswalks for build_matrix.py.

Writes:
  data/crosswalks/isco4_to_isco2.csv   columns: from_code, to_code, weight
  data/crosswalks/isco3_to_isco2.csv   columns: from_code, to_code, weight

`from_code` is the source ISCO-N code, `to_code` is its ISCO-2 parent (truncation),
`weight = 1 / n` where n is the number of source codes sharing that ISCO-2 parent.

Why 1/n: build_matrix.py multiplies each source score by `weight` then sums into
the target code (lines 92-99 of build_matrix.py). With 1/n weights the sum is a
simple mean — which matches the Felten convention used by aggregate_felten_aei.

The universe of source codes is the union of:
  - all ISCO-4 codes in the BLS SOC↔ISCO crosswalk (~436 codes), and
  - all ISCO-4 codes appearing in scores_long.csv (covers WP140 and any future
    sources whose ISCO universe extends beyond BLS).

Idempotent: re-runs overwrite the CSVs.
"""

from pathlib import Path

import pandas as pd

from common import CROSSWALKS, SCORES_DIR, load_bls_crosswalk


def _isco_universe(level: int) -> list[str]:
    """All distinct ISCO codes at `level` that appear in BLS or scores_long.csv."""
    bls = load_bls_crosswalk()
    codes = set(bls["isco4"].astype(str).str[:level])
    scores_path = SCORES_DIR / "scores_long.csv"
    if scores_path.exists():
        s = pd.read_csv(scores_path, dtype={"code": str, "taxonomy": str})
        # If a model is registered at isco4 or isco3, harvest those codes too
        for tax in ("isco4", "isco3"):
            sub = s[s["taxonomy"] == tax]
            if not sub.empty:
                codes |= set(sub["code"].astype(str).str[:level])
    return sorted(c for c in codes if c.isdigit())


def _build_truncation_crosswalk(level: int) -> pd.DataFrame:
    """ISCO-<level> → ISCO-2 truncation with weight = 1/n per ISCO-2 group."""
    universe = _isco_universe(level)
    df = pd.DataFrame({"from_code": universe})
    df["to_code"] = df["from_code"].str[:2]
    counts = df.groupby("to_code").size().rename("n").reset_index()
    df = df.merge(counts, on="to_code")
    df["weight"] = 1.0 / df["n"]
    # Add the source/target taxonomy labels per the registry schema documented
    # in CROSSWALKS.md (build_matrix loader strips them, but file-level
    # consumers like dashboards expect them)
    df["from_taxonomy"] = f"isco{level}"
    df["to_taxonomy"] = "isco2"
    return df[["from_taxonomy", "from_code", "to_taxonomy", "to_code", "weight"]]


_CROSSWALKS_MD = """# Inter-taxonomy crosswalks registry

| crosswalk file | from | to | source | added | notes |
|---|---|---|---|---|---|
| isco4_to_isco2.csv | isco4 | isco2 | ISCO-08 truncation | 2026-05-17 | weight = 1 / n where n = # of ISCO-4 codes per ISCO-2 parent → simple mean (matches Felten convention) when build_matrix distributes-and-sums |
| isco3_to_isco2.csv | isco3 | isco2 | ISCO-08 truncation | 2026-05-17 | same scheme as above; used by jrc_casas (ISCO-3 native) |

## How to add a new crosswalk
1. Create a file `<from_taxonomy>_to_<to_taxonomy>.csv` in this directory with columns `from_taxonomy, from_code, to_taxonomy, to_code, weight`. The `weight` column distributes a from_code's value across multiple to_codes; weights for the same from_code should sum to 1.0 for a clean split (or use 1.0 for one-to-one mappings).
2. Add a row to the table above describing the crosswalk source and methodology.
3. Re-run `python3 src/build_matrix.py` — combos that previously couldn't be built due to taxonomy mismatch will now succeed.
"""


def main():
    CROSSWALKS.mkdir(parents=True, exist_ok=True)
    for level in (4, 3):
        df = _build_truncation_crosswalk(level)
        out = CROSSWALKS / f"isco{level}_to_isco2.csv"
        df.to_csv(out, index=False)
        print(f"Wrote {out}  ({len(df):,} rows)")
        # Sanity print: weights per ISCO-2 should sum to 1.0
        sums = df.groupby("to_code")["weight"].sum()
        bad = sums[~sums.between(0.999, 1.001)]
        if len(bad):
            print(f"  WARNING: {len(bad)} ISCO-2 buckets with weight sum != 1.0: "
                  f"{bad.to_dict()}")
        else:
            print(f"  sanity: all {len(sums)} ISCO-2 buckets have weight sum = 1.0")

    md_path = CROSSWALKS / "CROSSWALKS.md"
    md_path.write_text(_CROSSWALKS_MD)
    print(f"Wrote {md_path}")


if __name__ == "__main__":
    main()
