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
        loc = pg.locator("text=Sulfur de-escalator").first
        await loc.scroll_into_view_if_needed(); await pg.wait_for_timeout(800)
        await pg.screenshot(path="/home/ubuntu/bfoe/shots/live_forties_strip.png")
        print("strip:", (await loc.locator("xpath=..").inner_text()).replace("\n"," | "))
        print("buzz:", (await pg.locator("text=Buzzard % (weekly)").first.locator("xpath=..").inner_text()).replace("\n"," | "))
        print("ERRS", errs)
        await pg.close()
asyncio.run(main())
