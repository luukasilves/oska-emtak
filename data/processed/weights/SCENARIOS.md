# Weight scenarios registry

| scenario | taxonomy | basis | added | notes |
|---|---|---|---|---|
| 2021_census | isco2 | REL2021 RL21154 raw counts | 2026-05-15 | v1 baseline; register-based, no sampling |

## How to add a new scenario
1. Implement a builder function in `src/build_weights.py` that emits rows with `scenario = <new_id>` and `taxonomy = <one of KNOWN_TAXONOMIES>`.
2. Wire it into the `SCENARIOS = {...}` dict.
3. Re-run `python3 src/build_weights.py`.
4. Add a row to this table.
