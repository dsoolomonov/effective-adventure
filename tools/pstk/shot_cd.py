import asyncio, sys
from playwright.async_api import async_playwright
URL, PW, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
async def main():
    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp("http://localhost:29229"); ctx = b.contexts[0]
        pg = await ctx.new_page(); await pg.set_viewport_size({"width": 1600, "height": 1000})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto(URL + "/auth/login"); await pg.fill("input[name=password]", PW); await pg.press("input[name=password]", "Enter")
        await pg.wait_for_timeout(4000)
        await pg.evaluate("""()=>{const x=[...document.querySelectorAll('button')].find(e=>e.textContent.trim().endsWith('Crude Differentials'));x&&x.click();}""")
        await pg.wait_for_timeout(15000)
        await pg.screenshot(path=OUT + "_1.png")
        await pg.evaluate("""()=>{const t=[...document.querySelectorAll('div')].find(e=>e.textContent.startsWith('North Sea FOB diffs vs Dated Brent strip — $/bbl'));t&&t.scrollIntoView();}""")
        await pg.wait_for_timeout(1500); await pg.screenshot(path=OUT + "_2.png")
        await pg.evaluate("""()=>{const t=[...document.querySelectorAll('div')].find(e=>e.textContent.startsWith('Seasonal — one grade'));t&&t.scrollIntoView();}""")
        await pg.wait_for_timeout(1500); await pg.screenshot(path=OUT + "_3.png")
        n = await pg.evaluate("()=>document.querySelectorAll('.js-plotly-plot').length")
        print("plots", n, "errors", errs)
        await pg.close()
asyncio.run(main())
