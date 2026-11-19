import asyncio, os, sys
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp("http://localhost:29229")
        ctx = b.contexts[0]
        pg = await ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: errs.append("console." + m.type + ": " + m.text) if m.type in ("error",) else None)
        await pg.set_viewport_size({"width": 1500, "height": 1000})
        await pg.goto("http://127.0.0.1:8000/auth/login")
        set_a = os.environ.get("APP_PASSWORD")
        await pg.fill("input[name=password]", set_a)
        await pg.click("button[type=submit], input[type=submit]")
        await pg.wait_for_timeout(2500)
        await pg.goto("http://127.0.0.1:8000/")
        await pg.wait_for_timeout(4000)
        # click Signal tab
        await pg.get_by_text("Signal", exact=False).first.click()
        await pg.wait_for_timeout(3000)
        await pg.get_by_text("Hormuz flows").click()
        for _ in range(40):
            await pg.wait_for_timeout(3000)
            if await pg.locator("text=How this is built").count(): break
        await pg.wait_for_timeout(4000)
        await pg.screenshot(path="/home/ubuntu/sig/hormuz_full.png", full_page=True)
        print("errors:", errs[:10])
        await pg.close()
asyncio.run(main())
