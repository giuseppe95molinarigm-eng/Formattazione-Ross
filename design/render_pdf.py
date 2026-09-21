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
CLEAN_CSS = ".trim-line, .safe-line, .label-tag { display: none !important; } body{background:#FBF6EC;} .page{margin:0;}"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
        page = await browser.new_page()
        pdf_paths = []
        for fn in PAGES:
            url = "file://" + os.path.join(BASE, "sample", fn)
            await page.goto(url)
            await page.add_style_tag(content=CLEAN_CSS)
            await page.wait_for_timeout(80)
            out = os.path.join(BASE, "preview-clean", fn.replace(".html", ".pdf"))
            await page.pdf(path=out, width="8.75in", height="11.25in", print_background=True, margin={"top":"0","bottom":"0","left":"0","right":"0"})
            pdf_paths.append(out)
        await browser.close()
        print("wrote", pdf_paths)

asyncio.run(main())
