import json
import docx
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

BASE = "/home/user/Formattazione-Ross"
main = json.load(open(f"{BASE}/master/parsed-source/main.json"))
recipes = json.load(open(f"{BASE}/master/master-recipes.json"))

mblocks = {b["i"]: b["text"] for b in main["blocks"] if b["type"] == "p"}

def mtext(i):
    return mblocks.get(i, "")

d = docx.Document()

# base style
normal = d.styles["Normal"]
normal.font.name = "Georgia"
normal.font.size = Pt(11)

def h(text, level=1):
    p = d.add_heading(text, level=level)
    return p

def para(text, bold=False, italic=False, size=11):
    p = d.add_paragraph()
    lines = text.split("\n")
    for idx, line in enumerate(lines):
        if idx > 0:
            p.add_run().add_break()
        r = p.add_run(line)
        r.bold = bold
        r.italic = italic
        r.font.size = Pt(size)
    return p

def label_para(label, value=None):
    p = d.add_paragraph()
    r = p.add_run(label if value is None else f"{label}: {value}")
    r.bold = True
    return p

def field_heading(text):
    p = d.add_paragraph()
    r = p.add_run(text)
    r.bold = True
    return p

def note(text):
    p = d.add_paragraph()
    r = p.add_run(text)
    r.italic = True
    r.font.color.rgb = docx.shared.RGBColor(0x99, 0x33, 0x00)
    return p

def pagebreak():
    d.add_page_break()

# =====================================================================
# TITLE PAGE
# =====================================================================
t = d.add_paragraph()
t.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = t.add_run("The Quick & Easy Dry Mix Pantry Cookbook")
r.bold = True
r.font.size = Pt(28)
t2 = d.add_paragraph()
t2.alignment = WD_ALIGN_PARAGRAPH.CENTER
r2 = t2.add_run("by Maggie Reeves")
r2.italic = True
r2.font.size = Pt(14)
pagebreak()

# =====================================================================
# COPYRIGHT / DISCLAIMER  (main.json blocks 2-13)
# =====================================================================
for i in range(2, 14):
    txt = mtext(i)
    if not txt:
        continue
    bold = (txt.strip() == "Disclaimer")
    para(txt, bold=bold, size=10)
pagebreak()

# =====================================================================
# FREE BONUS SECTION (blocks 20-21) -- QR image omitted per instructions
# =====================================================================
h(mtext(20), level=1)
para(mtext(21))
note("[QR CODE PLACEHOLDER — 30-Day Dry Mix Meal Plan bonus. Image withheld from this base file; will be supplied separately.]")
pagebreak()

# =====================================================================
# FOREWORD (blocks 42-59)
# =====================================================================
h(mtext(42), level=1)
for i in range(43, 60):
    txt = mtext(i)
    if not txt:
        continue
    bold = txt.strip() in ("Maggie",)
    para(txt, bold=bold)
pagebreak()

# =====================================================================
# FRONT-MATTER ESSAY 1: "What a Dry Mix Pantry Actually Is"
# (source calls this "Chapter One" — renumbered out of chapter sequence
#  here because the RECIPE chapters already use Chapter 1-6; kept as an
#  unnumbered front-matter essay so there is only one "Chapter One" in
#  the finished book. Flag this to the client if it needs revisiting.)
# =====================================================================
h(mtext(60).replace("Chapter One: ", ""), level=1)
for i in range(61, 92):
    txt = mtext(i)
    if not txt:
        continue
    style = None
    if txt.strip() in (
        "Why Homemade Always Beats Store-Bought",
        'What "Reading the Label" Should Actually Feel Like',
        "This Isn't the Basic Book You've Already Read",
        "How to Use This Book",
    ):
        h(txt, level=2)
        continue
    if txt.strip() == "Chapter Two: What You'll Actually Need":
        break
    para(txt)

pagebreak()

# =====================================================================
# FRONT-MATTER ESSAY 2: "What You'll Actually Need" (was "Chapter Two")
# =====================================================================
h("What You'll Actually Need", level=1)
sub_starts = {"The Jars", "Labels", "Measuring Tools", "A Funnel", "Storage Space", "How a Jar Becomes Dinner"}
for i in range(93, 115):
    txt = mtext(i)
    if not txt:
        continue
    if txt.strip() in sub_starts:
        h(txt, level=2)
        continue
    para(txt)
pagebreak()

# =====================================================================
# MID-BOOK REVIEW REQUEST
# =====================================================================
note("[Formatter note: place this spread near the physical midpoint of the finished, paginated book — "
     "provisionally after Chapter 3, but move once real page count is known.]")
for i in range(115, 127):
    txt = mtext(i)
    if not txt:
        continue
    bold = txt.strip() == "Maggie"
    para(txt, bold=bold)
note("[QR CODE PLACEHOLDER — Amazon review link. Image withheld from this base file.]")
pagebreak()

# =====================================================================
# RECIPE CHAPTERS
# =====================================================================
by_chapter = {}
for r in recipes:
    by_chapter.setdefault((r["chapter_num"], r["chapter"]), []).append(r)

for (num, name) in sorted(by_chapter.keys()):
    h(f"Chapter {num}: {name}", level=1)
    items = by_chapter[(num, name)]
    for r in items:
        h(f"{r['order']}. {r['title']}", level=2)
        if r["intro"]:
            para(r["intro"])
        f = r["fields"]
        if f.get("servings"):
            label_para("Servings", f["servings"])
        if f.get("serving_size"):
            label_para("Serving size", f["serving_size"])
        if f.get("yield"):
            label_para("Yield", f["yield"])
        if f.get("whats_in_jar"):
            field_heading("What's in the Jar?")
            for line in f["whats_in_jar"]:
                para(line)
        if f.get("ingredients"):
            field_heading("Ingredients")
            for line in f["ingredients"]:
                para(line)
        if f.get("what_to_add"):
            field_heading("What to Add")
            for line in f["what_to_add"]:
                para(line)
        if f.get("instructions"):
            field_heading("Instructions")
            for line in f["instructions"]:
                para(line)
        if f.get("nutrition"):
            label_para("Nutrition per serving", f["nutrition"])
        if f.get("storage"):
            label_para("Storage", f["storage"])
        d.add_paragraph()  # spacer between recipes
    pagebreak()

# =====================================================================
# CONCLUSION (blocks 130-140)
# =====================================================================
h(mtext(130).replace("Conclusion: ", ""), level=1)
for i in range(131, 141):
    txt = mtext(i)
    if not txt:
        continue
    bold = txt.strip() == "Maggie"
    para(txt, bold=bold)
note("[QR CODE PLACEHOLDER — Amazon review link, repeated in back matter. Image withheld from this base file.]")

out_path = f"{BASE}/master/Master-Manuscript-BASE-no-images.docx"
d.save(out_path)
print("saved", out_path)

# quick sanity counts
n_h1 = sum(1 for p in d.paragraphs if p.style.name == "Heading 1")
n_h2 = sum(1 for p in d.paragraphs if p.style.name == "Heading 2")
print("Heading1 count:", n_h1, "Heading2 count:", n_h2, "total paragraphs:", len(d.paragraphs))
