# Inter-taxonomy crosswalks registry

No crosswalks registered yet. v2 scaffolding only uses `taxonomy=isco2` on both scores and weights, so no bridging is needed.

## How to add a new crosswalk
1. Create a file `<from_taxonomy>_to_<to_taxonomy>.csv` in this directory with columns `from_code, to_code, weight`. The `weight` column distributes a from_code's value across multiple to_codes; weights for the same from_code should sum to 1.0 for a clean split (or use 1.0 for one-to-one mappings).
2. Add a row to the table below describing the crosswalk source and methodology.
3. Re-run `python3 src/build_matrix.py` — combos that previously couldn't be built due to taxonomy mismatch will now succeed.

| crosswalk file | from | to | source | added | notes |
|---|---|---|---|---|---|
| (none yet) | | | | | |
