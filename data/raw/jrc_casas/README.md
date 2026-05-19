# JRC Casas et al. 2025/26 — raw data placeholder

The JRC Casas methodology paper ("Revisiting the occupational impact of AI in the
generative AI era", JRC145832) maps 352 AI benchmarks to 14 cognitive abilities and
127 ISCO-3 occupations. The dataset is distributed as a PDF appendix at
https://publications.jrc.ec.europa.eu/repository/handle/JRC145832 — no public CSV/
xlsx supplementary file exists as of this writing.

To register `jrc_casas` as a model:

1. Open the JRC report PDF and extract the ISCO-3 × exposure table (likely Annex B
   or Appendix Table A).
2. Save as `jrc_casas_isco3.csv` with columns `isco3, exposure_raw`. Exposure can
   be the headline composite or an ability-weighted aggregate; pick whichever the
   appendix designates as the primary measure.
3. Uncomment the `jrc_casas` entry in `src/fetch_ai_scores.py`'s `MODELS` dict.
4. Re-run `python3 src/fetch_ai_scores.py`. The aggregator in that file expects
   the CSV at this path; it will min-max rescale exposure to [0, 1] and emit
   `taxonomy=isco3` rows.

The matrix join then uses `data/crosswalks/isco3_to_isco2.csv` to aggregate JRC's
ISCO-3 scores down to ISCO-2 for the county-level matrix.
