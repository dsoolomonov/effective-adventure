import os, asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        br=await p.chromium.connect_over_cdp('http://localhost:29229'); ctx=br.contexts[0]; pg=await ctx.new_page(); await pg.set_viewport_size({'width':1600,'height':1000})
        errs=[]; pg.on('pageerror',lambda e:errs.append(str(e)))
        B=os.environ.get('B','http://127.0.0.1:8000')
        await pg.goto(B+'/auth/login'); await pg.fill('input[name=password]',os.environ['APP_PASSWORD']); await pg.press('input[name=password]','Enter')
        await pg.wait_for_load_state('networkidle')
        await pg.locator('text=Refinery Outages').first.click()
        await pg.wait_for_selector('text=Desk read',timeout=90000); await pg.wait_for_timeout(2500)
        await pg.screenshot(path='/home/ubuntu/outages/shots/top.png')
        await pg.locator('text=Listed key outages').first.scroll_into_view_if_needed(); await pg.wait_for_timeout(800); await pg.screenshot(path='/home/ubuntu/outages/shots/mid.png')
        await pg.locator('button:has-text("FCC & Reforming")').first.click(); await pg.locator('button:has-text("Russia & FSU")').first.click()
        await pg.locator('button:has-text("Unplanned")').first.click(); await pg.wait_for_timeout(2500)
        await pg.locator('text=Pack charts by unit and region').scroll_into_view_if_needed()
        await pg.screenshot(path='/home/ubuntu/outages/shots/charts.png')
        n=await pg.evaluate("[...document.querySelectorAll('img[src*=\"/api/outages/chart/\"]')].map(i=>i.complete&&i.naturalWidth>0)")
        rows=await pg.locator('text=Key refinery outages (appendix)').locator('xpath=..').locator('tr').count()
        await pg.locator('text=Key refinery outages (appendix)').scroll_into_view_if_needed(); await pg.screenshot(path='/home/ubuntu/outages/shots/table.png')
        print('imgs',n,'tablerows',rows,'ERRS',errs)
        await pg.close()
asyncio.run(main())
