import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.connect_over_cdp("http://localhost:29229"); ctx=b.contexts[0]
        pg=await ctx.new_page(); await pg.set_viewport_size({"width":1600,"height":1000})
        await pg.goto("https://crude-oil-analytics.fly.dev/"); await pg.wait_for_timeout(4000)
        await pg.evaluate("""()=>{const x=[...document.querySelectorAll('*')].find(e=>e.children.length<3&&e.textContent.trim()==='Product Stocks');x&&x.click();}""")
        await pg.wait_for_timeout(14000)
        await pg.evaluate("""()=>{const t=[...document.querySelectorAll('div')].find(e=>e.textContent.startsWith('Latest stocks articles'));t&&t.scrollIntoView();window.scrollBy(0,-60)}""")
        await pg.wait_for_timeout(1500); await pg.screenshot(path="live_news.png")
        await pg.close()
asyncio.run(main())
