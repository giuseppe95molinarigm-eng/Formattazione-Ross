"""Batch review sheets.

Produces both a PNG contact sheet and a multi-page review PDF for a range of
illustrations. The identifying number is drawn OUTSIDE the artwork, in the
sheet's own caption strip — it is never composited into the coloring image.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .common import ROOT, img_name, load_config, p, read_json, rel


def _font(size: int) -> ImageFont.FreeTypeFont:
    for cand in ("fonts/Poppins-Bold.ttf", "fonts/Poppins-Regular.ttf"):
        fp = ROOT / cand
        if fp.exists():
            return ImageFont.truetype(str(fp), size)
    return ImageFont.load_default()


def _tile(path: Path, side: int, cap_h: int, label: str, sub: str,
          border: str = "#b0b0b0") -> Image.Image:
    """One cell: caption strip on top, artwork below, number never on the art."""
    cell = Image.new("RGB", (side, side + cap_h), "white")
    d = ImageDraw.Draw(cell)

    f_num = _font(int(cap_h * 0.52))
    f_sub = _font(int(cap_h * 0.30))
    d.text((6, 2), label, fill="black", font=f_num)
    if sub:
        d.text((6, int(cap_h * 0.58)), sub, fill="#787878", font=f_sub)

    if path.exists():
        art = Image.open(path).convert("L")
        art.thumbnail((side - 8, side - 8), Image.LANCZOS)
        off_x = (side - art.size[0]) // 2
        off_y = cap_h + (side - art.size[1]) // 2
        cell.paste(art.convert("RGB"), (off_x, off_y))
        d.rectangle([off_x - 1, off_y - 1, off_x + art.size[0], off_y + art.size[1]],
                    outline=border)
    else:
        d.rectangle([4, cap_h + 4, side - 4, side + cap_h - 4], outline="#cc0000")
        d.text((side // 2 - 60, cap_h + side // 2), "MISSING",
               fill="#cc0000", font=f_sub)
    return cell


def build_sheet(cfg: dict, ids: list[int]) -> list[Path]:
    rv = cfg["review"]
    cols, rows = int(rv["columns"]), int(rv["rows"])
    side = int(rv["thumb_px"])
    cap_h = int(rv["caption_height_px"])
    per_page = cols * rows

    final_dir = p(cfg, "final_dir")
    review_dir = p(cfg, "review_dir")
    review_dir.mkdir(parents=True, exist_ok=True)

    meta = read_json(p(cfg, "metadata"), default={"images": {}})["images"]
    prompts = read_json(p(cfg, "generated_prompts"), default={"prompts": {}})["prompts"]

    pad = 26
    sheet_w = cols * side + pad * (cols + 1)
    header = 150
    sheet_h = rows * (side + cap_h) + pad * (rows + 1) + header

    pages: list[Image.Image] = []
    for chunk_start in range(0, len(ids), per_page):
        chunk = ids[chunk_start:chunk_start + per_page]
        sheet = Image.new("RGB", (sheet_w, sheet_h), "white")
        d = ImageDraw.Draw(sheet)

        title = (f"{cfg['book']['title']} — review sheet  "
                 f"{chunk[0]:03d}–{chunk[-1]:03d}")
        d.text((pad, 30), title, fill="black", font=_font(50))
        d.text((pad, 96),
               "Numbers are printed outside the artwork for review only and are "
               "never part of the coloring illustrations.",
               fill="#666666", font=_font(27))

        for k, i in enumerate(chunk):
            r, c = divmod(k, cols)
            rec = meta.get(str(i), {})
            status = rec.get("validation_status", "—")
            warn = rec.get("validation_warnings") or []
            sub = status + (f"  ({len(warn)} warn)" if warn else "")
            concept = (prompts.get(str(i), {}).get("concept") or "")[:46]
            border = {"PASS": "#8fbf8f", "FAIL": "#cc0000"}.get(status, "#b0b0b0")
            cell = _tile(final_dir / img_name(i), side, cap_h,
                         f"{i:03d}   {sub}", concept, border)
            sheet.paste(cell,
                        (pad + c * (side + pad),
                         header + pad + r * (side + cap_h + pad)))
        pages.append(sheet)

    out: list[Path] = []
    tag = f"{ids[0]:03d}-{ids[-1]:03d}"
    for n, img in enumerate(pages, 1):
        png = review_dir / (f"contact_sheet_{tag}.png" if len(pages) == 1
                            else f"contact_sheet_{tag}_p{n}.png")
        img.save(png, optimize=True)
        out.append(png)

    pdf = review_dir / f"review_{tag}.pdf"
    pages[0].save(pdf, "PDF", resolution=150.0, save_all=True,
                  append_images=pages[1:])
    out.append(pdf)
    return out


def main(cfg: dict | None = None, start: int | None = None,
         end: int | None = None, ids: list[int] | None = None,
         quiet: bool = False) -> list[Path]:
    cfg = cfg or load_config()
    from .common import parse_range
    if ids is None:
        ids = parse_range(start, end, cfg["book"]["total_entries"])

    files = build_sheet(cfg, ids)
    if not quiet:
        print(f"review material for {ids[0]:03d}–{ids[-1]:03d}:")
        for f in files:
            print(f"  {rel(f)}  ({f.stat().st_size // 1024} KB)")
        missing = [i for i in ids
                   if not (p(cfg, 'final_dir') / img_name(i)).exists()]
        if missing:
            print(f"  note: {len(missing)} image(s) not generated yet: "
                  + ", ".join(f"{m:03d}" for m in missing))
    return files


if __name__ == "__main__":
    main()
