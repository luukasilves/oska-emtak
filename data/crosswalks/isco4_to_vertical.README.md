# isco4_to_vertical.csv — first-wave occupation-vertical map

User-owned, editable mapping from ISCO-4 occupation codes to **thematic functional
verticals** that cross ISCO major-group boundaries. The vertical layer is what the
"vertical × maakond AI-exposure coverage matrix" aggregates ISCO-4 codes into. The
goal is to start broad ("first wave"), then split toward up to 50 verticals as the
analysis matures — entirely by editing this one CSV.

Consumed by `src/build_vertical_matrix.py`. NOT consumed by `src/build_matrix.py`
(its crosswalk path distributes scores, not headcounts).

## Schema

```
from_taxonomy,from_code,to_taxonomy,to_code,weight,vertical_label,note
isco4,4132,vertical,V01_data_clerical,1.0,Andmesisestus ja kontoritöötlus,"data entry clerks"
```

| Column | Meaning |
|---|---|
| `from_taxonomy` | always `isco4` |
| `from_code` | ISCO-4 code, zero-padded to 4 chars |
| `to_taxonomy` | always `vertical` |
| `to_code` | the vertical id, format `V##_short_label` (stable across edits) |
| `weight` | normally 1.0; <1.0 splits a code partially into multiple verticals (rows must sum to ~1.0 per `from_code`) |
| `vertical_label` | Estonian display label (denormalised; aggregator picks the first label per `to_code`) |
| `note` | English ISCO-4 label, for human editing — free-form, ignored by the build |

## How to edit

- **Reassign one occupation** — change the `to_code` (and `vertical_label`) on that row.
- **Merge two verticals** — give both groups the same `to_code` (and same label).
- **Split a vertical** — give some rows a new `to_code`/label. A code can belong to
  two verticals at fractional weight (e.g. `4132` → `V01_data_clerical` at 0.5 and
  `V02_finance_accounting` at 0.5), but the simpler default is single-membership at
  weight 1.0.
- **Add a brand-new vertical** — invent a new `V##_short_label` id; reuse across
  whichever ISCO-4 rows belong to it.

`from_code` rows assigned to >1 vertical with weights not summing to ~1.0 are
flagged by the build with a warning, but the build still runs.

## Re-bootstrapping

The initial CSV was produced by `scripts/seed_isco4_to_vertical.py` using a rule
table (hand-curated ISCO-4 sets for the AI-most-affected bundles + ISCO-prefix
fallbacks + keyword overrides on Estonian names). Re-running that script overwrites
this file, so only re-run it if you want to start over from a different rule set.
The intended workflow is one bootstrap + ongoing hand edits.

## Vertical IDs (wave 1, 23 verticals)

Stable ids; rename labels freely, keep ids fixed so analyses can compare across
edits.

| id | label |
|---|---|
| V01_data_clerical | Andmesisestus ja kontoritöötlus |
| V02_finance_accounting | Rahandus ja raamatupidamine |
| V03_banking_insurance | Pangandus ja kindlustus |
| V04_customer_service | Klienditugi ja kontaktikeskus |
| V05_sales_retail | Müük ja jaekaubandus |
| V06_marketing_advertising | Turundus ja reklaam |
| V07_it_software | IT ja tarkvaraarendus |
| V08_it_infra_telecom | IT-taristu ja telekom |
| V09_data_analytics | Andmed ja analüütika |
| V10_admin_secretarial | Haldus ja sekretäritöö |
| V11_hr | Personal ja organisatsioon |
| V12_legal | Õigus |
| V13_management_exec | Juhtimine |
| V14_translation_media | Tõlge, keel ja meedia |
| V16_logistics_supply_admin | Logistika ja tarneahela kontoritöö |
| V17_research_science | Teadus ja tehnilised tippspetsialistid |
| V18_other_clerical | Muu kontoritöö |
| V19_social_cultural | Sotsiaal- ja kultuuritöö |
| V20_healthcare | Tervishoid |
| V21_education | Haridus |
| V22_service_personal | Isiku- ja teenindustöö |
| V23_agri_trades | Põllumajandus ja oskustöö |
| V24_operators_elementary | Operaatorid ja lihttöö |
| V25_armed_forces | Sõjavägi |
