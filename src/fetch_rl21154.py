"""Fetch RL21154 (Employment by ISCO occupation, Sex, and Location) from Statistics Estonia PXWeb API.

Outputs a long-format CSV: location_code, location_name, isco_code, isco_label, isco_level, sex, employed.
"""

import json
import sys
from pathlib import Path

import requests

URL = "https://andmed.stat.ee/api/v1/et/stat/rahvaloendus/rel2021/rahvastiku-majanduslik-aktiivsus/hoivatud-ja-tooranne/RL21154.px"

OUT_DIR = Path(__file__).parent.parent / "data" / "raw"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def fetch_metadata():
    r = requests.get(URL, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_all_data(meta):
    """Pull all rows: every location × every Amet × Sugu='1' (both sexes)."""
    location_values = meta["variables"][2]["values"]
    amet_values = meta["variables"][3]["values"]

    query = {
        "query": [
            {"code": "Aasta", "selection": {"filter": "item", "values": ["2021"]}},
            {"code": "Sugu", "selection": {"filter": "item", "values": ["1"]}},
            {"code": "Elukoht", "selection": {"filter": "item", "values": location_values}},
            {"code": "Amet", "selection": {"filter": "item", "values": amet_values}},
        ],
        "response": {"format": "json-stat2"},
    }
    r = requests.post(URL, json=query, timeout=120)
    r.raise_for_status()
    return r.json()


def jsonstat_to_long(stat):
    """Convert JSON-stat2 response into a long-format list of dicts."""
    dims = stat["id"]  # order of dimensions in the value array
    sizes = stat["size"]
    values = stat["value"]
    labels = {d: stat["dimension"][d]["category"]["label"] for d in dims}
    indices = {d: stat["dimension"][d]["category"]["index"] for d in dims}
    # index maps code -> position; we need reverse and ordered iteration
    ordered_codes = {d: sorted(indices[d], key=lambda c: indices[d][c]) for d in dims}

    rows = []
    # iterate in row-major order matching json-stat2 value array
    def iterate(dim_idx, key, flat_idx):
        if dim_idx == len(dims):
            v = values[flat_idx]
            row = {d: key[d] for d in dims}
            row.update({f"{d}_label": labels[d][key[d]] for d in dims})
            row["value"] = v
            rows.append(row)
            return
        d = dims[dim_idx]
        stride = 1
        for d2 in dims[dim_idx + 1:]:
            stride *= sizes[dims.index(d2)]
        for i, code in enumerate(ordered_codes[d]):
            key[d] = code
            iterate(dim_idx + 1, key, flat_idx + i * stride)

    iterate(0, {}, 0)
    return rows


def main():
    print("Fetching metadata...")
    meta = fetch_metadata()
    (OUT_DIR / "RL21154_metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))

    print("Fetching data (this can take a minute)...")
    stat = fetch_all_data(meta)
    (OUT_DIR / "RL21154_jsonstat.json").write_text(json.dumps(stat, ensure_ascii=False))
    print(f"  raw response saved; total cells: {len(stat['value'])}")

    print("Converting to long format...")
    rows = jsonstat_to_long(stat)
    print(f"  rows: {len(rows)}")

    # write CSV
    import csv
    out_csv = OUT_DIR / "RL21154_long.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {out_csv}")


if __name__ == "__main__":
    main()
