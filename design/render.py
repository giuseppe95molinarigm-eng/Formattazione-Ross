import asyncio, os
from playwright.async_api import async_playwright

PAGES = [
    "1-chapter-opener.html",
    "2-recipe-normal-1.html",
    "3-recipe-normal-2.html",
    "4-recipe-image-heavy.html",
    "5-recipe-text-heavy.html",
]
BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "preview")
OUT_CLEAN = os.path.join(BASE, "preview-clean")
os.makedirs(OUT, exist_ok=True)
os.makedirs(OUT_CLEAN, exist_ok=True)

CLEAN_CSS = ".trim-line, .safe-line, .label-tag { display: none !important; }"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
        page = await browser.new_page(viewport={"width": 1050, "height": 1350}, device_scale_factor=2)
        for fn in PAGES:
            url = "file://" + os.path.join(BASE, "sample", fn)
            await page.goto(url)
            await page.wait_for_timeout(150)
            el = await page.query_selector(".page")
            png_path = os.path.join(OUT, fn.replace(".html", ".png"))
            await el.screenshot(path=png_path)
            print("wrote", png_path)

            await page.add_style_tag(content=CLEAN_CSS)
            await page.wait_for_timeout(50)
            el = await page.query_selector(".page")
            png_path = os.path.join(OUT_CLEAN, fn.replace(".html", ".png"))
            await el.screenshot(path=png_path)
            print("wrote", png_path)
        await browser.close()

asyncio.run(main())
