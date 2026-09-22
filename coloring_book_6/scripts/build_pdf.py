"""Build the print-ready KDP interior PDF.

THE HARD RULE, enforced structurally rather than hoped for:

    every illustration sits on a LEFT / verso page
    its corresponding Spanish text sits on the FACING RIGHT / recto page

With 1-based PDF page numbers and page 1 being a recto (the first right-hand
page of the book block), verso pages are the EVEN numbers. So each pair is
laid out as (even = image, odd = text), and a blank filler page is inserted
whenever the running count would break that parity — including after every
section divider. The page plan is built and asserted BEFORE anything is drawn.

Margins follow Amazon KDP's inside/gutter table, selected by the ACTUAL final
page count rather than assumed.
"""
from __future__ import annotations

from pathlib import Path

import reportlab.rl_config
from reportlab.lib.colors import black, Color
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas

from .common import ROOT, img_name, load_config, p, read_json, rel, write_json

PT = 72.0  # points per inch


# ── margins ───────────────────────────────────────────────────────────────
def gutter_for(page_count: int, cfg: dict) -> float:
    """KDP minimum inside margin for this page count, plus our safety pad."""
    table = cfg["print"]["gutter_table"]
    base = table[-1]["gutter_in"]
    for row in table:
        if page_count <= row["max_pages"]:
            base = row["gutter_in"]
            break
    return float(base) + float(cfg["print"].get("gutter_safety_pad_in", 0.0))


def margins_for(page_index: int, page_count: int, cfg: dict) -> dict:
    """Margins in points for a given 1-based page number.

    Odd pages are rectos (right-hand): the gutter is on the LEFT.
    Even pages are versos (left-hand):  the gutter is on the RIGHT.
    """
    pr = cfg["print"]
    gut = gutter_for(page_count, cfg)
    out = float(pr["outside_margin_in"])
    is_recto = page_index % 2 == 1
    return {
        "left": (gut if is_recto else out) * PT,
        "right": (out if is_recto else gut) * PT,
        "top": float(pr["top_margin_in"]) * PT,
        "bottom": float(pr["bottom_margin_in"]) * PT,
        "gutter_in": gut,
        "is_recto": is_recto,
    }


# ── page plan ─────────────────────────────────────────────────────────────
def build_plan(cfg: dict, entries: list[dict], sections: list[dict]) -> list[dict]:
    """Produce the ordered list of pages, inserting blanks to hold parity."""
    plan: list[dict] = []

    def add(kind: str, **kw) -> None:
        plan.append({"kind": kind, **kw})

    def pad_until(parity: str) -> None:
        """Append blanks until the NEXT page to be added has the given parity."""
        while True:
            nxt = len(plan) + 1
            if (parity == "recto" and nxt % 2 == 1) or (
                parity == "verso" and nxt % 2 == 0
            ):
                return
            add("blank", reason=f"parity filler before {parity}")

    # ── front matter (rectos where it matters) ──
    add("title")                                  # page 1, recto
    add("copyright")                              # page 2, verso
    add("contents")                               # page 3, recto
    add("how_to")                                 # page 4, verso

    by_section = {s["section"]: s for s in sections}
    entries_by_id = {e["id"]: e for e in entries}

    for sec in sections:
        pad_until("recto")
        add("part", section=sec["section"], label=sec["label"],
            title=sec["title"])

        for eid in range(sec["first_id"], sec["last_id"] + 1):
            # the illustration must land on a verso (even) page
            pad_until("verso")
            add("image", id=eid, section=sec["section"])
            add("text", id=eid, section=sec["section"],
                text=entries_by_id[eid]["text"])

    # ── back matter ──
    pad_until("recto")
    add("end")

    # KDP prefers an even total page count for the book block
    if len(plan) % 2 == 1:
        add("blank", reason="even total page count")

    return plan


def verify_plan(plan: list[dict], entries: list[dict]) -> list[str]:
    """Assert the facing-page contract. Returns a list of problems."""
    problems: list[str] = []
    images = {}
    texts = {}

    for idx, pg in enumerate(plan, start=1):
        if pg["kind"] == "image":
            images[pg["id"]] = idx
            if idx % 2 != 0:
                problems.append(
                    f"illustration {pg['id']:03d} is on page {idx}, which is a "
                    f"RECTO (right-hand) page — it must be on a verso"
                )
        elif pg["kind"] == "text":
            texts[pg["id"]] = idx
            if idx % 2 != 1:
                problems.append(
                    f"text {pg['id']:03d} is on page {idx}, which is a VERSO "
                    f"(left-hand) page — it must be on a recto"
                )

    expected = {e["id"] for e in entries}
    if set(images) != expected:
        problems.append(f"image pages cover {len(images)} ids, expected {len(expected)}")
    if set(texts) != expected:
        problems.append(f"text pages cover {len(texts)} ids, expected {len(expected)}")

    for eid in sorted(expected & set(images) & set(texts)):
        if texts[eid] != images[eid] + 1:
            problems.append(
                f"entry {eid:03d}: image on page {images[eid]} but text on page "
                f"{texts[eid]} — the text must immediately follow on the facing page"
            )
    return problems


# ── typography helpers ────────────────────────────────────────────────────
def register_fonts(cfg: dict) -> dict[str, str]:
    names: dict[str, str] = {}
    for role, spec in cfg["layout"]["fonts"].items():
        path = ROOT / spec["file"]
        if not path.exists():
            raise SystemExit(f"font missing: {spec['file']}")
        pdfmetrics.registerFont(TTFont(spec["name"], str(path)))
        names[role] = spec["name"]
    return names


def wrap(text: str, font: str, size: float, max_w: float,
         max_chars: int | None = None) -> list[str]:
    """Greedy word wrap honouring both a pixel width and an optional measure."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        too_wide = pdfmetrics.stringWidth(trial, font, size) > max_w
        too_long = max_chars is not None and len(trial) > max_chars
        if cur and (too_wide or too_long):
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def fit_text(text: str, font: str, cfg: dict, box_w: float, box_h: float
             ) -> tuple[list[str], float, float]:
    """Shrink the body size until the wrapped text fits the box. Never crops."""
    tp = cfg["layout"]["text_page"]
    size = float(tp["body_size_pt"])
    floor = float(tp["body_size_min_pt"])
    ratio = float(tp["body_leading_ratio"])
    measure = tp.get("max_line_chars")

    while size >= floor:
        lines = wrap(text, font, size, box_w, measure)
        leading = size * ratio
        if len(lines) * leading <= box_h:
            return lines, size, leading
        size -= 0.5
    lines = wrap(text, font, floor, box_w, measure)
    return lines, floor, floor * ratio


# ── page painters ─────────────────────────────────────────────────────────
def draw_image_page(c, pg: dict, m: dict, cfg: dict, W: float, H: float) -> dict:
    """Place the illustration inside the safe box, aspect preserved."""
    path = p(cfg, "final_dir") / img_name(pg["id"])
    if not path.exists():
        raise SystemExit(f"missing production image for {pg['id']:03d}: {path}")

    box_w = W - m["left"] - m["right"]
    box_h = H - m["top"] - m["bottom"]

    img = ImageReader(str(path))
    iw, ih = img.getSize()
    scale = min(box_w / iw, box_h / ih)
    dw, dh = iw * scale, ih * scale
    x = m["left"] + (box_w - dw) / 2
    y = m["bottom"] + (box_h - dh) / 2

    c.drawImage(img, x, y, width=dw, height=dh,
                preserveAspectRatio=True, anchor="c", mask=None)

    return {
        "id": pg["id"],
        "px": [iw, ih],
        "printed_in": [round(dw / PT, 4), round(dh / PT, 4)],
        "effective_ppi": [round(iw / (dw / PT), 1), round(ih / (dh / PT), 1)],
    }


def draw_text_page(c, pg: dict, m: dict, cfg: dict, fonts: dict,
                   W: float, H: float) -> None:
    tp = cfg["layout"]["text_page"]
    box_w = W - m["left"] - m["right"]
    box_h = H - m["top"] - m["bottom"]

    num_size = float(tp["number_size_pt"])
    gap = float(tp["number_gap_pt"])
    body_font = fonts["body"]

    avail_h = box_h - num_size - gap
    lines, size, leading = fit_text(pg["text"], body_font, cfg, box_w, avail_h)

    block_h = num_size + gap + len(lines) * leading
    top_y = m["bottom"] + (box_h + block_h) / 2
    cx = m["left"] + box_w / 2

    # item number, set apart from the body copy
    c.setFont(fonts["number"], num_size)
    c.setFillColor(black)
    c.drawCentredString(cx, top_y - num_size, str(pg["id"]))

    # a short rule under the number for hierarchy
    rule_w = 90.0
    ry = top_y - num_size - gap * 0.45
    c.setStrokeColor(Color(0, 0, 0))
    c.setLineWidth(2.2)
    c.line(cx - rule_w / 2, ry, cx + rule_w / 2, ry)

    c.setFont(body_font, size)
    y = top_y - num_size - gap - leading * 0.82
    for ln in lines:
        c.drawCentredString(cx, y, ln)
        y -= leading


def draw_part_page(c, pg: dict, m: dict, cfg: dict, fonts: dict,
                   W: float, H: float) -> None:
    pp = cfg["layout"]["part_page"]
    box_w = W - m["left"] - m["right"]
    cx = m["left"] + box_w / 2
    cy = H / 2

    c.setFillColor(black)
    c.setFont(fonts["part"], float(pp["label_size_pt"]))
    c.drawCentredString(cx, cy + 96, pg["label"])

    rw = float(pp["rule_width_pt"])
    c.setLineWidth(2.5)
    c.line(cx - rw / 2, cy + 68, cx + rw / 2, cy + 68)

    size = float(pp["title_size_pt"])
    lines = wrap(pg["title"], fonts["title"], size, box_w * 0.86)
    while len(lines) > 3 and size > 22:
        size -= 2
        lines = wrap(pg["title"], fonts["title"], size, box_w * 0.86)
    c.setFont(fonts["title"], size)
    y = cy + 8
    for ln in lines:
        c.drawCentredString(cx, y, ln)
        y -= size * 1.22

    # a small star motif, echoing the collection's signature
    c.setLineWidth(2.0)
    for dx in (-34, 0, 34):
        _star(c, cx + dx, y - 34, 11)


def _star(c, cx: float, cy: float, r: float) -> None:
    import math
    pts = []
    for i in range(10):
        ang = math.pi / 2 + i * math.pi / 5
        rad = r if i % 2 == 0 else r * 0.42
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    path = c.beginPath()
    path.moveTo(*pts[0])
    for pt in pts[1:]:
        path.lineTo(*pt)
    path.close()
    c.drawPath(path, stroke=1, fill=0)


def draw_front(c, kind: str, m: dict, cfg: dict, fonts: dict,
               W: float, H: float, sections: list[dict]) -> None:
    fm = cfg["layout"]["front_matter"]
    bk = cfg["book"]
    box_w = W - m["left"] - m["right"]
    cx = m["left"] + box_w / 2
    c.setFillColor(black)

    if kind == "title":
        size = float(fm["title_size_pt"])
        lines = wrap(bk["title"], fonts["title"], size, box_w * 0.92)
        y = H * 0.66
        c.setFont(fonts["title"], size)
        for ln in lines:
            c.drawCentredString(cx, y, ln)
            y -= size * 1.16
        y -= 26
        c.setFont(fonts["sub"], float(fm["subtitle_size_pt"]))
        for ln in wrap(bk["subtitle"], fonts["sub"],
                       float(fm["subtitle_size_pt"]), box_w * 0.82):
            c.drawCentredString(cx, y, ln)
            y -= float(fm["subtitle_size_pt"]) * 1.42
        c.setLineWidth(2.0)
        for dx in (-40, 0, 40):
            _star(c, cx + dx, y - 40, 13)
        c.setFont(fonts["part"], float(fm["imprint_size_pt"]))
        c.drawCentredString(cx, m["bottom"] + 54, bk["imprint"])

    elif kind == "copyright":
        c.setFont(fonts["sub"], float(fm["copyright_size_pt"]))
        y = H * 0.5
        for ln in [bk["copyright"], bk["rights"], "", bk["imprint"]]:
            if ln:
                c.drawCentredString(cx, y, ln)
            y -= 18

    elif kind == "contents":
        c.setFont(fonts["title"], 40)
        c.drawCentredString(cx, H - m["top"] - 70, "Contenido")
        c.setLineWidth(2.2)
        c.line(cx - 80, H - m["top"] - 92, cx + 80, H - m["top"] - 92)
        y = H - m["top"] - 190
        for s in sections:
            c.setFont(fonts["part"], 21)
            c.drawCentredString(cx, y, s["label"])
            y -= 30
            c.setFont(fonts["sub"], 15)
            for ln in wrap(s["title"], fonts["sub"], 15, box_w * 0.8):
                c.drawCentredString(cx, y, ln)
                y -= 21
            y -= 34

    elif kind == "how_to":
        c.setFont(fonts["title"], 34)
        c.drawCentredString(cx, H - m["top"] - 80, "¡Vamos a empezar!")
        body = [
            "En cada página de la izquierda hay un dibujo para colorear.",
            "En la página de la derecha encontrarás un dato curioso",
            "sobre todo lo que ya sabes hacer con 6 años.",
            "",
            "Colorea, lee y descubre cómo estás creciendo.",
        ]
        c.setFont(fonts["sub"], 17)
        y = H * 0.58
        for ln in body:
            if ln:
                c.drawCentredString(cx, y, ln)
            y -= 27
        c.setLineWidth(2.0)
        for dx in (-40, 0, 40):
            _star(c, cx + dx, y - 26, 12)

    elif kind == "end":
        c.setFont(fonts["title"], 40)
        c.drawCentredString(cx, H * 0.56, "¡Feliz cumpleaños!")
        c.setFont(fonts["sub"], 18)
        c.drawCentredString(cx, H * 0.56 - 44, "Disfruta muchísimo de tus 6 años.")
        c.setLineWidth(2.0)
        for dx in (-46, 0, 46):
            _star(c, cx + dx, H * 0.56 - 96, 14)


# ── driver ────────────────────────────────────────────────────────────────
def main(cfg: dict | None = None, quiet: bool = False) -> dict:
    cfg = cfg or load_config()
    entries = read_json(p(cfg, "entries"))["entries"]
    sections = read_json(p(cfg, "sections"))["sections"]

    plan = build_plan(cfg, entries, sections)
    problems = verify_plan(plan, entries)
    if problems:
        print("PAGE PLAN FAILED — refusing to build:")
        for pr in problems:
            print(f"  FAIL  {pr}")
        raise SystemExit(1)

    page_count = len(plan)
    W = float(cfg["print"]["trim_width_in"]) * PT
    H = float(cfg["print"]["trim_height_in"]) * PT

    missing = [pg["id"] for pg in plan
               if pg["kind"] == "image"
               and not (p(cfg, "final_dir") / img_name(pg["id"])).exists()]
    if missing:
        raise SystemExit(
            "cannot build the interior: "
            f"{len(missing)} illustration(s) not generated yet: "
            + ", ".join(f"{m:03d}" for m in missing)
        )

    out_path = ROOT / cfg["output"]["interior_pdf"]
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fonts = register_fonts(cfg)

    # ReportLab seeds every page's resource dictionary with its default base-14
    # font (Helvetica), which is NOT embedded and which KDP preflight rejects.
    # Pointing the default at an embedded face removes it entirely.
    base = fonts.get("base", fonts["body"])
    reportlab.rl_config.canvas_basefontname = base

    c = rl_canvas.Canvas(str(out_path), pagesize=(W, H),
                         initialFontName=base,
                         pageCompression=1 if cfg["output"]["compress_streams"] else 0)
    c.setTitle(cfg["output"]["pdf_title"])
    c.setAuthor(cfg["output"]["pdf_author"])
    c.setSubject(cfg["book"]["subtitle"])
    c.setCreator("coloring_book_6 pipeline")

    placements: list[dict] = []
    for idx, pg in enumerate(plan, start=1):
        m = margins_for(idx, page_count, cfg)
        kind = pg["kind"]
        if kind == "image":
            placements.append({**draw_image_page(c, pg, m, cfg, W, H), "page": idx})
        elif kind == "text":
            draw_text_page(c, pg, m, cfg, fonts, W, H)
        elif kind == "part":
            draw_part_page(c, pg, m, cfg, fonts, W, H)
        elif kind in {"title", "copyright", "contents", "how_to", "end"}:
            draw_front(c, kind, m, cfg, fonts, W, H, sections)
        # 'blank' draws nothing at all
        c.showPage()
    c.save()

    page_map = {
        "page_count": page_count,
        "gutter_in": gutter_for(page_count, cfg),
        "trim_in": [cfg["print"]["trim_width_in"], cfg["print"]["trim_height_in"]],
        "pages": [
            {"page": i, "kind": pg["kind"], "id": pg.get("id"),
             "section": pg.get("section"), "reason": pg.get("reason"),
             "side": "recto" if i % 2 == 1 else "verso"}
            for i, pg in enumerate(plan, start=1)
        ],
        "image_placements": placements,
    }
    write_json(p(cfg, "page_map"), page_map)

    if not quiet:
        blanks = sum(1 for pg in plan if pg["kind"] == "blank")
        min_ppi = min(min(pl["effective_ppi"]) for pl in placements)
        print(f"built {rel(out_path)}")
        print(f"  pages             : {page_count} (even: "
              f"{'yes' if page_count % 2 == 0 else 'NO'})")
        print(f"  illustrations      : {sum(1 for x in plan if x['kind']=='image')} "
              f"(all on verso/left)")
        print(f"  text pages         : {sum(1 for x in plan if x['kind']=='text')} "
              f"(all on recto/right)")
        print(f"  section dividers   : {sum(1 for x in plan if x['kind']=='part')}")
        print(f"  parity/other blanks: {blanks}")
        print(f"  gutter (KDP table) : {page_map['gutter_in']}in for "
              f"{page_count} pages")
        print(f"  min effective PPI  : {min_ppi:.0f}")
        print(f"  file size          : {out_path.stat().st_size / 1e6:.1f} MB")
        print("  facing-page contract: VERIFIED (image verso / text recto, all 101)")
    return page_map


if __name__ == "__main__":
    main()
