import asyncio, sys, re
from playwright.async_api import async_playwright
URL, OUT = sys.argv[1], sys.argv[2]
env=dict(x.split(b'=',1) for x in open('/home/ubuntu/xmove/.env.run','rb').read().split(b'\0') if b'=' in x)
PW=(env.get(b'APP_PASSWORD',b'').decode() if '127.0.0.1' in sys.argv[1] else '') or re.search(r'_APP_PASSWORD = os.environ.get\("APP_PASSWORD", "([^"]*)"\)',open('/home/ubuntu/crude-oil-analytics/app/main.py').read()).group(1)
TITLES=['Read — crude move','Moves — yesterday','Brent vs gasoil — change since start','This week: Brent vs gasoil','Intraday lead-lag','Pass-through','Crude types','Brent-Dubai vs DFL','Brent vs WTI vs Dubai','Intraday correlation']
async def main():
    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp("http://localhost:29229"); ctx = b.contexts[0]
        pg = await ctx.new_page(); await pg.set_viewport_size({"width": 1600, "height": 1000})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto(URL + "/auth/login"); await pg.fill("input[name=password]", PW); await pg.press("input[name=password]", "Enter")
        await pg.wait_for_timeout(4000)
        await pg.evaluate("""()=>{const x=[...document.querySelectorAll('button')].find(e=>e.textContent.trim().endsWith('Cross-Asset Moves'));x&&x.click();}""")
        await pg.wait_for_timeout(15000)
        for i,t in enumerate(TITLES):
            await pg.evaluate("""(t)=>{const x=[...document.querySelectorAll('div')].find(e=>e.children.length==0&&e.textContent.trim().toLowerCase().startsWith(t.toLowerCase()));x&&x.scrollIntoView();}""", t)
            await pg.wait_for_timeout(1200); await pg.screenshot(path=f"{OUT}_{i}.png")
        n = await pg.evaluate("()=>document.querySelectorAll('.js-plotly-plot').length")
        print("plots", n, "errors", errs)
        await pg.close()
asyncio.run(main())
