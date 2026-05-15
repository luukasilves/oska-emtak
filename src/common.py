"""Shared constants and helpers for the Estonia AI-exposure v2 pipeline.

Centralises:
  - directory paths (ROOT, RAW, PROCESSED, CROSSWALKS, ...)
  - AMET_TO_ISCO          mapping from RL21154 Amet codes to (ISCO-1, ISCO-2)
  - TARGET_ISCO2          the 40-cell ISCO 2-digit list published by Estonia
  - KNOWN_TAXONOMIES      controlled vocabulary for the `taxonomy` column
  - load_bls_crosswalk()  BLS SOC-2010 ↔ ISCO-08 (used by score aggregators)
  - parse_rl21154_location_code(code)  → (maakond_code, omav_code, asust_code, type_suffix)
  - load_crosswalk(from_taxonomy, to_taxonomy)   → DataFrame or None
  - build_combined_municipality_geo()  combined ~90-polygon GeoDataFrame
"""

from pathlib import Path

import pandas as pd


# ----- Directory paths ----------------------------------------------------------------
ROOT = Path(__file__).parent.parent
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
CROSSWALKS = ROOT / "data" / "crosswalks"
SCORES_DIR = PROCESSED / "scores"
WEIGHTS_DIR = PROCESSED / "weights"
GEOMETRY_DIR = PROCESSED / "geometry"
MATRICES_DIR = PROCESSED / "matrices"
SUMMARIES_DIR = PROCESSED / "summaries"
CHARTS_DIR = ROOT / "output" / "charts"


# ----- Estonian Amet code → ISCO mapping ----------------------------------------------
# RL21154 publishes 51 categories: 1=total, 2/7/14/20/25/30/34/40/44/51=major groups,
# others=sub-major (ISCO 2-digit). Sub-major rows start with ".." in the label.
# Each row maps to its ISCO 1-digit major group + ISCO 2-digit sub-group (or None for
# the major-group totals themselves).
AMET_TO_ISCO = {
    2:  ("1", None),   # Juhid (Managers)
    3:  ("1", "11"),   # Seadusandjad, kõrgemad ametnikud ja tippjuhid
    4:  ("1", "12"),   # Äriteenindus- ja haldusjuhid
    5:  ("1", "13"),   # Põhitegevuse ja valdkondade juhid
    6:  ("1", "14"),   # Külalismajanduse, kaubandus- jm teenuste juhid
    7:  ("2", None),   # Tippspetsialistid (Professionals)
    8:  ("2", "21"),   # Loodus- ja tehnikateaduste tippspetsialistid
    9:  ("2", "22"),   # Tervishoiu tippspetsialistid
    10: ("2", "23"),   # Pedagoogika tippspetsialistid
    11: ("2", "24"),   # Äri ja halduse tippspetsialistid
    12: ("2", "25"),   # IKT tippspetsialistid
    13: ("2", "26"),   # Õigus-, sotsiaal- ja kultuurivaldkonna tippspetsialistid
    14: ("3", None),   # Tehnikud ja keskastme spetsialistid (Technicians)
    15: ("3", "31"),   # Loodus- ja tehnikateaduste keskastme
    16: ("3", "32"),   # Tervishoiu keskastme
    17: ("3", "33"),   # Äri ja halduse keskastme
    18: ("3", "34"),   # Õigus-, sotsiaal-, kultuuri- keskastme
    19: ("3", "35"),   # IT ja telekommunikatsiooni tehnikud
    20: ("4", None),   # Kontoritöötajad (Clerical)
    21: ("4", "41"),   # Kontoritöötajad
    22: ("4", "42"),   # Klienditeenindajad
    23: ("4", "43"),   # Arvepidamise ja materjaliarvestuse
    24: ("4", "44"),   # Muud kontoritöötajad
    25: ("5", None),   # Teenindus- ja müügitöötajad (Service & Sales)
    26: ("5", "51"),   # Isikuteenindajad
    27: ("5", "52"),   # Müügitöötajad
    28: ("5", "53"),   # Isikuhooldustöötajad
    29: ("5", "54"),   # Pääste-, politsei- ja turvatöötajad
    30: ("6", None),   # Põllumajanduse oskustöölised (Skilled Agric)
    31: ("6", "61"),
    32: ("6", "62"),
    33: ("6", "63"),
    34: ("7", None),   # Oskus- ja käsitöölised (Skilled Trades)
    35: ("7", "71"),   # Ehitustöölised
    36: ("7", "72"),   # Metallitöötluse, masinaehituse
    37: ("7", "73"),   # Käsitöömeistrid, täppisinstrumentide
    38: ("7", "74"),   # Elektri- ja elektroonika
    39: ("7", "75"),   # Toiduaine-, puidu-, rõivatööstuse
    40: ("8", None),   # Seadme- ja masinaoperaatorid (Plant Operators)
    41: ("8", "81"),   # Seadme- ja masinaoperaatorid
    42: ("8", "82"),   # Koostajad
    43: ("8", "83"),   # Mootorsõidukite ja liikurmasinate juhid
    44: ("9", None),   # Lihttöölised (Elementary)
    45: ("9", "91"),   # Puhastustöölised ja abilised
    46: ("9", "92"),   # Põllumajanduse lihttöölised
    47: ("9", "93"),   # Mäetööstuse, ehituse, töötleva tööstuse, veonduse
    48: ("9", "94"),   # Toitlustuse abitöölised
    49: ("9", "95"),   # Tänaval jms kohtades teenuse osutajad
    50: ("9", "96"),   # Jäätmekäitluse jm
    51: ("0", None),   # Sõjaväelased (Armed Forces)
}


# Estonian RL21154 publishes these 40 ISCO 2-digit groups
TARGET_ISCO2 = [
    "11", "12", "13", "14",                        # Managers
    "21", "22", "23", "24", "25", "26",            # Professionals
    "31", "32", "33", "34", "35",                  # Technicians
    "41", "42", "43", "44",                        # Clerical
    "51", "52", "53", "54",                        # Service & Sales
    "61", "62", "63",                              # Skilled agriculture
    "71", "72", "73", "74", "75",                  # Skilled trades
    "81", "82", "83",                              # Plant operators
    "91", "92", "93", "94", "95", "96",            # Elementary
]


# Controlled vocabulary for the `taxonomy` column. Append new entries over time.
KNOWN_TAXONOMIES = [
    "isco1", "isco2", "isco3", "isco4",
    "soc6", "onet_soc8", "oska69",
]


# Known EHAK omavalitsus code remaps: GeoJSON vs Statistics Estonia have a handful of
# version mismatches; we map RL21154 codes → the GeoJSON codes that hold the polygons.
OMAV_REMAP = {
    "0305": "0304",  # Kiili vald
    "0719": "0718",  # Saku vald
    "0725": "0726",  # Saue vald
    "0502": "0503",  # Märjamaa vald
}


# ----- Loaders / helpers --------------------------------------------------------------

def load_bls_crosswalk():
    """BLS SOC-2010 ↔ ISCO-08 crosswalk → DataFrame.

    Returns columns: soc6, soc_title, isco4 (4-char zero-padded), isco_title, isco2.
    Many-to-many: a SOC may map to multiple ISCO codes and vice versa.
    """
    xls = pd.ExcelFile(RAW / "bls_soc_isco_crosswalk.xls")
    df = pd.read_excel(xls, "2010 SOC to ISCO-08", header=6)
    df = df.rename(columns={
        "2010 SOC Code": "soc6",
        "2010 SOC Title": "soc_title",
        "ISCO-08 Code": "isco4",
        "ISCO-08 Title EN": "isco_title",
    })
    df = df[["soc6", "soc_title", "isco4", "isco_title"]].dropna(subset=["soc6", "isco4"])
    df["isco4"] = df["isco4"].astype(int).astype(str).str.zfill(4)
    df["isco2"] = df["isco4"].str[:2]
    df["soc6"] = df["soc6"].astype(str).str.strip()
    return df


def parse_rl21154_location_code(code):
    """Decompose a 14-character RL21154 Elukoht code.

    Returns (maakond_code, omav_code, asust_code, type_suffix) or None for shorter
    aggregate codes (e.g. Estonia total or region totals).
    """
    code_str = str(code)
    if len(code_str) != 14:
        return None
    return (
        code_str[0:4],
        code_str[4:8],
        code_str[8:12],
        code_str[12:14],
    )


def load_crosswalk(from_taxonomy: str, to_taxonomy: str):
    """Return DataFrame with columns from_code, to_code, weight; or None if absent.

    Looks for data/crosswalks/<from>_to_<to>.csv. The on-disk file may have a richer
    schema (from_taxonomy, from_code, to_taxonomy, to_code, weight per the registry
    spec) but the returned frame is normalised to from_code/to_code/weight only.
    """
    path = CROSSWALKS / f"{from_taxonomy}_to_{to_taxonomy}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, dtype={"from_code": str, "to_code": str})
    if "weight" not in df.columns:
        df["weight"] = 1.0
    return df[["from_code", "to_code", "weight"]].copy()


def build_combined_municipality_geo():
    """Build the ~90-polygon GeoDataFrame: omavalitsus minus Tallinn/Kohtla-Järve
    plus the 13 linnaosa polygons from asustusyksus.geojson (TYYP=6).
    """
    import geopandas as gpd

    om = gpd.read_file(RAW / "omavalitsus.geojson")
    au = gpd.read_file(RAW / "asustusyksus.geojson")
    linnaosa = au[au["TYYP"] == "6"].copy()
    om_filtered = om[~om["OKOOD"].isin(["0784", "0321"])].copy()
    om_filtered["join_code"] = om_filtered["OKOOD"]
    om_filtered["join_type"] = "omav"
    om_filtered["label"] = om_filtered["ONIMI"]
    linnaosa["join_code"] = linnaosa["AKOOD"]
    linnaosa["join_type"] = "linnaosa"
    linnaosa["label"] = linnaosa["ANIMI"]
    cols = ["join_code", "join_type", "label", "MKOOD", "MNIMI", "geometry"]
    combined = pd.concat([om_filtered[cols], linnaosa[cols]], ignore_index=True)
    return gpd.GeoDataFrame(combined, crs=om.crs)
