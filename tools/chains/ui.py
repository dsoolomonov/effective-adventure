import asyncio, os
from playwright.async_api import async_playwright
B = os.environ.get('B', 'http://127.0.0.1:8011'); OUT = os.environ.get('OUT', '/home/ubuntu/chains/shots'); os.makedirs(OUT, exist_ok=True)
async def main():
    async with async_playwright() as p:
        br = await p.chromium.connect_over_cdp('http://localhost:29229'); pg = await br.contexts[0].new_page(); await pg.set_viewport_size({'width': 1600, 'height': 1000}); errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        await pg.goto(B + '/auth/login'); await pg.fill('input[name=password]', os.environ['APP_PASSWORD']); await pg.press('input[name=password]', 'Enter')
        await pg.wait_for_load_state('networkidle')
        await pg.locator('text=Brent Chains').first.click()
        await pg.wait_for_selector('text=Desk read', timeout=90000); await pg.wait_for_timeout(2500)
        await pg.screenshot(path=OUT + '/top.png')
        await pg.locator('text=Who kept the cargoes').first.scroll_into_view_if_needed(); await pg.wait_for_timeout(800); await pg.screenshot(path=OUT + '/charts.png')
        await pg.locator('text=Total number of chained').first.scroll_into_view_if_needed(); await pg.wait_for_timeout(500); await pg.screenshot(path=OUT + '/table.png')
        n = await pg.evaluate("document.querySelectorAll('.js-plotly-plot').length")
        sels = pg.locator('select'); k = await sels.count()
        await sels.nth(k - 1).select_option('Trafigura'); await pg.wait_for_timeout(500)
        cnt = await pg.locator('text=/cargoes · .* mb/').first.text_content()
        await pg.locator('text=Brent forward chains — cargo list').scroll_into_view_if_needed(); await pg.screenshot(path=OUT + '/list.png')
        print('plots', n, 'filter', cnt, 'ERRS', errs); await pg.close()
asyncio.run(main())
