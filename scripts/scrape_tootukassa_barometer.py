"""Scrape the current-period Töötukassa barometer Excel files via Playwright.

The barometer SPA (https://www.tootukassa.ee/et/baromeeter/tabel) sets a runtime
`selfServiceURL` and uses Apollo GraphQL. The Excel download endpoint requires
an authenticated browser session — direct curl returns the SPA HTML.

Usage:
    pip install playwright openpyxl
    python -m playwright install chromium
    python scripts/scrape_tootukassa_barometer.py [PERIOD_ID]

Default PERIOD_ID is 396 (2026 H1). Drops files into data/raw/tootukassa_barometer/.

Both rating types (LABOUR_BALANCE, LABOUR_DEMAND) are pulled in one run.

The verified Excel URL pattern (for reference; needs cookies from the SPA):
    https://www.tootukassa.ee/etootukassa/baromeeter/table/excel
        ?periodId=<id>&ratingType=<LABOUR_BALANCE|LABOUR_DEMAND>

GraphQL backend (for the curious): POST https://www.tootukassa.ee/web/graphql
"""
import sys, time, pathlib
from playwright.sync_api import sync_playwright


OUT = pathlib.Path('data/raw/tootukassa_barometer')
PERIOD = sys.argv[1] if len(sys.argv) > 1 else '396'
RATING_TYPES = ['LABOUR_BALANCE', 'LABOUR_DEMAND']

OUT.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(
        accept_downloads=True, locale='et-EE',
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'
    )
    for rt in RATING_TYPES:
        page = ctx.new_page()
        url = f'https://www.tootukassa.ee/et/baromeeter/tabel?periodId={PERIOD}&ratingType={rt}'
        print(f"loading {url} ...")
        page.goto(url, wait_until='domcontentloaded', timeout=45000)
        time.sleep(12)  # SPA hydration + GraphQL fetch
        with page.expect_download(timeout=20000) as dl_info:
            page.locator("a:has-text('Salvesta')").first.click()
        dl = dl_info.value
        target = OUT / f'baromeeter_{PERIOD}_{rt}.xlsx'
        dl.save_as(str(target))
        print(f"  -> {target} ({target.stat().st_size} bytes)")
        page.close()
    browser.close()

print(f"\nDone. Next: parse with the recipe in data/raw/tootukassa_barometer/README.md")
