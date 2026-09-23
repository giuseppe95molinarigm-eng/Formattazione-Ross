#!/usr/bin/env python3
"""Build "The Declutter Beyond Toolkit" printable PDF (US Letter).

The Toolkit is the downloadable companion the main book points to ("printable
worksheets ... available as a download"), so it is set for home printing on
8.5 x 11 in paper, in the same design system as the book (book.css tokens:
EB Garamond body, Avenir-style display, flourish, underlined caps titles).

Text is carried over run by run; nothing is rewritten.  Paragraphs made of
underscores (the manuscript's writing lines) are drawn as ruled writing lines,
one rule per manuscript line.
"""
import html
import re
import sys
from pathlib import Path

import docx

HERE = Path(__file__).resolve().parent
BOOK = HERE.parent
sys.path.insert(0, str(BOOK))
from build_book import para_info, seg_html, esc, W  # noqa: E402  (same docx reader as the book)

SRC = HERE / "source" / "Declutter_Beyond_Checklist_v13_7.docx"
OUT_HTML = HERE / "output" / "toolkit.html"
OUT_PDF = HERE / "output" / "Declutter_Beyond_Toolkit_Letter.pdf"

SECTION_HEADS = {
    "The Inventory", "The Cost Assessment", "What You’re Clearing Toward",
    "Before You Begin: Identify the Specific Block",
    "The Protocol: Thirty Days, Three Phases",
    "A Note on What This Protocol Is Not",
}


class Toolkit:
    def __init__(self):
        self.parts = []
        self.toc = []
        self.n = 0
        self.prev = None
        self.task_open = False
        self.section_open = False
        self.dropcap = False
        self.head_open = False
        self.head_lines = 0

    def anchor(self):
        self.n += 1
        return f"t{self.n}"

    def close_task(self):
        if self.task_open:
            if self.head_open:
                self.parts.append("</div>")
                self.head_open = False
            self.parts.append("</div>")
            self.task_open = False

    def close_section(self):
        self.close_task()
        if self.section_open:
            self.parts.append("</section>")
            self.section_open = False

    def opener(self, label, title, rh, level, follow=False):
        self.close_section()
        a = self.anchor()
        lab = f'<div class="ch-label">{esc(label)}</div>' if label else ""
        self.parts.append(
            f'<section class="part{" follow" if follow else ""}" id="{a}"><div class="rh">{esc(rh)}</div>'
            f'<header class="opener">{lab}<h1 class="ch-title">{esc(title)}</h1>'
            f'<img class="flourish" src="../../images/flourish.png" alt=""></header>')
        self.section_open = True
        self.toc.append((level, label, title, a))
        self.prev = "opener"
        self.dropcap = True

    def h(self, level, text):
        self.close_task()
        self.parts.append(f'<h{level} class="h{level}">{esc(text)}</h{level}>')
        self.prev = f"h{level}"
        self.dropcap = False

    def prompt(self, body):
        self.close_task()
        self.parts.append(f'<div class="task"><div class="task-head"><p class="prompt">{body}</p>')
        self.task_open = True
        self.head_lines = 0
        self.head_open = True
        self.prev = "prompt"
        self.dropcap = False

    def line(self):
        # a prompt stays with its first three writing lines; further lines may
        # continue on the next page instead of leaving a gap
        if not self.task_open:
            self.parts.append('<div class="task"><div class="task-head">')
            self.task_open = True
            self.head_lines = 0
            self.head_open = True
        self.parts.append('<div class="wline"></div>')
        if self.head_open:
            self.head_lines += 1
            if self.head_lines == 3:
                self.parts.append("</div>")
                self.head_open = False
        self.prev = "line"

    def para(self, body, text, cls=None):
        self.close_task()
        classes = [cls] if cls else []
        if self.prev in ("opener", "h2", "h3", None):
            classes.append("noindent")
        if self.dropcap and re.match(r"[A-Za-z]", text):
            classes.append("dropcap")
            body = re.sub(r"^((?:<[^>]+>)*)([A-Za-z])", r'\1<span class="dc">\2</span>', body, count=1)
        self.dropcap = False
        c = f' class="{" ".join(classes)}"' if classes else ""
        self.parts.append(f"<p{c}>{body}</p>")
        self.prev = cls or "p"


def build():
    d = docx.Document(str(SRC))
    rels = d.part.rels
    paras = [c for c in d.element.body if c.tag == W + "p"]
    infos = [para_info(p, rels) for p in paras]

    tk = Toolkit()
    prev_text = ""
    for x in infos:
        text = x["text"].strip()
        if not text:
            continue                      # empty / page-break paragraphs
        body = seg_html(x["segs"])
        if x["style"] == "Heading1":
            tk.opener(None, text, text, "part")
        elif re.fullmatch(r"_+", text):
            tk.line()
        elif x["all_bold"] and (m := re.match(r"Worksheet (\d+):\s*(.*)", text)):
            # Worksheet 1 follows the one-paragraph introduction on its page
            tk.opener(f"WORKSHEET {m.group(1)}", m.group(2), text, "worksheet",
                      follow=tk.prev == "p")
        elif x["all_bold"] and text == "The 30-Day Unstuck Protocol":
            tk.opener(None, text, text, "part")
        elif x["all_bold"] and text in SECTION_HEADS:
            tk.h(2, text)
        elif x["all_bold"] and re.match(r"Days \d+–\d+:", text):
            tk.h(3, text)
        elif x["all_bold"]:
            tk.prompt(body)
        elif text.endswith("?") and (prev_text.endswith(":") or tk.prev == "quote"):
            tk.para(body, text, "quote")  # the protocol's starting-point questions
        else:
            tk.para(body, text)
        prev_text = text
    tk.close_section()

    toc = ['<section class="contents"><h1 class="back-title"><span>CONTENTS</span></h1>']
    for level, label, title, a in tk.toc:
        if level == "part":
            toc.append(f'<p class="toc-top"><a href="#{a}">{esc(title.upper())}</a></p>')
        else:
            toc.append(f'<p class="toc-entry"><a href="#{a}">Worksheet {label.split()[-1]}: {esc(title)}</a></p>')
    toc.append("</section>")

    title = '''<section class="titlepage">
<div class="tp-title">DECLUTTER<br>BEYOND</div>
<div class="tp-rule"></div>
<div class="tp-sub">The Declutter Beyond Toolkit</div>
<div class="tp-author">ALEX LEE</div>
<div class="tp-pub">PURPOSEFUL LIVING PRESS</div>
<div class="tp-copy">© Copyright 2026 - All rights reserved.</div>
</section>'''

    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(f'''<!DOCTYPE html>
<html lang="en-US"><head><meta charset="utf-8">
<title>The Declutter Beyond Toolkit</title>
<link rel="stylesheet" href="../toolkit.css">
</head><body>
{title}
{"".join(toc)}
{"".join(tk.parts)}
</body></html>''', encoding="utf-8")


def render():
    import weasyprint
    doc = weasyprint.HTML(filename=str(OUT_HTML)).render()
    doc.metadata.title = "The Declutter Beyond Toolkit"
    doc.metadata.authors = ["Alex Lee"]
    doc.write_pdf(str(OUT_PDF))
    return doc


if __name__ == "__main__":
    build()
    d = render()
    print(f"{OUT_PDF.name}: {len(d.pages)} pages")
