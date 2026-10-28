#!/usr/bin/env python3
"""Kindle EPUB of "Declutter Beyond", built from output/book.html, the same
structured source as the print PDF (client edits, Book 1 copyright page,
web addresses and QR codes included).

Print-only devices are dropped (running heads, flourish ornament, drop caps,
spacing/tuning classes); the two web addresses become links and the QR images
get the alt text requested by the client.
"""
import datetime
import html
import re
import shutil
import uuid
import zipfile
from pathlib import Path

import lxml.html
from lxml import etree
from PIL import Image

HERE = Path(__file__).resolve().parent
SRC = HERE / "output" / "book.html"
OUT = HERE / "output" / "Declutter_Beyond_Alex_Lee.epub"
WORK = HERE / "output" / "epub_build"

TITLE = "Declutter Beyond"
SUBTITLE = "Simplify Your Time, Digital Life, Money, and Relationships"
AUTHOR = "Alex Lee"
PUBLISHER = "Purposeful Living Press"
LINKS = {
    "beyond-review.purposefullivingpress.com": "https://beyond-review.purposefullivingpress.com",
    "resources-declutter.purposefullivingpress.com": "https://resources-declutter.purposefullivingpress.com",
}
QR_ALT = {
    "qr-review-beyond-captioned.png": "QR code linking to the review page for this book.",
    "qr-resources-declutter-captioned.png": "QR code linking to the companion resources download.",
}

CSS = """@charset "utf-8";
body { font-family: serif; line-height: 1.4; margin: 0 4%; }
p { margin: 0; text-indent: 1.5em; text-align: justify; }
p.noindent, p.dropcap, p.center, p.keyline, p.epigraph, p.script, p.quote, p.boldhead, p.item, p.cp, p.cp-head,
p.phase-name, p.ch-label, p.back-sub { text-indent: 0; }
p.center { text-align: center; margin: 0.6em 0; }
p.keyline, p.epigraph { text-align: center; font-style: italic; margin: 0.8em 1.5em; }
p.epigraph { margin-bottom: 1.6em; }
p.script, p.quote { text-align: left; margin: 0.7em 1.5em; }
p.script { font-style: italic; }
p.boldhead { text-align: left; margin-top: 0.8em; page-break-after: avoid; }
p.item { margin: 0.3em 0 0 1em; }
h1, h2, h3, .ch-label, .phase-name, .phase-num, .back-sub { font-family: sans-serif; page-break-after: avoid; }
h1.phase-num { text-align: center; margin-top: 30%; font-size: 1.8em; font-weight: bold; }
p.phase-name { text-align: center; font-size: 1.4em; margin-top: 0.8em; }
p.ch-label { text-align: center; color: #666; font-weight: bold; margin-top: 2em; letter-spacing: 0.05em; }
h1.ch-title { text-align: center; font-weight: normal; font-size: 1.6em; margin: 0.3em 0 1.6em; }
h1.back-title { text-align: center; font-size: 1.3em; margin: 2em 0 1.5em; }
p.back-sub { font-size: 1.15em; text-transform: uppercase; margin: 0 0 0.6em; }
h2 { font-size: 1.2em; font-weight: normal; margin: 1.6em 0 0.5em; }
h3 { font-size: 1em; font-weight: bold; margin: 1.2em 0 0.3em; }
ol { margin: 0.6em 0 0.6em 1.2em; padding-left: 1.2em; }
li { margin-bottom: 0.4em; text-align: left; }
div.figure { text-align: center; margin: 1em 0; page-break-inside: avoid; }
div.figure img { max-width: 100%; height: auto; }
div.qr img { width: 45%; max-width: 2.2in; }
a { color: inherit; text-decoration: underline; }
.titlepage { text-align: center; margin-top: 15%; }
.titlepage p { text-indent: 0; text-align: center; }
h1.booktitle { font-size: 2.2em; letter-spacing: 0.04em; margin-bottom: 0.6em; }
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

KEEP_CLASSES = {"noindent", "center", "keyline", "epigraph", "script", "quote", "boldhead", "item",
                "cp-head", "phase-name", "ch-label", "back-sub", "ch-title", "back-title", "phase-num"}


def inner(el):
    """Inner XHTML of an element with print-only markup removed."""
    el = clean(el)
    s = (el.text and html.escape(el.text, quote=False) or "")
    for ch in el:
        s += etree.tostring(ch, method="xml", encoding="unicode", with_tail=True)
    s = re.sub(r"\s+", " ", s).replace("​", "").strip()
    for shown, url in LINKS.items():
        s = s.replace(shown, f'<a href="{url}">{shown}</a>')
    return s


def clean(el):
    el = lxml.html.fromstring(lxml.html.tostring(el, encoding="unicode"))
    for span in el.xpath(".//span"):               # drop caps, no-hyphen and URL wrappers
        span.drop_tag()
    for br in el.xpath(".//br"):
        br.tail = " " + (br.tail or "")
        br.drop_tag()
    for e in el.iter():
        e.attrib.pop("class", None)
        e.attrib.pop("id", None)
        e.attrib.pop("style", None)
    for tag, new in (("strong", "b"), ("em", "i")):
        for e in el.iter(tag):
            e.tag = new
    return el


def classes(el):
    return [c for c in (el.get("class") or "").split() if c in KEEP_CLASSES]


def convert_section(sec, img_dir, used):
    out = []
    for el in sec.iter():
        if el is sec or el.getparent() is not sec and el.getparent().tag not in ("header",):
            continue
        cls = (el.get("class") or "").split()
        if "rhr" in cls or el.tag == "img" and "flourish" in cls:
            continue
        if el.tag == "header":
            continue                          # its children are visited next
        if el.tag == "div" and "ch-label" in cls:
            out.append(f'<p class="ch-label">{inner(el)}</p>')
        elif el.tag == "h1":
            c = "ch-title" if "ch-title" in cls else "back-title"
            out.append(f'<h1 class="{c}">{inner(el)}</h1>')
        elif el.tag == "div" and "phase-num" in cls:
            out.append(f'<h1 class="phase-num">{inner(el)}</h1>')
        elif el.tag == "div" and "phase-rule" in cls:
            continue
        elif el.tag in ("h2", "h3"):
            out.append(f"<{el.tag}>{inner(el)}</{el.tag}>")
        elif el.tag == "figure":
            img = el.find(".//img")
            src = (SRC.parent / img.get("src")).resolve()
            name = src.name
            if name in QR_ALT:
                shutil.copy(src, img_dir / name)
                used.add(name)
                out.append(f'<div class="figure qr"><img src="images/{name}" alt="{QR_ALT[name]}"/></div>')
            else:
                jpg = src.stem + ".jpg"
                if jpg not in used:
                    with Image.open(src) as im:
                        im.convert("RGB").save(img_dir / jpg, quality=85)
                    used.add(jpg)
                out.append(f'<div class="figure"><img src="images/{jpg}" alt="Illustration"/></div>')
        elif el.tag == "ol":
            items = []
            for li in el.findall("li"):
                for m in li.xpath(".//span[contains(@class,'marker')]"):
                    m.drop_tree()
                items.append(f"<li>{inner(li)}</li>")
            out.append("<ol>" + "".join(items) + "</ol>")
        elif el.tag == "p":
            c = classes(el)
            if "dropcap" in cls:
                c = ["noindent"]
            attr = f' class="{" ".join(c)}"' if c else ""
            out.append(f"<p{attr}>{inner(el)}</p>")
    return "\n".join(out)


def xhtml(title, body):
    return ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" '
            'xml:lang="en-US" lang="en-US">\n'
            f'<head><meta charset="utf-8"/><title>{html.escape(title)}</title>'
            '<link rel="stylesheet" type="text/css" href="style.css"/></head>\n'
            f'<body>\n{body}\n</body></html>\n')


def build():
    if WORK.exists():
        shutil.rmtree(WORK)
    oebps = WORK / "OEBPS"
    img_dir = oebps / "images"
    img_dir.mkdir(parents=True)
    body = lxml.html.parse(str(SRC)).getroot().find("body")
    secs = [s for s in body if s.tag == "section"]
    title_sec, copy_sec, toc_sec, main = secs[0], secs[1], secs[2], secs[3:]
    used = set()
    files = []          # (id, title, body)

    files.append(("title", TITLE,
                  f'<div class="titlepage"><h1 class="booktitle">{TITLE.upper()}</h1>'
                  f'<p class="subtitle">{html.escape(SUBTITLE)}</p>'
                  f'<p class="author">{AUTHOR.upper()}</p><p class="publisher">{PUBLISHER.upper()}</p></div>'))
    cp = []
    for p in copy_sec.findall("p"):
        c = "cp-head" if "cp-head" in (p.get("class") or "") else "cp"
        cp.append(f'<p class="{c}">{inner(p)}</p>')
    files.append(("copyright", "Copyright", "\n".join(cp)))
    files.append(("toc", "Table of Contents", ""))

    # TOC entries from the printed TOC (same wording and hierarchy)
    toc = []
    for p in toc_sec.findall("p"):
        a = p.find("a")
        text = re.sub(r"\s+", " ", a.text_content()).strip()
        toc.append((p.get("class"), text, a.get("href")[1:]))
    id_to_file = {}
    for k, sec in enumerate(main, 1):
        fid = f"s{k:02d}"
        id_to_file[sec.get("id")] = fid
        h = sec.find(".//h1")
        t = re.sub(r"\s+", " ", h.text_content()).strip() if h is not None else \
            re.sub(r"\s+", " ", sec.find("./div").text_content()).strip()
        files.append((fid, t, convert_section(sec, img_dir, used)))

    def entry(text, target):
        return f'<a href="{id_to_file[target]}.xhtml">{html.escape(text)}</a>'

    nav = '<ol>'
    open_phase = False
    for cls, text, target in toc:
        if cls == "toc-entry" and open_phase:
            nav += f"<li>{entry(text, target)}</li>"
            continue
        if open_phase:
            nav += "</ol></li>"
            open_phase = False
        if cls == "toc-phase":
            nav += f"<li>{entry(text, target)}<ol>"
            open_phase = True
        else:
            nav += f"<li>{entry(text, target)}</li>"
    if open_phase:
        nav += "</ol></li>"
    nav += "</ol>"
    first_body = id_to_file[toc[0][2]]
    toc_body = (f'<nav epub:type="toc" id="toc"><h1 class="back-title">TABLE OF CONTENTS</h1>{nav}</nav>'
                '<nav epub:type="landmarks" hidden="hidden"><ol>'
                '<li><a epub:type="toc" href="toc.xhtml">Table of Contents</a></li>'
                f'<li><a epub:type="bodymatter" href="{first_body}.xhtml">Start of Content</a></li>'
                '</ol></nav>')

    (oebps / "style.css").write_text(CSS, encoding="utf-8")
    for fid, title, b in files:
        (oebps / f"{fid}.xhtml").write_text(xhtml(title, toc_body if fid == "toc" else b), encoding="utf-8")

    manifest = ['<item id="css" href="style.css" media-type="text/css"/>']
    for fid, _, _ in files:
        props = ' properties="nav"' if fid == "toc" else ""
        manifest.append(f'<item id="{fid}" href="{fid}.xhtml" media-type="application/xhtml+xml"{props}/>')
    for k, name in enumerate(sorted(used)):
        mt = "image/png" if name.endswith(".png") else "image/jpeg"
        manifest.append(f'<item id="img{k}" href="images/{name}" media-type="{mt}"/>')
    spine = "".join(f'<itemref idref="{fid}"/>' for fid, _, _ in files)
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    opf = f'''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="en-US">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="bookid">urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, "declutter-beyond-ebook")}</dc:identifier>
<dc:title>{TITLE}</dc:title>
<dc:creator id="author">{AUTHOR}</dc:creator>
<meta refines="#author" property="role" scheme="marc:relators">aut</meta>
<dc:publisher>{PUBLISHER}</dc:publisher>
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
    (WORK / "META-INF").mkdir()
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
    print(f"{OUT.name}: {len(files)} files, {len(used)} images")


if __name__ == "__main__":
    build()
