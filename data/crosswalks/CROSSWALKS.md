# Inter-taxonomy crosswalks registry

| crosswalk file | from | to | source | added | notes |
|---|---|---|---|---|---|
| isco4_to_isco2.csv | isco4 | isco2 | ISCO-08 truncation | 2026-05-17 | weight = 1 / n where n = # of ISCO-4 codes per ISCO-2 parent → simple mean (matches Felten convention) when build_matrix distributes-and-sums |
| isco3_to_isco2.csv | isco3 | isco2 | ISCO-08 truncation | 2026-05-17 | same scheme as above; used by jrc_casas (ISCO-3 native) |

## How to add a new crosswalk
1. Create a file `<from_taxonomy>_to_<to_taxonomy>.csv` in this directory with columns `from_taxonomy, from_code, to_taxonomy, to_code, weight`. The `weight` column distributes a from_code's value across multiple to_codes; weights for the same from_code should sum to 1.0 for a clean split (or use 1.0 for one-to-one mappings).
2. Add a row to the table above describing the crosswalk source and methodology.
3. Re-run `python3 src/build_matrix.py` — combos that previously couldn't be built due to taxonomy mismatch will now succeed.
