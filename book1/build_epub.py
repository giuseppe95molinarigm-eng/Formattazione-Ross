#!/usr/bin/env python3
"""Build the Kindle EPUB of "Declutter Your Home, Calm Your Life" from the
approved V11 print PDF (the only source available).

The text is read from the PDF, line by line, and rebuilt into paragraphs,
headings, lists and images using the book's own layout rules (indents,
fonts, sizes). Nothing is retyped. The two web addresses become links,
and the QR images get the alt text the client asked for.
"""
import html
import re
import sys
import uuid
import zipfile
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from pdf_lines import page_lines  # noqa: E402

PDF = HERE / "output" / "V11-Declutter_Your_Home_Alex_Lee_6x9.pdf"
OUT = HERE / "output" / "Declutter_Your_Home_Calm_Your_Life_Alex_Lee.epub"
WORK = HERE / "output" / "epub_build"

TITLE = "Declutter Your Home, Calm Your Life"
SUBTITLE = "A Room-by-Room Guide to Simple Living, Organized Spaces, and Stress-Free Daily Routines"
AUTHOR = "Alex Lee"
PUBLISHER = "Purposeful Living Press"

LINKS = {
    "home-review.purposefullivingpress.com": "https://home-review.purposefullivingpress.com",
    "resources-declutter.purposefullivingpress.com": "https://resources-declutter.purposefullivingpress.com",
}
QR_FILES = {
    "review": (HERE / "qr" / "QR_home-review_labeled.png", "QR code linking to the review page for this book"),
    "resources": (HERE / "qr" / "qr-resources-declutter-captioned.png",
                  "QR code linking to the companion resources download."),
}
QR_PAGES = {"49": "resources", "219": "review", "221": "resources"}

ROMAN_FRONT = {"i", "ii", "iii", "iv"}


def esc(s):
    return html.escape(s, quote=False)


# ---------------------------------------------------------------------------
# reading the PDF
# ---------------------------------------------------------------------------
def margins(label):
    """Left / right edge of the text block for a page label."""
    try:
        n = int(label)
    except ValueError:
        n = {"i": 1, "ii": 2, "iii": 3, "iv": 4}[label]
    return (72.0, 384.0) if n % 2 else (50.4, 362.4)


def is_flourish(info):
    return (info["width"], info["height"]) == (153, 47)


def page_items(doc, page, img_dir, img_count):
    """Text lines and images of one page, in reading order."""
    label = page.get_label()
    items = []
    for info in page.get_image_info(xrefs=True):
        if is_flourish(info) or info["xref"] == 0:
            continue
        x0, y0, x1, y1 = info["bbox"]
        if label in QR_PAGES:
            key = QR_PAGES[label]
            items.append(dict(kind="qr", y=y0, key=key))
            continue
        img_count[0] += 1
        name = f"img{img_count[0]:02d}.jpg"
        pix = pymupdf.Pixmap(doc, info["xref"])
        if pix.colorspace is None or pix.colorspace.n != 3 or pix.alpha:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        pix.save(str(img_dir / name), jpg_quality=88)
        items.append(dict(kind="img", y=y0, file=name, w=pix.width, h=pix.height,
                          width_pt=x1 - x0))
    lines = page_lines(page)
    # drop caps: attach the big letter to the first line of its paragraph
    caps = [l for l in lines if l["size"] > 30 and "Garamond" in l["font"]]
    for c in caps:
        lines.remove(c)
        target = min((l for l in lines if c["y"] - 24 < l["y"] < c["y"] - 4), key=lambda l: l["y"])
        # the drop cap is a word of its own ("A child's...") when a space separates it
        sep = " " if c["text"] != c["text"].rstrip() else ""
        target["runs"] = [(c["text"].strip() + sep, False, False, 12)] + target["runs"]
        target["text"] = c["text"].strip() + sep + target["text"]
        target["dropcap"] = True
        target["x0"] = c["x0"]
    for l in lines:
        l["kind"] = "line"
        items.append(l)
    items.sort(key=lambda it: it["y"])
    return label, items


# ---------------------------------------------------------------------------
# rebuilding structure
# ---------------------------------------------------------------------------
class Builder:
    def __init__(self):
        self.files = []          # (id, title, html_body)
        self.body = []
        self.title = None
        self.para = None         # open paragraph: dict(tag, cls, runs)
        self.list = None         # open list: (tag, [items])
        self.prev = None         # previous line
        self.heading_buf = None  # consecutive heading lines being joined
        self.toc = []            # (level, title, file_id)
        self.label = None
        self.chapter_label = None

    # ----- output helpers -----
    def flush_para(self):
        if self.para:
            runs = self.para["runs"]
            inner = runs_html(runs)
            if self.list is not None and self.para.get("li"):
                self.list[1].append(inner)
            else:
                cls = f' class="{self.para["cls"]}"' if self.para.get("cls") else ""
                self.body.append(f'<p{cls}>{inner}</p>')
            self.para = None

    def flush_list(self):
        self.flush_para()
        if self.list:
            tag, items = self.list
            self.body.append(f"<{tag}>" + "".join(f"<li>{i}</li>" for i in items) + f"</{tag}>")
            self.list = None

    def flush_heading(self):
        if self.heading_buf:
            tag, cls, text = self.heading_buf
            c = f' class="{cls}"' if cls else ""
            self.body.append(f"<{tag}{c}>{esc(text)}</{tag}>")
            self.heading_buf = None

    def flush_all(self):
        self.flush_heading()
        self.flush_list()

    def new_file(self, fid, title, level=1):
        self.flush_all()
        if self.body:
            self.files.append((self.cur_id, self.cur_title, "\n".join(self.body)))
        self.body = []
        self.cur_id, self.cur_title = fid, title
        if level:
            self.toc.append((level, title, fid))

    def heading(self, tag, cls, text, join_gap):
        self.flush_list()
        if (self.heading_buf and self.heading_buf[0] == tag and self.heading_buf[1] == cls
                and self.prev is not None and join_gap):
            self.heading_buf = (tag, cls, self.heading_buf[2].rstrip() + " " + text.strip())
        else:
            self.flush_heading()
            self.heading_buf = (tag, cls, text.strip())


def runs_html(runs):
    """Runs -> HTML; web addresses become links."""
    out = []
    for text, bold, ital, _size in runs:
        t = esc(text)
        if bold and ital:
            t = f"<b><i>{t}</i></b>"
        elif bold:
            t = f"<b>{t}</b>"
        elif ital:
            t = f"<i>{t}</i>"
        out.append(t)
    s = "".join(out)
    s = re.sub(r"</b><b>|</i><i>|</b></i><b><i>", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    for shown, url in LINKS.items():
        s = s.replace(esc(shown), f'<a href="{url}">{esc(shown)}</a>')
    return s


def join_runs(a, b):
    """Append line b's runs to paragraph runs a."""
    if not a:
        return list(b)
    last = a[-1][0].rstrip()
    first = b[0][0].lstrip()
    if re.search(r"[\w][-‐]$", last) or last.endswith("—") or last.endswith("/") or first.startswith("—"):
        sep = ""
    else:
        sep = " "
    a = a[:-1] + [(last + sep, a[-1][1], a[-1][2], a[-1][3])]
    return a + [(first,) + tuple(b[0][1:])] + list(b[1:])


def build():
    doc = pymupdf.open(PDF)
    if WORK.exists():
        import shutil
        shutil.rmtree(WORK)
    (WORK / "OEBPS" / "images").mkdir(parents=True)
    img_dir = WORK / "OEBPS" / "images"
    bd = Builder()
    bd.cur_id, bd.cur_title = "front", "Title Page"
    img_count = [0]
    file_no = [0]

    def fid():
        file_no[0] += 1
        return f"s{file_no[0]:02d}"

    # ---- title page and copyright (pages i, ii) ----
    bd.body.append(f'<div class="titlepage"><h1 class="booktitle">{esc(TITLE)}</h1>'
                   f'<p class="subtitle">{esc(SUBTITLE)}</p>'
                   f'<p class="author">{esc(AUTHOR.upper())}</p>'
                   f'<p class="publisher">{esc(PUBLISHER.upper())}</p></div>')
    bd.new_file("copyright", "Copyright", level=0)
    for l in page_lines(doc[1]):
        if l["runs"][0][1] and l["text"].strip().endswith(":"):
            bd.flush_para()
            bd.body.append(f'<p class="cp-head">{esc(l["text"].strip())}</p>')
            continue
        start = bd.prev is None or l["y"] - bd.prev["y"] > 15
        if start:
            bd.flush_para()
            bd.para = dict(cls="cp", runs=list(l["runs"]))
        else:
            bd.para["runs"] = join_runs(bd.para["runs"], l["runs"])
        bd.prev = l
    bd.flush_all()
    bd.new_file("toc", "Contents", level=0)       # filled in at the end
    bd.body.append("<!-- toc -->")
    bd.prev = None

    # ---- main text (from arabic page 1) ----
    first = doc.get_page_numbers("1")[0]
    pending_label = None
    for pno in range(first, doc.page_count):
        label, items = page_items(doc, doc[pno], img_dir, img_count)
        L, R = margins(label)
        mid = (L + R) / 2
        page_prev_y = None
        for it in items:
            if it["kind"] in ("img", "qr"):
                bd.flush_all()
                if it["kind"] == "qr":
                    path, alt = QR_FILES[it["key"]]
                    bd.body.append(f'<div class="qr"><img src="images/{path.name}" alt="{esc(alt)}"/></div>')
                else:
                    width = min(100, round(it["width_pt"] / (R - L) * 100))
                    bd.body.append(f'<div class="figure"><img src="images/{it["file"]}" alt="Illustration" '
                                   f'style="width:{width}%"/></div>')
                bd.prev = None
                page_prev_y = None
                continue
            l = it
            f, size, text = l["font"], l["size"], l["text"]
            gap = None if page_prev_y is None else l["y"] - page_prev_y
            page_prev_y = l["y"]
            # --- phase divider
            if "Avenir-Black" in f and size >= 29:
                fid_ = fid()
                bd.new_file(fid_, text.strip(), level=1)
                bd.body.append(f'<h1 class="phase-num">{esc(text.strip())}</h1>')
                bd.phase_title = fid_
                bd.prev = l
                continue
            if "Avenir-Book" in f and size >= 27:
                bd.heading("p", "phase-name", text, gap is not None and gap < 45)
                bd.prev = l
                # TOC title = "PHASE I: THE FOUNDATION & MINDSET"
                continue
            # --- chapter label / back-matter title
            if "Avenir-Black" in f and 15 < size < 17:
                gray = l["runs"] and l.get("color", 0) == 0x808285
                pending_label = text.strip()
                bd.flush_all()
                if is_gray(doc[pno], l):
                    bd.chapter_label = pending_label
                else:
                    fid_ = fid()
                    toc_name = {"A NOTE FROM ME TO YOU": "A NOTE FROM ME TO YOU", "APPENDIX": "Appendix",
                                "ABOUT THE AUTHOR": "About The Author"}.get(pending_label, title_case(pending_label))
                    bd.new_file(fid_, toc_name, level=2)
                    bd.body.append(f'<h1 class="back-title">{esc(pending_label)}</h1>')
                    bd.chapter_label = None
                bd.prev = l
                continue
            if "Avenir-Book" in f and 21 < size < 23:
                if bd.chapter_label and not (bd.heading_buf and bd.heading_buf[1] == "ch-title"):
                    fid_ = fid()
                    bd.flush_all()
                    bd.pending_chapter = (fid_, bd.chapter_label)
                    bd.new_file(fid_, bd.chapter_label, level=2)
                    bd.body.append(f'<p class="ch-label">{esc(bd.chapter_label)}</p>')
                bd.heading("h1", "ch-title", text, True)
                bd.prev = l
                continue
            # --- headings
            if "Avenir-Medium" in f and 13.5 < size < 14.5:
                bd.heading("h2", None, text, gap is not None and gap < 18)
                bd.prev = l
                continue
            if "Garamond-Bold" in f and 12.5 < size < 13.5:
                bd.heading("h3", None, text, gap is not None and gap < 17)
                bd.prev = l
                continue
            bd.flush_heading()
            whole_bi = all((r[1] and r[2]) or not r[0].strip() for r in l["runs"])
            if whole_bi and abs((l["x0"] + l["x1"]) / 2 - mid) < 4 and l["x0"] - L > 5:
                whole_bi = False                     # a centred line, not a heading
            if whole_bi and len(text) < 90 and (bd.para is None or gap is None or gap > 17):
                bd.flush_list()
                bd.body.append(f"<h4>{esc(text.strip())}</h4>")
                bd.prev = l
                continue
            # --- lists
            m_bul = re.match(r"\s*•\s*", text)
            m_num = re.match(r"\s*(\d+)\.\s+", text)
            indent = l["x0"] - L
            centered = (abs((l["x0"] + l["x1"]) / 2 - mid) < 4 and indent > 5 and abs(indent - 14.4) > 1
                        and not (m_bul or m_num))
            if m_bul or (m_num and indent > 10):
                tag = "ul" if m_bul else "ol"
                cut = (m_bul or m_num).end()
                runs = strip_prefix(l["runs"], cut)
                bd.flush_para()
                if not bd.list or bd.list[0] != tag:
                    bd.flush_list()
                    bd.list = (tag, [])
                bd.para = dict(li=True, runs=runs)
                bd.prev = l
                continue
            if bd.list and bd.para and bd.para.get("li") and indent > 25 and not centered:
                bd.para["runs"] = join_runs(bd.para["runs"], l["runs"])
                bd.prev = l
                continue
            # --- body paragraphs
            dropcap = l.get("dropcap")
            new_para = (bd.para is None or dropcap or abs(indent - 14.4) < 2
                        or (gap is not None and gap > 17.5)
                        or (gap is not None and abs(indent) < 2 and bd.prev is not None
                            and bd.prev.get("x1", R) < R - 30 and not centered)
                        or centered != (bd.para or {}).get("centered", False)
                        or (bd.para or {}).get("li"))
            if new_para:
                if bd.para and bd.para.get("li"):
                    bd.flush_list()
                bd.flush_list()
                cls = "dropcap" if dropcap else ("center" if centered else
                                                 ("noindent" if abs(indent) < 2 else None))
                bd.para = dict(cls=cls, runs=list(l["runs"]), centered=centered)
            else:
                bd.para["runs"] = join_runs(bd.para["runs"], l["runs"])
            bd.prev = l
    bd.new_file("end", "", level=0)
    files = bd.files[:]
    return doc, files, bd.toc, img_count[0]


def is_gray(page, line):
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                if abs(s["origin"][1] - line["y"]) < 0.6 and s["text"].strip():
                    return s["color"] == 0x808285
    return False


def strip_prefix(runs, n):
    out, skip = [], n
    for t, b, i, s in runs:
        if skip >= len(t):
            skip -= len(t)
            continue
        out.append((t[skip:], b, i, s))
        skip = 0
    if out:
        out[0] = (out[0][0].lstrip(" \t"),) + out[0][1:]
    return out


def title_case(s):
    small = {"a", "an", "and", "the", "to", "of", "for", "in", "on", "or", "from", "me"}
    words = s.lower().split()
    return " ".join(w if (k and w in small) else w.capitalize() for k, w in enumerate(words))


# ---------------------------------------------------------------------------
CSS = """
@charset "utf-8";
body { font-family: serif; line-height: 1.4; margin: 0 4%; }
p { margin: 0; text-indent: 1.5em; text-align: justify; }
p.noindent, p.dropcap, p.center, p.cp, p.cp-head { text-indent: 0; }
p.center { text-align: center; margin: 0.6em 0; }
h1, h2, h3, h4, .ch-label, .phase-name { font-family: sans-serif; font-weight: normal; page-break-after: avoid; }
h1.phase-num { text-align: center; margin-top: 30%; font-weight: bold; font-size: 1.8em; }
p.phase-name { text-align: center; text-indent: 0; font-size: 1.5em; margin-top: 0.8em; }
p.ch-label { text-align: center; text-indent: 0; color: #666; font-weight: bold; margin-top: 2em; letter-spacing: 0.05em; }
h1.ch-title { text-align: center; font-size: 1.6em; margin: 0.3em 0 1.6em; }
h1.back-title { text-align: center; font-size: 1.3em; font-weight: bold; margin: 2em 0 1.5em; }
h2 { font-size: 1.2em; margin: 1.6em 0 0.5em; }
h3 { font-family: serif; font-weight: bold; font-size: 1.05em; margin: 1.2em 0 0.3em; }
h4 { font-family: serif; font-weight: bold; font-style: italic; font-size: 1em; margin: 1em 0 0.2em; }
ul, ol { margin: 0.6em 0 0.6em 1.2em; padding-left: 1.2em; }
li { margin-bottom: 0.4em; text-align: left; }
div.figure, div.qr { text-align: center; margin: 1em 0; page-break-inside: avoid; }
div.figure img { max-width: 100%; height: auto; }
div.qr img { width: 50%; max-width: 2.5in; height: auto; }
a { color: inherit; text-decoration: underline; }
.titlepage { text-align: center; margin-top: 15%; }
h1.booktitle { font-size: 2em; font-weight: bold; letter-spacing: 0.03em; margin-bottom: 0.8em; }
.titlepage p { text-indent: 0; text-align: center; }
p.subtitle { font-style: italic; font-size: 1.15em; margin-bottom: 4em; }
p.author { font-size: 1.4em; font-weight: bold; letter-spacing: 0.08em; }
p.publisher { margin-top: 0.5em; font-size: 0.9em; letter-spacing: 0.05em; }
p.cp { font-size: 0.85em; margin-bottom: 0.8em; text-align: left; }
p.cp-head { font-size: 0.85em; font-weight: bold; margin-top: 1.2em; }
nav ol { list-style: none; padding-left: 0; margin-left: 0; }
nav ol ol { padding-left: 1.2em; }
nav li { margin: 0.35em 0; }
nav a { text-decoration: none; }
"""


def xhtml(title, body):
    return ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" '
            'xml:lang="en-US" lang="en-US">\n'
            f'<head><meta charset="utf-8"/><title>{esc(title)}</title>'
            '<link rel="stylesheet" type="text/css" href="style.css"/></head>\n'
            f'<body>\n{body}\n</body></html>\n')


def write_epub(doc, files, toc, n_images):
    import shutil
    oebps = WORK / "OEBPS"
    for key, (path, _alt) in QR_FILES.items():
        shutil.copy(path, oebps / "images" / path.name)
    (oebps / "style.css").write_text(CSS, encoding="utf-8")

    # navigation: phases at level 1 with their chapters nested
    tree = []
    for level, title, fid_ in toc:
        if level == 1:
            tree.append([title, fid_, []])
        elif tree and level == 2 and title.upper().startswith("CHAPTER") and tree[-1][0].startswith("PHASE"):
            tree[-1][2].append((title, fid_))
        else:
            tree.append([title, fid_, []])
    chap_titles = {}
    for fid_, title, body in files:
        m = re.search(r'<h1 class="ch-title">(.*?)</h1>', body)
        p = re.search(r'<p class="phase-name">(.*?)</p>', body)
        if m:
            chap_titles[fid_] = html.unescape(m.group(1))
        elif p:
            chap_titles[fid_] = html.unescape(p.group(1))

    def label_for(title, fid_):
        """Entries as in the printed Table of Contents."""
        sub = chap_titles.get(fid_)
        if title.upper().startswith("PHASE") and sub:
            return f"{title.upper()}: {sub.upper()}"
        if sub:
            word, _, num = title.partition(" ")
            return f"{word.capitalize()} {num}: {sub}".replace(" :", ":") if num else f"{word.capitalize()}: {sub}"
        return title

    def ol(nodes):
        out = "<ol>"
        for node in nodes:
            title, fid_ = node[0], node[1]
            out += f'<li><a href="{fid_}.xhtml">{esc(label_for(title, fid_))}</a>'
            if len(node) > 2 and node[2]:
                out += ol([[t, f] for t, f in node[2]])
            out += "</li>"
        return out + "</ol>"

    nav_list = ol(tree)
    nav = (f'<nav epub:type="toc" id="toc"><h1 class="back-title">TABLE OF CONTENTS</h1>{nav_list}</nav>'
           '<nav epub:type="landmarks" hidden="hidden"><ol>'
           '<li><a epub:type="toc" href="toc.xhtml">Table of Contents</a></li>'
           f'<li><a epub:type="bodymatter" href="{tree[0][1]}.xhtml">Start of Content</a></li>'
           '</ol></nav>')
    pages = []
    for fid_, title, body in files:
        if fid_ == "toc":
            body = nav
        (oebps / f"{fid_}.xhtml").write_text(xhtml(title or TITLE, body), encoding="utf-8")
        pages.append(fid_)

    images = sorted(p.name for p in (oebps / "images").iterdir())
    manifest = ['<item id="css" href="style.css" media-type="text/css"/>']
    for p_ in pages:
        props = ' properties="nav"' if p_ == "toc" else ""
        manifest.append(f'<item id="{p_}" href="{p_}.xhtml" media-type="application/xhtml+xml"{props}/>')
    for k, name in enumerate(images):
        mt = "image/png" if name.endswith(".png") else "image/jpeg"
        manifest.append(f'<item id="img{k}" href="images/{name}" media-type="{mt}"/>')
    spine = "".join(f'<itemref idref="{p_}"/>' for p_ in pages)
    import datetime
    now = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    opf = f'''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="en-US">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="bookid">urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, "declutter-your-home-calm-your-life-ebook")}</dc:identifier>
<dc:title>{esc(TITLE)}</dc:title>
<dc:creator id="author">{esc(AUTHOR)}</dc:creator>
<meta refines="#author" property="role" scheme="marc:relators">aut</meta>
<dc:publisher>{esc(PUBLISHER)}</dc:publisher>
<dc:language>en-US</dc:language>
<dc:date>2026</dc:date>
<meta property="dcterms:modified">{now}</meta>
</metadata>
<manifest>
{chr(10).join(manifest)}
</manifest>
<spine>{spine}</spine>
</package>'''
    (oebps / "content.opf").write_text(opf, encoding="utf-8")
    (WORK / "META-INF").mkdir(exist_ok=True)
    (WORK / "META-INF" / "container.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<container version="1.0" '
        'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
        '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
        '</rootfiles></container>', encoding="utf-8")
    if OUT.exists():
        OUT.unlink()
    with zipfile.ZipFile(OUT, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        for f in sorted(WORK.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(WORK).as_posix(), compress_type=zipfile.ZIP_DEFLATED)
    print(f"{OUT.name}: {len(pages)} files, {len(images)} images")


if __name__ == "__main__":
    doc, files, toc, n = build()
    write_epub(doc, files, toc, n)
