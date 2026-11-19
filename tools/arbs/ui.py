import asyncio, os
from playwright.async_api import async_playwright
B = os.environ.get('B', 'http://127.0.0.1:8011'); OUT = os.environ.get('OUT', '/home/ubuntu/arbs/shots'); os.makedirs(OUT, exist_ok=True)
async def main():
    async with async_playwright() as p:
        br = await p.chromium.connect_over_cdp('http://localhost:29229'); pg = await br.contexts[0].new_page(); await pg.set_viewport_size({'width': 1600, 'height': 1000}); errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        await pg.goto(B + '/auth/login'); await pg.fill('input[name=password]', os.environ['APP_PASSWORD']); await pg.press('input[name=password]', 'Enter')
        await pg.wait_for_load_state('networkidle')
        await pg.locator('text=Crude Arbs').first.click()
        await pg.wait_for_selector('text=Desk read', timeout=90000); await pg.wait_for_timeout(2500)
        await pg.screenshot(path=OUT + '/top.png')
        await pg.locator('text=Sweet arb map').first.scroll_into_view_if_needed(); await pg.wait_for_timeout(800); await pg.screenshot(path=OUT + '/map.png')
        sels = pg.locator('select'); k = await sels.count()
        await sels.nth(k - 2).select_option('Jan-27'); await pg.wait_for_timeout(800); await pg.screenshot(path=OUT + '/map_jan.png')
        await sels.nth(k - 2).select_option('Mar-27')
        await sels.nth(k - 1).select_option('Azeri Lt.'); await pg.wait_for_timeout(800)
        await pg.locator('text=Grade arb curve').first.scroll_into_view_if_needed(); await pg.wait_for_timeout(500); await pg.screenshot(path=OUT + '/curve.png')
        await pg.locator('text=Sweet arb tables').first.scroll_into_view_if_needed(); await pg.wait_for_timeout(500); await pg.screenshot(path=OUT + '/sweet.png')
        await pg.locator('text=Sour arb tables').first.scroll_into_view_if_needed(); await pg.wait_for_timeout(500); await pg.screenshot(path=OUT + '/sour.png')
        n = await pg.evaluate("document.querySelectorAll('.js-plotly-plot').length")
        print('selects', k, 'plots', n, 'ERRS', errs); await pg.close()
asyncio.run(main())
