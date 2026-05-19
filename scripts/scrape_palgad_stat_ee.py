"""Scrape worker headcounts per ISCO-4 occupation from palgad.stat.ee.

Statistics Estonia publishes salary-application data at ISCO-4 × maakond ×
quarterly from administrative records (TÖR + tax declarations), with cells
suppressed when fewer than 20 persons. This is the only public dataset that
breaks employment down at the 4-digit occupation level for Estonia.

The application's frontend (palgad.stat.ee) is a Drupal SPA. Its data is
served by a chart endpoint:

    GET /api/charts/<chart>/<isco4>/<year>/<quarter>/<salary>/<county>/<age>/<gender>

Notable chart names:
- workers_total_section   - worker counts (M / F) at the filtered cell
- county_average_salary-chart - salary
- gender_salary_comparison-chart - M/F salary comparison

The ISCO-4 taxonomy is embedded in the page's hidden 'occupations overlay'.
We first extract it from the live page, then loop over all codes.

Outputs (under data/raw/palgad_stat_ee/):
- occupations_overlay.html    - cached overlay HTML (taxonomy source)
- taxonomy_isco4.csv          - 428 ISCO-4 groups (isco4, name_et)
- taxonomy_leaves.csv         - 2,744 leaf occupations (isco4, leaf_id, name)
- workers_raw/{isco4}_{county}.html - per-cell raw response (one file each)
- workers_long.csv            - parsed long format: isco4, county, gender, count

Usage:
    python -m playwright install chromium  # one-time, ~92 MB
    pip install playwright
    python scripts/scrape_palgad_stat_ee.py [--counties=all|each]

Polite default: 1.0 s between requests. With 428 codes × (1 national + 15
maakonnad), expect:
  --counties=all  : ~430 requests, ~8 min
  --counties=each : ~6,850 requests, ~2 hours (recommended for full data)

Cells with fewer than 20 persons are suppressed by stat.ee — their HTML
returns no workers_total--table; we record those as count=NaN.
"""
from __future__ import annotations

import argparse
import csv
import pathlib
import re
import sys
import time
import urllib.parse

sys.path.insert(0, '/Users/luukas/Library/Python/3.9/lib/python/site-packages')
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).parent.parent
OUT = ROOT / 'data' / 'raw' / 'palgad_stat_ee'
WORKERS_RAW = OUT / 'workers_raw'
COUNTIES = {
    'all': 'Kogu Eesti',
    'harju': 'Harju maakond', 'hiiu': 'Hiiu maakond', 'ida_viru': 'Ida-Viru maakond',
    'jogeva': 'Jõgeva maakond', 'jarva': 'Järva maakond', 'laane': 'Lääne maakond',
    'laane_viru': 'Lääne-Viru maakond', 'polva': 'Põlva maakond', 'parnu': 'Pärnu maakond',
    'rapla': 'Rapla maakond', 'saare': 'Saare maakond', 'tartu': 'Tartu maakond',
    'valga': 'Valga maakond', 'viljandi': 'Viljandi maakond', 'voru': 'Võru maakond',
}

URL_TPL = ("https://palgad.stat.ee/api/charts/workers_total_section/"
           "{isco4}/{year}/{quarter}/{salary}/{county}/{age}/{gender}")

ROW_RE = re.compile(r'<th>([^<]+)</th>\s*<td>([^<]+)</td>')
TABLE_RE = re.compile(r'<table class="workers_total--table">(.+?)</table>', re.S)


def extract_taxonomy_via_browser():
    """Fetch palgad.stat.ee front page and dump the occupations overlay HTML.

    Re-extracts taxonomy_isco4.csv even if a stale copy exists, so we always
    track the current state of the system.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(locale='et-EE')
        page = ctx.new_page()
        page.goto('https://palgad.stat.ee/', wait_until='networkidle', timeout=60000)
        time.sleep(3)
        overlay = page.evaluate(
            "() => document.querySelector('#edit-occupations-overlay').outerHTML"
        )
        (OUT / 'occupations_overlay.html').write_text(overlay)
        browser.close()

    html = (OUT / 'occupations_overlay.html').read_text()
    group_pat = re.compile(r'<a\s+href="#"\s+data-parent-id="(\d+)">([^<]+)</a>')
    groups = {m.group(1): m.group(2) for m in group_pat.finditer(html)}

    with open(OUT / 'taxonomy_isco4.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['isco4', 'name_et'])
        w.writeheader()
        for code in sorted(groups):
            w.writerow({'isco4': code, 'name_et': groups[code]})
    print(f"Wrote {OUT/'taxonomy_isco4.csv'} ({len(groups)} ISCO-4 groups)")
    return sorted(groups), groups


def parse_workers(html: str):
    """Return list[(gender, count)] or None if suppressed."""
    m = TABLE_RE.search(html)
    if not m:
        return None
    rows = []
    for label, val in ROW_RE.findall(m.group(1)):
        # val like "277 707" — strip non-breaking spaces and commas
        clean = re.sub(r'\s+', '', val).replace('\xa0', '')
        try:
            count = int(clean)
        except ValueError:
            continue
        rows.append((label.strip(), count))
    return rows or None


def scrape_counts(counties_mode: str, year: str, quarter: str,
                  delay: float = 1.0):
    codes, names = extract_taxonomy_via_browser()
    WORKERS_RAW.mkdir(parents=True, exist_ok=True)
    counties_to_query = ['all'] if counties_mode == 'all' else list(COUNTIES)

    rows_out = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(locale='et-EE')
        total = len(codes) * len(counties_to_query)
        done = 0
        t_start = time.time()
        for isco4 in codes:
            for county in counties_to_query:
                done += 1
                url = URL_TPL.format(isco4=isco4, year=year, quarter=quarter,
                                     salary='average', county=county,
                                     age='all', gender='all')
                fname = WORKERS_RAW / f'{isco4}_{county}.html'
                if fname.exists() and fname.stat().st_size > 1000:
                    raw = fname.read_text()
                else:
                    resp = ctx.request.get(url, timeout=30000)
                    raw = resp.text() if resp.status == 200 else ''
                    fname.write_text(raw)
                    time.sleep(delay)
                rows = parse_workers(raw)
                if rows is None:
                    rows_out.append({
                        'isco4': isco4, 'name_et': names[isco4],
                        'county': county, 'county_name': COUNTIES[county],
                        'gender': 'all', 'count': '',  # suppressed/missing
                        'source_url': url,
                    })
                else:
                    for label, count in rows:
                        gender = {'Mehed': 'M', 'Naised': 'F', 'Kokku': 'all'}.get(label, label)
                        rows_out.append({
                            'isco4': isco4, 'name_et': names[isco4],
                            'county': county, 'county_name': COUNTIES[county],
                            'gender': gender, 'count': count,
                            'source_url': url,
                        })
                if done % 25 == 0 or done == total:
                    elapsed = time.time() - t_start
                    rate = done / elapsed if elapsed else 0
                    eta = (total - done) / rate / 60 if rate else 0
                    print(f"  [{done}/{total}] {isco4} {county}  "
                          f"rate={rate:.1f}/s  eta={eta:.1f} min")
        browser.close()

    out_csv = OUT / 'workers_long.csv'
    with open(out_csv, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['isco4', 'name_et', 'county', 'county_name',
                                          'gender', 'count', 'source_url'])
        w.writeheader()
        w.writerows(rows_out)
    print(f"\nWrote {out_csv} ({len(rows_out):,} rows)")

    # quick sanity
    by_gender = {}
    for r in rows_out:
        if r['count'] != '':
            by_gender[r['gender']] = by_gender.get(r['gender'], 0) + int(r['count'])
    print(f"sum by gender (across all cells): {by_gender}")
    suppressed = sum(1 for r in rows_out if r['count'] == '')
    print(f"suppressed cells: {suppressed}/{len(rows_out)}")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--counties', default='all', choices=['all', 'each'],
                    help="'all'=national totals only; 'each'=loop 15 maakonnad too")
    ap.add_argument('--year', default='2025')
    ap.add_argument('--quarter', default='Q4')
    ap.add_argument('--delay', type=float, default=1.0)
    args = ap.parse_args()
    print(f"Scraping palgad.stat.ee  year={args.year} quarter={args.quarter} "
          f"counties={args.counties}  delay={args.delay}s")
    scrape_counts(args.counties, args.year, args.quarter, args.delay)
