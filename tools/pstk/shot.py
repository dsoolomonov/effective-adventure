import asyncio,os
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.connect_over_cdp("http://localhost:29229"); ctx=b.contexts[0]
        pg=await ctx.new_page(); await pg.set_viewport_size({"width":1600,"height":1000})
        errs=[]; pg.on("pageerror",lambda e: errs.append(str(e)))
        await pg.goto("https://crude-oil-analytics.fly.dev/auth/login")
        await pg.fill("input[name=password]",os.environ["APP_PASSWORD"]); await pg.keyboard.press("Enter")
        await pg.wait_for_timeout(4000)
        await pg.evaluate("""()=>{const x=[...document.querySelectorAll('*')].find(e=>e.children.length<3&&e.textContent.trim()==='Product Stocks');x&&x.click();}""")
        await pg.wait_for_timeout(12000)
        await pg.screenshot(path="live1.png",full_page=False)
        n=await pg.evaluate("()=>document.body.innerText.includes('Regional oil stocks')")
        print('summary present',n,'errors',errs[:5])
        await pg.evaluate("""()=>{const t=[...document.querySelectorAll('div')].find(e=>e.textContent.startsWith('Regional oil stocks'));t&&t.scrollIntoView();}""")
        await pg.wait_for_timeout(1500); await pg.screenshot(path="live2.png")
        await pg.evaluate("window.scrollBy(0,900)"); await pg.wait_for_timeout(2500); await pg.screenshot(path="live3.png")
        await pg.close()
asyncio.run(main())
