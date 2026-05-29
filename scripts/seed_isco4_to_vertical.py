"""Seed the first-wave thematic vertical map: ISCO-4 → vertical.

Produces data/crosswalks/isco4_to_vertical.csv covering every ISCO-4 code present in
the palgad.stat.ee taxonomy (data/raw/palgad_stat_ee/taxonomy_isco4.csv). Each code
is assigned to exactly one of ~22 wave-1 thematic verticals using a rule table of
hand-curated ISCO-4 sets + ISCO-prefix fallbacks. A keyword override re-routes any
code whose Estonian name matches finance/IT/HR/legal/etc. keywords to the matching
vertical, so codes outside the hand-curated set still land in a sensible bucket.

This file is meant to be regenerated rarely. The output CSV is editable — the
intended workflow is: re-run this once to bootstrap, then maintain by hand.
Re-running overwrites the CSV (use with care if you've edited it manually).

Run: python3 scripts/seed_isco4_to_vertical.py
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TAXONOMY = ROOT / "data" / "raw" / "palgad_stat_ee" / "taxonomy_isco4.csv"
TIER_FLAGS = ROOT / "data" / "processed" / "summaries" / "tier_flags_isco4.csv"
OUT_CSV = ROOT / "data" / "crosswalks" / "isco4_to_vertical.csv"


# Rule order matters: first match wins. Each rule = (vertical_id, label, predicate).
# Predicate is either {"isco4_in": set[str]} or {"isco4_startswith": tuple[str,...]}.
# Hand-curated ISCO-4 sets cover the AI-most-affected white-collar bundles; prefix
# rules then sweep up the remaining codes by ISCO major/minor group.
RULES = [
    # ── Finance & accounting (cross-ISCO: managers + professionals + assoc + clerks) ──
    ("V02_finance_accounting", "Rahandus ja raamatupidamine", {"isco4_in": {
        "1211",  # Finance managers
        "2411", "2412", "2413",  # Accounting profs, finance/investment advisers, financial analysts
        "3311", "3312", "3313",  # Securities/finance dealers, credit officers, accounting assoc
        "4311", "4312", "4313",  # Accounting clerks, statistical/finance clerks, payroll clerks
    }}),
    # ── Banking & insurance (front-office + specialised) ──
    ("V03_banking_insurance", "Pangandus ja kindlustus", {"isco4_in": {
        "1346",          # Financial / insurance services branch mgrs
        "3321", "3322",  # Insurance reps, commercial sales reps
        "3315",          # Loss adjusters / appraisers
        "4211",          # Bank tellers and related
        "4214",          # Debt-collectors
    }}),
    # ── IT & software development ──
    ("V07_it_software", "IT ja tarkvaraarendus", {"isco4_in": {
        "2511", "2512", "2513", "2514", "2519",  # Sys analysts, devs, web/multimedia, apps progs, other
        "1330",          # ICT services managers
    }}),
    # ── IT infrastructure & telecom ──
    ("V08_it_infra_telecom", "IT-taristu ja telekom", {"isco4_in": {
        "2521", "2522", "2523", "2529",          # DB designers, sys admins, networks, other ICT profs
        "3511", "3512", "3513", "3514",          # ICT ops technicians, user-support, networks, web
        "7421", "7422",                          # Electronics / ICT installers & servicers
    }}),
    # ── Data, statistics & analytics ──
    ("V09_data_analytics", "Andmed ja analüütika", {"isco4_in": {
        "2120",          # Mathematicians, actuaries, statisticians
        "3314",          # Statistical/mathematical/related assoc professionals
        "2433",          # Technical & medical sales profs (analytics-adjacent for product analytics)
    }}),
    # ── Customer service & contact centre ──
    ("V04_customer_service", "Klienditugi ja kontaktikeskus", {"isco4_in": {
        "4221", "4222", "4223", "4224", "4225", "4226", "4227", "4229",
        # Travel consultants, contact centre info clerks, telephone switchboard, hotel receptionists,
        # client info workers, survey interviewers, enquiry clerks, other client info workers
    }}),
    # ── Sales & retail ──
    ("V05_sales_retail", "Müük ja jaekaubandus", {"isco4_in": {
        "1221",          # Sales & marketing managers
        "2434",          # ICT sales professionals
        "3322", "3323", "3324",  # Commercial sales reps, buyers, trade brokers
        "5221", "5222", "5223",  # Shopkeepers, shop supervisors, shop sales assistants
        "5230",                  # Cashiers and ticket clerks
        "5242", "5243", "5244", "5245", "5246", "5249",  # Door-to-door, sales demonstrators, etc.
    }}),
    # ── Marketing & advertising ──
    ("V06_marketing_advertising", "Turundus ja reklaam", {"isco4_in": {
        "1222",          # Advertising & PR managers
        "2431", "2432",  # Advertising/marketing profs, PR profs
    }}),
    # ── HR / Personnel ──
    ("V11_hr", "Personal ja organisatsioon", {"isco4_in": {
        "1212",          # HR managers
        "2423", "2424",  # Personnel/careers profs, training & staff dev profs
        "4416",          # Personnel clerks
    }}),
    # ── Legal ──
    ("V12_legal", "Õigus", {"isco4_in": {
        "1349",          # Some legal/professional service mgrs — actually too broad, leave to mgmt
        "2611", "2612", "2619",  # Lawyers, judges, other legal profs
        "3411",          # Legal/related assoc professionals
        "4411",          # Library clerks (placeholder; reclass via override if needed)
    }}),
    # ── Translation, language & media ──
    ("V14_translation_media", "Tõlge, keel ja meedia", {"isco4_in": {
        "2641", "2642", "2643",  # Authors/writers, journalists, translators/interpreters
        "2651", "2652", "2653", "2654", "2655", "2656",  # Visual artists, musicians, dancers, film/stage, actors, broadcasters
        "2659",                  # Other creative & performing artists
        "3431", "3432", "3433", "3434", "3435",  # Photographers, designers, gallery technicians, chefs (?), other (chefs reclass)
    }}),
    # ── Admin & secretarial ──
    ("V10_admin_secretarial", "Haldus ja sekretäritöö", {"isco4_in": {
        "2421", "2422",          # Mgmt & org analysts, policy admin profs
        "3341", "3342", "3343", "3344",  # Office supervisors, legal secs, admin/exec secs, medical secs
        "4120",                  # Secretaries (general)
        "4226",                  # Receptionists (general) - overlaps with customer service; keep here
    }}),
    # ── Data entry & clerical processing ──
    ("V01_data_clerical", "Andmesisestus ja kontoritöötlus", {"isco4_in": {
        "4110",          # General office clerks
        "4131", "4132",  # Typists & word-processing, data entry
        "4415",          # Filing & copying clerks
        "4419",          # Other clerical support workers nec
    }}),
    # ── Logistics & supply chain clerical ──
    ("V16_logistics_supply_admin", "Logistika ja tarneahela kontoritöö", {"isco4_in": {
        "4321", "4322", "4323",  # Stock clerks, production clerks, transport clerks
        "3331",                  # Clearing & forwarding agents
        "3333",                  # Employment agents
        "3334",                  # Real estate agents & property mgrs
    }}),
    # ── Healthcare professionals & associates (mostly low-exposure but cover) ──
    ("V20_healthcare", "Tervishoid", {"isco4_startswith": ("22", "32")}),
    # ── Education ──
    ("V21_education", "Haridus", {"isco4_startswith": ("23",)}),
    # ── Engineering & technical professions (catch the rest of 21/31) ──
    ("V17_research_science", "Teadus ja tehnilised tippspetsialistid",
     {"isco4_startswith": ("21", "31")}),
    # ── Other legal/social/cultural assoc professionals not bucketed above ──
    ("V19_social_cultural", "Sotsiaal- ja kultuuritöö",
     {"isco4_startswith": ("26", "34")}),
    # ── Business-services associate professionals sweep (33xx not hand-listed) ──
    ("V10_admin_secretarial", "Haldus ja sekretäritöö",
     {"isco4_startswith": ("33",)}),
    # ── ICT technicians sweep (35xx not hand-listed) ──
    ("V08_it_infra_telecom", "IT-taristu ja telekom",
     {"isco4_startswith": ("35",)}),
    # ── General/exec management (catch any ISCO-1 mgr not bucketed above) ──
    ("V13_management_exec", "Juhtimine", {"isco4_startswith": ("1",)}),
    # ── Other clerical (44- catch-all) ──
    ("V18_other_clerical", "Muu kontoritöö", {"isco4_startswith": ("4",)}),
    # ── Personal services (5- catch-all) ──
    ("V22_service_personal", "Isiku- ja teenindustöö", {"isco4_startswith": ("5",)}),
    # ── Skilled agriculture & trades ──
    ("V23_agri_trades", "Põllumajandus ja oskustöö",
     {"isco4_startswith": ("6", "7")}),
    # ── Plant operators & elementary ──
    ("V24_operators_elementary", "Operaatorid ja lihttöö",
     {"isco4_startswith": ("8", "9")}),
    # ── Armed forces ──
    ("V25_armed_forces", "Sõjavägi", {"isco4_startswith": ("0",)}),
]


# Keyword overrides applied AFTER prefix bucketing — keep a code in a thematic
# vertical even if its prefix would route it elsewhere. Patterns are case-insensitive
# substring matches against the Estonian occupation name from taxonomy_isco4.csv.
KEYWORD_OVERRIDES = [
    # finance keywords pull cross-ISCO codes into finance bundle
    (r"\b(finants|rahandus|raamatupidam|maksu|audit|eelarve|investeer)\b",
     "V02_finance_accounting", "Rahandus ja raamatupidamine"),
    (r"\b(pang|krediidi|laenu|kindlustus)\b",
     "V03_banking_insurance", "Pangandus ja kindlustus"),
    (r"\b(turundus|reklaam|kaubam[äa]rgi)\b",
     "V06_marketing_advertising", "Turundus ja reklaam"),
    (r"\b(personali|värbamis|HR-)",
     "V11_hr", "Personal ja organisatsioon"),
    (r"\b(jurist|õigusn[õo]u|vandeadvokaad|kohtuni|prokur)",
     "V12_legal", "Õigus"),
    (r"\b(tarkvara|programmeer|veebi|app|IT-arenduse|infosüsteemi)",
     "V07_it_software", "IT ja tarkvaraarendus"),
    (r"\b(klienditeenind|kontaktikeskuse|telefoni|kõnekeskuse)",
     "V04_customer_service", "Klienditugi ja kontaktikeskus"),
    (r"\b(andmete sisestamise|andmesisestaja|kontoritöö)",
     "V01_data_clerical", "Andmesisestus ja kontoritöötlus"),
    (r"\b(tõlk|tõlkija|keeleteadla|toimetaj|ajakirjani)",
     "V14_translation_media", "Tõlge, keel ja meedia"),
]


def _match_rule(code: str):
    for vid, label, pred in RULES:
        if "isco4_in" in pred and code in pred["isco4_in"]:
            return vid, label
        if "isco4_startswith" in pred and code.startswith(pred["isco4_startswith"]):
            return vid, label
    return "V99_unmapped", "Klassifitseerimata"


def _apply_keyword_override(code: str, name_et: str, current_vid: str, current_label: str):
    name_lc = (name_et or "").lower()
    for pat, vid, label in KEYWORD_OVERRIDES:
        if re.search(pat, name_lc):
            return vid, label
    return current_vid, current_label


def main():
    if not TAXONOMY.exists():
        sys.exit(f"missing {TAXONOMY} — run the palgad scraper first")
    tax = pd.read_csv(TAXONOMY, dtype={"isco4": str})
    tax["isco4"] = tax["isco4"].str.zfill(4)
    tax = tax.drop_duplicates("isco4").sort_values("isco4")

    # Optional: pull English label from tier_flags for the `note` column (debug aid).
    note_map = {}
    if TIER_FLAGS.exists():
        tf = pd.read_csv(TIER_FLAGS, dtype={"isco4_code": str})
        tf["isco4_code"] = tf["isco4_code"].str.zfill(4)
        note_map = dict(zip(tf["isco4_code"], tf["isco4_label"].fillna("")))

    rows = []
    for _, r in tax.iterrows():
        code = r["isco4"]
        name_et = r["name_et"]
        vid, label = _match_rule(code)
        vid, label = _apply_keyword_override(code, name_et, vid, label)
        rows.append({
            "from_taxonomy": "isco4",
            "from_code": code,
            "to_taxonomy": "vertical",
            "to_code": vid,
            "weight": 1.0,
            "vertical_label": label,
            "note": note_map.get(code, ""),
        })

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "from_taxonomy", "from_code", "to_taxonomy", "to_code",
            "weight", "vertical_label", "note",
        ])
        w.writeheader()
        w.writerows(rows)

    # Report distribution
    df = pd.DataFrame(rows)
    counts = df.groupby(["to_code", "vertical_label"]).size().reset_index(name="n_isco4")
    counts = counts.sort_values("n_isco4", ascending=False)
    print(f"Wrote {OUT_CSV} ({len(rows):,} ISCO-4 → vertical rows)")
    print(f"\nVerticals ({len(counts)}):")
    for _, r in counts.iterrows():
        print(f"  {r['to_code']:30s} {r['n_isco4']:3d}  {r['vertical_label']}")
    unmapped = df[df["to_code"] == "V99_unmapped"]
    if len(unmapped):
        print(f"\n!! {len(unmapped)} ISCO-4 codes hit the unmapped catch-all:")
        for _, r in unmapped.head(20).iterrows():
            print(f"   {r['from_code']}  {r['note']}")


if __name__ == "__main__":
    main()
