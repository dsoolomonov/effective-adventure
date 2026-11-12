import asyncio, os, sys
from playwright.async_api import async_playwright
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
PW = os.environ["APP_PASSWORD"]
TAG = sys.argv[2] if len(sys.argv) > 2 else "local"
async def main():
    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp("http://localhost:29229")
        ctx = b.contexts[0]
        pg = await ctx.new_page()
        await pg.set_viewport_size({"width": 1600, "height": 1000})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto(BASE + "/auth/login")
        if await pg.locator("input[name=password]").count():
            await pg.fill("input[name=password]", PW)
            await pg.keyboard.press("Enter")
            await pg.wait_for_timeout(2500)
        await pg.goto(BASE + "/")
        await pg.wait_for_selector("text=Asia Balances", timeout=40000)
        await pg.click("button.mp-nav-item:has-text('Asia Balances')")
        await pg.wait_for_selector("text=Desk read", timeout=60000)
        await pg.wait_for_timeout(5000)
        sc = "document.querySelector('.mp-nav-item').closest('div').parentElement.children[1]"
        for prod in ["Gasoil", "Gasoline", "Jet / Kero", "Fuel oil"]:
            await pg.locator('button:visible', has_text=prod).last.click()
            await pg.wait_for_timeout(2500)
            for i, y in enumerate([0, 900, 1800, 2700]):
                await pg.evaluate(f"{sc}.scrollTop={y}")
                await pg.wait_for_timeout(600)
                await pg.screenshot(path=f"/home/ubuntu/asia_bal/shots/{TAG}_{prod.split()[0].lower()}_{i}.png")
        n_plots = await pg.evaluate("document.querySelectorAll('.js-plotly-plot').length")
        print("plots", n_plots, "ERRS", errs)
        await pg.close()
asyncio.run(main())
