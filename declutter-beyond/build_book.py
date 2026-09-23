#!/usr/bin/env python3
"""Build the 6x9 KDP print interior of "Declutter Beyond" (Alex Lee).

Pipeline: manuscript .docx  ->  structured HTML (book.html)  ->  WeasyPrint PDF.

The design system (book.css) reproduces the series look of
"Declutter Your Home, Calm Your Life" (V9, 6x9).  The author's text is
carried over run-by-run (bold/italic preserved); nothing is rewritten.
"""
import html
import re
import sys
from pathlib import Path

import docx

HERE = Path(__file__).resolve().parent
SRC = HERE / "source" / "Declutter_Beyond_Manuscript_v13_24_1.1.docx"
OUT_HTML = HERE / "output" / "book.html"
OUT_PDF = HERE / "output" / "Declutter_Beyond_Interior_6x9.pdf"

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
EMU_PER_PT = 12700

BOOK_TITLE = "Declutter Beyond"

ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4}


# --------------------------------------------------------------------------
# docx reading helpers
# --------------------------------------------------------------------------
def run_props(r):
    rpr = r.find(W + "rPr")
    b = i = False
    if rpr is not None:
        for tag, name in ((W + "b", "b"), (W + "i", "i")):
            el = rpr.find(tag)
            if el is not None and el.get(W + "val") not in ("0", "false"):
                if name == "b":
                    b = True
                else:
                    i = True
    return b, i


def iter_runs(p):
    """Yield w:r elements in reading order, including those in hyperlinks."""
    for child in p:
        if child.tag == W + "r":
            yield child
        elif child.tag in (W + "hyperlink", W + "smartTag", W + "ins"):
            for r in child.iter(W + "r"):
                yield r


def para_segments(p):
    """Return list of (text, bold, italic) segments, merged when equal."""
    segs = []
    for r in iter_runs(p):
        b, i = run_props(r)
        buf = ""
        for el in r:
            if el.tag == W + "t":
                buf += el.text or ""
            elif el.tag == W + "tab":
                buf += " "
            elif el.tag == W + "br" and el.get(W + "type") not in ("page", "column"):
                buf += "\n"
        if not buf:
            continue
        if segs and segs[-1][1] == b and segs[-1][2] == i:
            segs[-1] = (segs[-1][0] + buf, b, i)
        else:
            segs.append((buf, b, i))
    return segs


def seg_html(segs, url_breaks=False):
    out = []
    for text, b, i in segs:
        t = html.escape(text).replace("\n", "<br>")
        if url_breaks:
            # allow line breaks inside long URLs without altering visible text
            t = re.sub(r"(https?://\S+)",
                       lambda m: '<span class="url">' + re.sub(r"([/?=&])", r"\1&#8203;", m.group(1)) + "</span>",
                       t)
        if b:
            t = f"<strong>{t}</strong>"
        if i:
            t = f"<em>{t}</em>"
        out.append(t)
    return "".join(out)


def para_info(p, rels):
    ppr = p.find(W + "pPr")
    style = align = None
    ind_left = 0
    num = None
    if ppr is not None:
        ps = ppr.find(W + "pStyle")
        style = ps.get(W + "val") if ps is not None else None
        jc = ppr.find(W + "jc")
        align = jc.get(W + "val") if jc is not None else None
        ind = ppr.find(W + "ind")
        if ind is not None:
            ind_left = int(ind.get(W + "left") or ind.get(W + "start") or 0)
        numpr = ppr.find(W + "numPr")
        if numpr is not None:
            nid = numpr.find(W + "numId")
            num = nid.get(W + "val") if nid is not None else None
    segs = para_segments(p)
    text = "".join(s[0] for s in segs)
    blips = p.findall(".//" + A + "blip")
    img = None
    if blips:
        rid = blips[0].get(R + "embed")
        ext = p.find(".//" + WP + "extent")
        img = (Path(rels[rid].target_ref).name,
               int(ext.get("cx")) / EMU_PER_PT, int(ext.get("cy")) / EMU_PER_PT)
    total = sum(len(s[0]) for s in segs if s[0].strip())
    bold = sum(len(s[0]) for s in segs if s[1] and s[0].strip())
    ital = sum(len(s[0]) for s in segs if s[2] and s[0].strip())
    return dict(style=style or "Normal", align=align, ind=ind_left, num=num, segs=segs,
                text=text, img=img,
                all_bold=total > 0 and bold == total,
                all_ital=total > 0 and ital == total)


# --------------------------------------------------------------------------
# text measuring (used to balance centred lines and TOC/phase breaks)
# --------------------------------------------------------------------------
from PIL import ImageFont
_FONTS = {}


def text_width(text, font_file, size_pt):
    f = _FONTS.get(font_file)
    if f is None:
        f = _FONTS[font_file] = ImageFont.truetype(str(HERE / "fonts" / font_file), 100)
    return f.getlength(text) * size_pt / 100.0


def balanced_width(text, font_file, size_pt, avail):
    """Width that spreads a centred paragraph evenly over its lines, so no
    line ends up with a single stranded word."""
    w = text_width(text, font_file, size_pt)
    if w <= avail:
        return None
    slack = 14.0
    n = int(w // (avail - slack)) + 1
    return min(avail, w / n + slack)


def split_balanced(words, font_file, size_pt):
    """Split a word list into two lines of similar width."""
    best = None
    for k in range(1, len(words)):
        a, b = " ".join(words[:k]), " ".join(words[k:])
        m = max(text_width(a, font_file, size_pt), text_width(b, font_file, size_pt))
        if best is None or m < best[0]:
            best = (m, a, b)
    return best[1], best[2]


# --------------------------------------------------------------------------
# HTML building
# --------------------------------------------------------------------------
def esc(s):
    return html.escape(s)


def split_title(title):
    """Break a display title after an em dash, as the reference does."""
    if " — " in title:
        a, b = title.split(" — ", 1)
        return f"{esc(a)} —<br>{esc(b)}"
    return esc(title)


class Book:
    def __init__(self, fig_heights=None, fig_defer=None):
        self.fig_heights = fig_heights or {}
        self.fig_defer = fig_defer or {}
        self.fig_n = 0
        self.pending_fig = None
        self.parts = []          # html chunks
        self.toc = []            # (level, kind, label, title, anchor)
        self.n = 0
        self.prev = None         # previous block kind (for indent logic)
        self.after_opener = False
        self.open_section = False
        self.list_open = None
        self.list_counter = {}
        self.dropcap_pending = False
        self.opener_kind = None

    def anchor(self):
        self.n += 1
        return f"s{self.n}"

    def flush_fig(self):
        if self.pending_fig:
            self.parts.append(self.pending_fig[0])
            self.pending_fig = None

    def close_list(self):
        if self.list_open:
            self.parts.append("</ol>")
            self.list_open = None

    def close_section(self):
        self.close_list()
        self.flush_fig()
        if self.open_section:
            self.parts.append("</section>")
            self.open_section = False

    def add(self, s, kind):
        if kind not in ("li", "numli"):
            self.close_list()
        if self.pending_fig and kind != "p":
            self.flush_fig()
        self.parts.append(s)
        self.prev = kind
        if self.pending_fig and kind == "p":
            self.pending_fig[1] -= 1
            if self.pending_fig[1] <= 0:
                self.flush_fig()

    # ----- structural openers -----
    def phase(self, text):
        self.close_section()
        m = re.match(r"Phase\s+([IVX]+):\s*(.*)", text)
        num, name = m.group(1), m.group(2)
        a = self.anchor()
        if " — " in name:
            main, sub = name.split(" — ", 1)
            sub_html = f'<p class="phase-sub">{esc(sub.upper())}</p>'
        else:
            main, sub_html = name, ""
        main_u = main.upper()
        if text_width(main_u, "nunito-sans-300-normal.ttf", 28) > 300:
            a1, b1 = split_balanced(main_u.split(), "nunito-sans-300-normal.ttf", 28)
            main_html = f"{esc(a1)}<br>{esc(b1)}"
        else:
            main_html = esc(main_u)
        self.parts.append(
            f'<section class="phase" id="{a}"><div class="phase-num">PHASE {num}</div>'
            f'<div class="phase-rule"></div><p class="phase-name">{main_html}</p>{sub_html}</section>')
        self.toc.append(("phase", num, name, a))
        self.prev = "phase"

    def opener(self, label, title, rh, toc_level, toc_text, dropcap=True, cls="chap"):
        self.close_section()
        a = self.anchor()
        lab = f'<div class="ch-label">{esc(label)}</div>' if label else ""
        self.parts.append(
            f'<section class="{cls}" id="{a}"><div class="rhr">{esc(rh)}</div>'
            f'<header class="opener{"" if label else " nolabel"}">{lab}'
            f'<h1 class="ch-title">{split_title(title)}</h1>'
            f'<img class="flourish" src="../images/flourish.png" alt=""></header>')
        self.open_section = True
        self.toc.append((toc_level, None, toc_text, a))
        self.prev = "opener"
        self.dropcap_pending = dropcap

    # ----- paragraphs -----
    def para(self, info):
        segs, text = info["segs"], info["text"]
        st, al = info["style"], info["align"]
        if info["img"]:
            name, wpt, hpt = info["img"]
            qr = name == "image9.png"
            cls = "fig qr" if qr else "fig"
            # author's placed size, limited to the text block
            maxw, maxh = 312.0, 378.0
            if qr:
                maxh = 86.4          # 1.2 in: scannable, ~330 dpi from the supplied file
            k = self.fig_n
            self.fig_n += 1
            maxh = self.fig_heights.get(k, maxh)
            s = min(1.0, maxw / wpt, maxh / hpt)
            fig = (f'<figure class="{cls}" data-fig="{k}"><img src="../images/{name}" '
                   f'style="width:{wpt*s:.1f}pt;height:{hpt*s:.1f}pt" alt=""></figure>')
            self.dropcap_pending = False
            if self.fig_defer.get(k):
                # float the figure below the next paragraph(s) to avoid a page gap
                self.close_list()
                self.flush_fig()
                self.pending_fig = [fig, self.fig_defer[k]]
                return
            self.add(fig, "fig")
            return
        if not text.strip():
            return
        centered = al in ("center",)
        body = seg_html(segs, url_breaks=True)

        # chapter epigraph: centered italic quote right after an opener
        bal = ""
        if centered and info["all_ital"]:
            bw = balanced_width(text.strip(), "EBGaramond-Italic.ttf", 12, 276.0)
            if bw:
                bal = f' style="width:{bw:.1f}pt;margin-left:auto;margin-right:auto"'
        if self.prev == "opener" and centered and info["all_ital"] and self.opener_kind == "chapter":
            self.add(f'<p class="epigraph"{bal}>{body}</p>', "epigraph")
            return
        if centered and info["all_ital"]:
            self.add(f'<p class="keyline"{bal}>{body}</p>', "keyline")
            self.dropcap_pending = False
            return
        if centered:
            self.add(f'<p class="center">{body}</p>', "center")
            self.dropcap_pending = False
            return
        if st == "ListParagraph" and info["num"]:
            nid = info["num"]
            if self.list_open != nid:
                self.close_list()
                self.flush_fig()
                self.parts.append('<ol class="numlist">')
                self.list_open = nid
                self.list_counter[nid] = 0
            self.list_counter[nid] += 1
            self.parts.append(f'<li><span class="marker">{self.list_counter[nid]}.</span>{body}</li>')
            self.prev = "li"
            return
        m = re.match(r"(\d+)\.\s", text)
        if m and st == "BodyText":
            # typed numbers in the manuscript: hang the number, keep the text
            first = segs[0]
            rest = [(first[0][m.end():], first[1], first[2])] + list(segs[1:])
            if self.list_open != "typed":
                self.close_list()
                self.flush_fig()
                self.parts.append('<ol class="numlist">')
                self.list_open = "typed"
            mk = seg_html([(m.group(1) + ".", first[1], first[2])])
            self.parts.append(f'<li><span class="marker">{mk}</span>{seg_html(rest)}</li>')
            self.prev = "li"
            return
        if info["ind"] >= 360:
            cls = "script" if info["all_ital"] else "quote"
            self.add(f'<p class="{cls}">{body}</p>', cls)
            self.dropcap_pending = False
            return
        if info["all_bold"]:
            self.add(f'<p class="boldhead">{body}</p>', "boldhead")
            self.dropcap_pending = False
            return
        classes = []
        kind = "p"
        if self.prev in ("boldhead", "item") and segs and segs[0][1] and segs[0][0].rstrip().endswith(":"):
            classes.append("item")
            kind = "item"
        if self.prev in ("opener", "epigraph", "h3", "h4", "boldhead") or self.prev is None:
            classes.append("noindent")
        if self.dropcap_pending and re.match(r"[A-Za-z]", text):
            classes.append("dropcap")
        self.dropcap_pending = False
        if "dropcap" in classes:
            body = re.sub(r"^((?:<[^>]+>)*)([A-Za-z])", r'\1<span class="dc">\2</span>', body, count=1)
        c = f' class="{" ".join(classes)}"' if classes else ""
        self.add(f"<p{c}>{body}</p>", kind)

    def heading(self, level, text):
        self.dropcap_pending = False
        self.flush_fig()
        self.add(f'<h{level} class="h{level}">{esc(text)}</h{level}>', f"h{level}")


# --------------------------------------------------------------------------
def build(fig_heights=None, fig_defer=None):
    d = docx.Document(str(SRC))
    rels = d.part.rels
    body = d.element.body
    paras = [c for c in body if c.tag == W + "p"]   # the Word TOC (w:sdt) is skipped
    infos = [para_info(p, rels) for p in paras]

    # --- front matter (paragraphs 0-38) -----------------------------------
    first_h = next(i for i, x in enumerate(infos) if x["style"] == "Heading1")
    fm = [x for x in infos[:first_h] if x["text"].strip()]
    ft = [x["text"] for x in fm]
    title, subtitle, author, publisher = ft[0], ft[1], ft[2], ft[3]
    copyright_paras = fm[4:]
    assert title == "Declutter Beyond" and author == "Alex Lee", ft[:4]

    sub_words = subtitle.split(", ")
    # "Simplify Your Time, Digital Life, / Money, and Relationships"
    sub_html = esc(", ".join(sub_words[:2]) + ",") + "<br>" + esc(", ".join(sub_words[2:]))

    fm_html = [f'''<section class="titlepage">
<div class="tp-title">{esc(title.upper()).replace(" ", "<br>", 1)}</div>
<div class="tp-rule"></div>
<div class="tp-sub">{sub_html}</div>
<div class="tp-author">{esc(author.upper())}</div>
<div class="tp-pub">{esc(publisher)}</div>
</section>''']
    cp = []
    for x in copyright_paras:
        t = x["text"].strip()
        if t.endswith(":") and len(t) < 30:
            cp.append(f'<p class="cp-head">{esc(t)}</p>')
        else:
            cp.append(f"<p>{seg_html(x['segs'])}</p>")
    fm_html.append('<section class="copyright">' + "\n".join(cp) + "</section>")

    # --- main text ---------------------------------------------------------
    bk = Book(fig_heights, fig_defer)
    for idx in range(first_h, len(infos)):
        x = infos[idx]
        st, text = x["style"], x["text"].strip()
        if st == "Heading1":
            if re.match(r"Phase\s+[IVX]+:", text):
                bk.opener_kind = None
                bk.phase(text)
                continue
            m = re.match(r"(Introduction|CONCLUSION|Appendix [A-Z]):\s*(.*)", text, re.I)
            if m:
                lab = m.group(1).upper()
                ttl = m.group(2)
                bk.opener_kind = "chapter"
                cls = "chap intro" if lab == "INTRODUCTION" else "chap"
                bk.opener(lab, ttl, ttl, "top" if not lab.startswith("APPENDIX") else "sub",
                          f"{m.group(1).title() if lab != 'CONCLUSION' else 'Conclusion'}: {ttl}",
                          cls=cls)
            else:
                bk.opener_kind = "back"
                bk.opener(None, text, text, "top" if text == "A Note From Me to You" else "sub", text)
            continue
        if st == "Heading2":
            m = re.match(r"CHAPTER\s+(\d+):\s*(.*)", text)
            num, ttl = m.group(1), m.group(2)
            bk.opener_kind = "chapter"
            bk.opener(f"CHAPTER {num}", ttl, ttl, "chapter", f"Chapter {num}: {ttl}")
            continue
        if st == "Heading3":
            bk.heading(2, text)
            bk.prev = "h3"
            continue
        if st == "Heading4":
            bk.heading(3, text)
            bk.prev = "h4"
            continue
        bk.para(x)
    bk.close_section()

    # --- table of contents -------------------------------------------------
    toc = ['<section class="toc"><h1 class="toc-title"><span>TABLE OF CONTENTS</span></h1>']
    for level, num, text, a in bk.toc:
        if level == "phase":
            name = text.upper()
            if text_width(f"PHASE {num}: {name}", "nunito-sans-500-normal.ttf", 10.5) > 300 and " — " in name:
                n1, n2 = name.split(" — ", 1)
                nm = f"{esc(n1)} —<br>{esc(n2)}"
            else:
                nm = esc(name)
            toc.append(f'<p class="toc-phase"><a href="#{a}"><strong>PHASE {num}:</strong> {nm}</a></p>')
        elif level == "top":
            t = text.upper()
            if text_width(t, "nunito-sans-500-normal.ttf", 10.5) > 270 and ": " in t:
                x1, x2 = t.split(": ", 1)
                th = f"{esc(x1)}:<br>{esc(x2)}"
            else:
                th = esc(t)
            toc.append(f'<p class="toc-top"><a href="#{a}">{th}</a></p>')
        else:
            t = esc(text)
            if text_width(text, "EBGaramond-Regular.ttf", 11) > 270 and " — " in text:
                x1, x2 = text.split(" — ", 1)
                t = f"{esc(x1)} —<br>{esc(x2)}"
            toc.append(f'<p class="toc-entry"><a href="#{a}">{t}</a></p>')
    toc.append("</section>")

    doc = f'''<!DOCTYPE html>
<html lang="en-US"><head><meta charset="utf-8">
<title>{BOOK_TITLE}</title>
<meta name="author" content="Alex Lee">
<link rel="stylesheet" href="../book.css">
</head><body>
<div class="rhv">{BOOK_TITLE}</div>
{"".join(fm_html)}
{"".join(toc)}
{"".join(bk.parts)}
</body></html>'''
    OUT_HTML.write_text(doc, encoding="utf-8")
    return bk


def render():
    import weasyprint
    doc = weasyprint.HTML(filename=str(OUT_HTML)).render()
    doc.metadata.title = "Declutter Beyond: Simplify Your Time, Digital Life, Money, and Relationships"
    doc.metadata.authors = ["Alex Lee"]
    doc.write_pdf(str(OUT_PDF))
    return doc


TEXT_BOTTOM = 648 - 53.3      # bottom of the text block (pt)
FIG_MARGINS = 14 + 14 + 3


def fit_figures(pdf_path, fig_heights, fig_defer, final=False):
    """Pagination pass for illustrations.  A figure pushed to the top of a page
    leaves a gap on the page before.  Small overruns are solved by scaling the
    image (never below 75%); larger gaps by letting the following paragraph(s)
    flow ahead of the figure, as a floating figure would."""
    import pymupdf
    doc = pymupdf.open(pdf_path)
    changed = False
    k = -1
    for i in range(len(doc)):
        for info in doc[i].get_image_info():
            if (info["width"], info["height"]) == (153, 47):      # flourish
                continue
            k += 1
            x0, y0, x1, y1 = info["bbox"]
            if y0 > 90 or i == 0 or (info["width"], info["height"]) == (399, 399):
                continue
            prev = doc[i - 1]
            lines = [s["origin"][1] for b in prev.get_text("dict")["blocks"] if b["type"] == 0
                     for l in b["lines"] for s in l["spans"]
                     if s["text"].strip() and 60 < s["origin"][1] < 600]
            if not lines:
                continue
            gap = TEXT_BOTTOM - (max(lines) + 5)
            avail = gap - FIG_MARGINS
            h = y1 - y0
            if 0.75 * h <= avail < h:
                fig_heights[k] = round(avail, 1)
                changed = True
            elif gap > 64 and fig_defer.get(k, 0) < 4:
                fig_defer[k] = fig_defer.get(k, 0) + 1
                changed = True
            elif gap > 64 and final:
                # floating did not close the gap: keep the author's order
                fig_defer.pop(k, None)
                changed = True
    return changed


if __name__ == "__main__":
    fig_heights, fig_defer = {}, {}
    build()
    if "--html-only" not in sys.argv:
        for _ in range(8):
            d = render()
            if not fit_figures(OUT_PDF, fig_heights, fig_defer):
                break
            build(fig_heights, fig_defer)
        if fit_figures(OUT_PDF, fig_heights, fig_defer, final=True):
            build(fig_heights, fig_defer)
            d = render()
        print("figure scaling:", fig_heights, "figure float:", fig_defer)
        print(f"{OUT_PDF.name}: {len(d.pages)} pages")
