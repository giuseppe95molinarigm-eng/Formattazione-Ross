"""Render the built PDF to page PNGs and contact sheets for visual QC."""
import sys, pymupdf
from pathlib import Path
from PIL import Image
pdf = sys.argv[1] if len(sys.argv) > 1 else "output/Declutter_Beyond_Interior_6x9.pdf"
out = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/qc"); out.mkdir(parents=True, exist_ok=True)
d = pymupdf.open(pdf)
ims = []
for i, p in enumerate(d):
    pm = p.get_pixmap(dpi=60)
    im = Image.frombytes("RGB", (pm.width, pm.height), pm.samples); ims.append(im)
w, h = ims[0].size
per = 12
for s in range(0, len(ims), per):
    c = Image.new("RGB", (6 * (w + 8), 2 * (h + 8)), (120, 120, 120))
    for k, im in enumerate(ims[s:s + per]):
        c.paste(im, ((k % 6) * (w + 8), (k // 6) * (h + 8)))
    c.save(out / f"sheet{s // per + 1:02d}.png")
print(len(ims), "pages ->", out)
