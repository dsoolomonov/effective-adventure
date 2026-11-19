import os, asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        br=await p.chromium.connect_over_cdp('http://localhost:29229'); ctx=br.contexts[0]; pg=await ctx.new_page(); await pg.set_viewport_size({'width':1600,'height':1000})
        errs=[]; pg.on('pageerror',lambda e:errs.append(str(e)))
        B=os.environ.get('B','http://127.0.0.1:8000')
        await pg.goto(B+'/auth/login'); await pg.fill('input[name=password]',os.environ['APP_PASSWORD']); await pg.press('input[name=password]','Enter')
        await pg.wait_for_load_state('networkidle')
        await pg.locator('text=Session Pricing').first.click()
        await pg.wait_for_selector('text=Who moved it',timeout=90000); await pg.wait_for_timeout(3500)
        await pg.screenshot(path='/home/ubuntu/sessprice/shots/top.png')
        await pg.locator('text=Who moved it').first.scroll_into_view_if_needed(); await pg.wait_for_timeout(800); await pg.screenshot(path='/home/ubuntu/sessprice/shots/who.png')
        await pg.locator('button:has-text("This week")').first.click(); await pg.wait_for_timeout(800)
        await pg.select_option('select', 'G12'); await pg.wait_for_timeout(1500)
        await pg.locator('text=Price with session bands').first.scroll_into_view_if_needed(); await pg.wait_for_timeout(800); await pg.screenshot(path='/home/ubuntu/sessprice/shots/key.png')
        await pg.locator('text=Correlation of daily changes').first.scroll_into_view_if_needed(); await pg.wait_for_timeout(800); await pg.screenshot(path='/home/ubuntu/sessprice/shots/cross.png')
        n=await pg.evaluate("document.querySelectorAll('.js-plotly-plot').length")
        print('plots',n,'ERRS',errs)
        await pg.close()
asyncio.run(main())
