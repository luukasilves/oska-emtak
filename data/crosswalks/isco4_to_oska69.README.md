# OSKA-amet ↔ ISCO-4 crosswalk — not buildable from public sources

The Kutsekoda OSKA system has 16 valdkonnad → 69 ametialagrupid → ~400 ametid.
Mapping to ISCO-08 is internally documented at ISCO-4 (per CEDEFOP), but:

1. **OSKA's internal crosswalk file is not publicly published.** Confirmed by
   inspecting oska.kutsekoda.ee, oskused.ee, and the methodology PDF.
2. **oskused.ee/ametid pages do not expose ISCO/AK codes.** Each of the ~478
   listed ametid (per https://oskused.ee/sitemap.txt) has a Remix-rendered
   page with required skills, duties, working conditions, salary, and training
   pointers — but no ISCO/AK code anywhere in the page text or remix context.
   A direct scrape of those pages yields zero ISCO mentions per page.
3. **Name-based fuzzy matching** of OSKA Estonian occupation names to the
   official AK 2008 / ISCO-08 list is feasible but unreliable for the long
   tail (~120 ametid where titles diverge from ISCO's official Estonian
   labels — many OSKA ametid bundle 2-3 ISCO 4-digit codes).

## Paths to fill this gap
- **(a) Direct request to Kutsekoda** for the internal crosswalk file. The
  fastest and most accurate path.
- **(b) Manual mapping pass** by a human-in-the-loop reviewer using the AK 2008
  list (klassifikaatorid.stat.ee). ~1 working day for 400 ametid.
- **(c) Hybrid LLM + manual review** — feed each OSKA name + description to an
  LLM with the AK 2008 list as context, then review the suggested mappings.

Until one of these is done, the dashboard uses **ISCO-08 official English
titles** as labels at ISCO-4 (loaded by `common.load_isco_labels()`), which
is fine for the analytical layer but loses Estonian-language readability.

This file deliberately has no .csv companion — the absence of one signals
the gap to anyone re-running the pipeline.
