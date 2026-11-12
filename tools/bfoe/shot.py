import asyncio, os, sys
from playwright.async_api import async_playwright
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
PW = os.environ["APP_PASSWORD"]; TAG = sys.argv[2] if len(sys.argv) > 2 else "local"
async def main():
    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp("http://localhost:29229")
        pg = await b.contexts[0].new_page()
        await pg.set_viewport_size({"width": 1600, "height": 1000})
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto(BASE + "/auth/login")
        if await pg.locator("input[name=password]").count():
            await pg.fill("input[name=password]", PW); await pg.keyboard.press("Enter"); await pg.wait_for_timeout(2500)
        await pg.goto(BASE + "/")
        await pg.wait_for_selector("text=Platts Assessment", timeout=40000)
        await pg.click("button.mp-nav-item:has-text('Platts Assessment')")
        await pg.wait_for_selector("text=Dated basket ex-QP", timeout=90000)
        await pg.wait_for_timeout(4000)
        sc = "document.querySelector('.mp-nav-item').closest('div').parentElement.children[1]"
        for i, y in enumerate([0, 900, 1800]):
            await pg.evaluate(f"{sc}.scrollTop={y}"); await pg.wait_for_timeout(600)
            await pg.screenshot(path=f"/home/ubuntu/bfoe/shots/{TAG}_exqp_{i}.png")
        txt = await pg.locator("text=Dated basket ex-QP").first.locator("xpath=..").inner_text()
        print("KPI:", txt.replace("\n", " | "))
        await pg.evaluate(f"{sc}.scrollTop=0")
        await pg.locator("button:visible", has_text="Raw (incl. QP)").click(); await pg.wait_for_timeout(2000)
        await pg.screenshot(path=f"/home/ubuntu/bfoe/shots/{TAG}_raw_0.png")
        await pg.locator("button:visible", has_text="Ex-QP (stripped)").click(); await pg.wait_for_timeout(1000)
        await pg.locator("button:visible", has_text="◀").click(); await pg.wait_for_timeout(8000)
        d = await pg.locator("input[type=date]").input_value()
        print("after prev:", d, (await pg.locator("text=Dated basket ex-QP").first.locator("xpath=..").inner_text()).replace("\n"," | "))
        await pg.screenshot(path=f"/home/ubuntu/bfoe/shots/{TAG}_prev.png")
        print("plots", await pg.evaluate("document.querySelectorAll('.js-plotly-plot').length"), "ERRS", errs)
asyncio.run(main())
