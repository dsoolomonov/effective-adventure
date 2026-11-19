import asyncio, os
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp("http://localhost:29229")
        ctx = b.contexts[0]
        pg = await ctx.new_page()
        await pg.set_viewport_size({"width": 1500, "height": 1000})
        await pg.goto("http://127.0.0.1:8000/")
        await pg.wait_for_timeout(4000)
        await pg.get_by_text("Signal", exact=False).first.click()
        await pg.wait_for_timeout(3000)
        await pg.get_by_text("Hormuz flows").click()
        for _ in range(40):
            await pg.wait_for_timeout(2000)
            if await pg.locator("text=How this is built").count(): break
        await pg.wait_for_timeout(3000)
        h = await pg.locator("text=How this is built").first.evaluate("e => { let n=e; while(n && n.scrollHeight<=n.clientHeight) n=n.parentElement; return n ? n.scrollHeight : 0; }")
        print("scrollH", h)
        for i, y in enumerate(range(800, int(h), 900)):
            await pg.locator("text=How this is built").first.evaluate(f"e => {{ let n=e; while(n && n.scrollHeight<=n.clientHeight) n=n.parentElement; n.scrollTop={y}; }}")
            await pg.wait_for_timeout(700)
            await pg.screenshot(path=f"/home/ubuntu/sig/hz_{i}.png")
        await pg.close()
asyncio.run(main())
