#!/usr/bin/env python3
"""Build the InDesign source (IDML) of "The Declutter Beyond Toolkit"
(US Letter, single-sided, for home printing).

Content comes from toolkit/output/toolkit.html; the page plan from the
approved toolkit PDF.  Same type system as the book (see build_book_idml.py).
Writing lines are empty paragraphs with a paragraph rule, so they can be
added or removed in InDesign like text.
"""
import re
import sys
from pathlib import Path

import lxml.html
import pymupdf

HERE = Path(__file__).resolve().parent
BOOK = HERE.parent
sys.path.insert(0, str(HERE))
from idml import Document, PAGE  # noqa: E402
from build_book_idml import SERIF, SANS, GOTHIC, CASLON, LSEP, THIN, runs_of  # noqa: E402

HTML = BOOK / "toolkit" / "output" / "toolkit.html"
PDF = BOOK / "toolkit" / "output" / "Declutter_Beyond_Toolkit_Letter.pdf"
OUT_DIR = BOOK / "indesign" / "Declutter_Beyond_Toolkit_InDesign"
OUT = OUT_DIR / "Declutter_Beyond_Toolkit_Letter.idml"

W, H = 612.0, 792.0
X0, X1 = 72.0, 540.0
TOP, BOTTOM = 67.8, 724.0            # body: first baseline 84.8, leading 17


def define_styles(doc):
    k80 = doc.color("K=80", (0, 0, 0, 80))
    k60 = doc.color("K=60", (0, 0, 0, 60))
    k40 = doc.color("K=40", (0, 0, 0, 40))
    black = "Color/Black"
    base = "$ID/[No paragraph style]"
    common = dict(AppliedLanguage="$ID/English: USA", FillColor=black, Composer="HL Composer",
                  KeepFirstLines=2, KeepLastLines=2, KeepLinesTogether="true", Hyphenation="false",
                  Tracking=0, Ligatures="true", KerningMethod="$ID/Metrics")
    body = dict(common, FontStyle="Regular", PointSize=12, Leading=17, Justification="LeftJustified",
                FirstLineIndent=14.4, MinimumWordSpacing=80, DesiredWordSpacing=100, MaximumWordSpacing=133,
                MinimumLetterSpacing=-2, DesiredLetterSpacing=0, MaximumLetterSpacing=2)
    ps = doc.paragraph_style
    ps("Body", base, SERIF, **body)
    ps("Body No Indent", "Body", SERIF, **dict(body, FirstLineIndent=0))
    ps("Body Drop Cap", "Body", SERIF, **dict(body, FirstLineIndent=0, DropCapCharacters=1, DropCapLines=2))
    ps("Quote", "Body", SERIF, **dict(body, Justification="LeftAlign", FirstLineIndent=0, LeftIndent=21.6,
                                      RightIndent=21.6, SpaceBefore=6, SpaceAfter=6))
    head = dict(common, Justification="LeftAlign", FirstLineIndent=0, KeepWithNext=2)
    ps("Heading 1", base, SANS, **dict(head, FontStyle="Medium", PointSize=15, Leading=18,
                                       SpaceBefore=26, SpaceAfter=8))
    ps("Heading 2", base, SANS, **dict(head, FontStyle="Black", PointSize=11.5, Leading=14,
                                       SpaceBefore=16, SpaceAfter=4))
    ps("Prompt", "Body", SERIF, **dict(body, FontStyle="Bold", Justification="LeftAlign", FirstLineIndent=0,
                                       SpaceBefore=7.8, KeepWithNext=1))
    line = dict(common, FontStyle="Regular", PointSize=12, Leading=22.6, Justification="LeftAlign",
                RuleBelow="true", RuleBelowLineWeight=0.6, RuleBelowOffset=0, RuleBelowWidth="ColumnWidth",
                RuleBelowColor=k40, RuleBelowTint=100)
    ps("Writing Line", base, SERIF, **line)
    ps("Writing Line Keep", "Writing Line", SERIF, **dict(line, KeepWithNext=1))
    ps("Part Label", base, SANS, **dict(common, FontStyle="Black", PointSize=17, Leading=20,
                                        Justification="CenterAlign", FillColor=k60, Capitalization="AllCaps",
                                        KeepWithNext=3))
    ps("Part Title", base, SANS, **dict(common, FontStyle="Book", PointSize=26, Leading=34,
                                        Justification="CenterAlign", SpaceBefore=6.5, KeepWithNext=3))
    ps("Flourish", base, SERIF, **dict(common, Justification="CenterAlign", PointSize=12, Leading=13.5,
                                       SpaceBefore=28.4, SpaceAfter=29.8, KeepWithNext=2))
    back = dict(common, FontStyle="Black", PointSize=18, Leading=22, Justification="CenterAlign",
                SpaceAfter=47.5, RuleBelow="true", RuleBelowLineWeight=0.75, RuleBelowOffset=9,
                RuleBelowWidth="TextWidth", RuleBelowColor=k60, RuleBelowTint=100)
    ps("Contents Title", base, SANS, **back)
    tab = [("RightAlign", 396, ".")]
    toc = dict(common, Justification="LeftAlign", FirstLineIndent=0)
    ps("TOC Section", base, SANS, tabs=tab, **dict(toc, FontStyle="Medium", PointSize=12, Leading=15,
                                                    SpaceBefore=12.8, SpaceAfter=8))
    ps("TOC Entry", base, SERIF, tabs=tab, **dict(toc, FontStyle="Regular", PointSize=13, Leading=18,
                                                  LeftIndent=22, SpaceAfter=6))
    ps("Book Title", base, GOTHIC, **dict(common, FontStyle="Regular", PointSize=60, Leading=72,
                                          Justification="CenterAlign", Tracking=10))
    ps("Book Subtitle", base, CASLON, **dict(common, FontStyle="Italic", PointSize=21, Leading=30,
                                             Justification="CenterAlign"))
    ps("Book Author", base, GOTHIC, **dict(common, FontStyle="Regular", PointSize=36, Leading=40,
                                           Justification="CenterAlign", Tracking=14))
    ps("Book Publisher", base, SERIF, **dict(common, FontStyle="Regular", PointSize=17, Leading=20,
                                             Justification="CenterAlign"))
    ps("Copyright Line", base, SERIF, **dict(common, FontStyle="Regular", PointSize=9.5, Leading=12,
                                             Justification="CenterAlign", FillColor=k80))
    ps("Running Head", base, SERIF, **dict(common, FontStyle="Italic", PointSize=9.5, Leading=12,
                                           Justification="RightAlign", FillColor=k80))
    ps("Folio", base, SERIF, **dict(common, FontStyle="Bold", PointSize=10, Leading=12,
                                    Justification="CenterAlign"))
    cs = doc.character_style
    cs("Bold", SERIF, FontStyle="Bold")
    cs("Italic", SERIF, FontStyle="Italic")
    cs("Bold Italic", SERIF, FontStyle="Bold Italic")
    cs("Folio", SERIF, FontStyle="Bold", PointSize=10.5, FillColor=black)


def page_plan():
    d = pymupdf.open(PDF)
    plan = []
    for i, p in enumerate(d):
        if i == 0:
            plan.append("title"); continue
        if i == 1:
            plan.append("contents"); continue
        foot = [s for b in p.get_text("dict")["blocks"] if b["type"] == 0 for l in b["lines"]
                for s in l["spans"] if s["origin"][1] > 740 and s["text"].strip()]
        plan.append("opener" if foot else "body")
    return plan


def build():
    body = lxml.html.parse(str(HTML)).getroot().find("body")
    secs = [s for s in body if s.tag == "section"]
    title_sec, contents_sec, parts = secs[0], secs[1], secs[2:]
    plan = page_plan()

    doc = Document(W, H, facing=False)
    define_styles(doc)
    for style, ps_ in (("Regular", "EBGaramond-Regular"), ("Italic", "EBGaramond-Italic"),
                       ("Bold", "EBGaramond-Bold"), ("Bold Italic", "EBGaramond-BoldItalic")):
        doc.font(SERIF, style, ps_)
    for style in ("Book", "Medium", "Black"):
        doc.font(SANS, style, "Avenir-" + style, "TrueType")
    doc.font(GOTHIC, "Regular", "LeagueGothic-Regular")
    doc.font(CASLON, "Italic", "ACaslonPro-Italic", "OpenTypeCFF")
    doc.add_variable("Worksheet Label", "Part Label")
    doc.add_variable("Part Title", "Part Title")

    def margins(side):
        return (72, 72, 72, 72)

    def frame(story, top, bottom=BOTTOM, x0=X0, x1=X1):
        rec = {"story": story.sid, "id": doc.uid("tf"), "prev": None, "next": None}

        def produce(side):
            return doc.frame_xml(side, rec["story"], rec["prev"], rec["next"], (x0, top, x1, bottom), rec["id"])
        produce.rec = rec
        return produce

    def thread(frames):
        recs = [f.rec for f in frames]
        for k, r in enumerate(recs):
            r["prev"] = recs[k - 1]["id"] if k else None
            r["next"] = recs[k + 1]["id"] if k + 1 < len(recs) else None

    def head(with_label):
        def produce(side):
            st = doc.story()
            runs = []
            if with_label:
                runs += [("", None, {"_variable": "Worksheet Label"}), (": ", None, {})]
            runs += [("", None, {"_variable": "Part Title"}),
                     (THIN * 2 + "•" + THIN * 2 + PAGE, "Folio", {})]
            st.para("Running Head", runs)
            return doc.frame_xml(side, st.sid, None, None, (X0, 36.5, X1, 52), doc.uid("tf"))
        return produce

    def foot(side):
        st = doc.story()
        st.para("Folio", [(PAGE, None, {})])
        return doc.frame_xml(side, st.sid, None, None, (X0, 748.1, X1, 764), doc.uid("tf"))

    m_ws = doc.master("A", "Worksheet", [], [head(True)])
    m_part = doc.master("B", "Part", [], [head(False)])
    m_open = doc.master("C", "Opener", [], [foot])

    pages = [doc.page() for _ in plan]
    doc.section(0, "Arabic", 1)

    # ---- title page
    p = pages[0]
    for style, text, base, lead in (("Book Title", "DECLUTTER" + LSEP + "BEYOND", 160.1, 72),
                                    ("Book Subtitle", "The Declutter Beyond Toolkit", 353.1, 30),
                                    ("Book Author", "ALEX LEE", 621.8, 40),
                                    ("Book Publisher", "PURPOSEFUL LIVING PRESS", 657.1, 20),
                                    ("Copyright Line", None, 697.7, 12)):
        if text is None:
            text = title_sec.find("./div[@class='tp-copy']").text_content().strip()
        st = doc.story()
        st.para(style, [(text, None, {})])
        p["items"].append(frame(st, base - lead, base - lead + 160))
    p["items"].append(lambda side: doc.line_xml(side, 189, 290.3, 423, 0.6, "Color/Black"))

    # ---- which part each page belongs to (a "follow" part starts on the
    # same page as the part before it, below it)
    opener_pages = [i for i, kind in enumerate(plan) if kind == "opener"]
    part_page, k = {}, 0
    for j, sec in enumerate(parts):
        if "follow" in (sec.get("class") or "") and j:
            part_page[j] = part_page[j - 1]
        else:
            part_page[j] = opener_pages[k]
            k += 1
    owner = [max((j for j in part_page if part_page[j] <= i), default=None) if i >= 2 else None
             for i in range(len(plan))]
    st = doc.story()
    st.para("Contents Title", [("CONTENTS", None, {})])
    id_index = {}
    for j, sec in enumerate(parts):
        anchor = sec.get("id")
        if anchor:
            id_index[anchor] = j
    for el in contents_sec.findall("p"):
        a_ = el.find("a")
        j = id_index[a_.get("href")[1:]]
        num = str(part_page[j] + 1)
        st.para("TOC Section" if el.get("class") == "toc-top" else "TOC Entry",
                runs_of(a_) + [("\t" + num, None, {})])
    pages[1]["items"].append(frame(st, 126.9 - 22, x0=108, x1=504))

    # ---- parts (a "follow" part continues the story of the part before it)
    stories, frames_of = {}, {}
    story_of_part = {}
    for j, sec in enumerate(parts):
        if "follow" in (sec.get("class") or "") and j:
            story_of_part[j] = story_of_part[j - 1]
        else:
            story_of_part[j] = doc.story()
            frames_of[story_of_part[j].sid] = []
    prev_style = None
    for j, sec in enumerate(parts):
        st = story_of_part[j]
        label = sec.find(".//div[@class='ch-label']")
        for el in sec.iter():
            cls = (el.get("class") or "").split()
            if el.tag == "div" and "ch-label" in cls:
                t = el.text_content().strip().title()          # "Worksheet 1", shown in caps by the style
                attrs = {"SpaceBefore": 52.3} if "follow" in (sec.get("class") or "") else {}
                st.para("Part Label", [(t, None, {})], **attrs)
                prev_style = "Part Label"
            elif el.tag == "h1" and "ch-title" in cls:
                st.para("Part Title", [(el.text_content().strip(), None, {})])
                prev_style = "Part Title"
            elif el.tag == "img" and "flourish" in cls:
                src = (BOOK / "toolkit" / "output" / el.get("src")).resolve()
                from PIL import Image
                with Image.open(src) as im:
                    pw, ph = im.size
                st.para("Flourish", [{"file": src.name, "path": src, "w": 44, "h": 13.5,
                                      "px_w": pw, "px_h": ph}])
                prev_style = "Flourish"
            elif el.tag == "h2":
                attrs = {"SpaceBefore": 0} if prev_style == "Flourish" else {}
                st.para("Heading 1", [(el.text_content().strip(), None, {})], **attrs)
                prev_style = "Heading 1"
            elif el.tag == "h3":
                st.para("Heading 2", [(el.text_content().strip(), None, {})])
                prev_style = "Heading 2"
            elif el.tag == "p" and "prompt" in cls:
                attrs = {"SpaceBefore": 0} if prev_style in ("Heading 1", "Heading 2") else \
                        {"SpaceBefore": 12} if prev_style in ("Body", "Body No Indent", "Quote") else {}
                st.para("Prompt", runs_of(el), **attrs)
                prev_style, nlines = "Prompt", 0
            elif el.tag == "div" and "wline" in cls:
                if prev_style == "Prompt":
                    nlines = 0
                nlines = nlines + 1 if prev_style in ("Writing Line", "Writing Line Keep") else 1
                style = "Writing Line Keep" if nlines < 3 else "Writing Line"
                attrs = {"SpaceBefore": 4.2} if prev_style == "Prompt" else {}
                st.para(style, [], **attrs)
                prev_style = "Writing Line Keep" if style == "Writing Line Keep" else "Writing Line"
            elif el.tag == "p" and "prompt" not in cls:
                if "dropcap" in cls:
                    style = "Body Drop Cap"
                elif "quote" in cls:
                    style = "Quote"
                elif "noindent" in cls:
                    style = "Body No Indent"
                else:
                    style = "Body"
                attrs = {}
                if style == "Quote" and prev_style == "Quote":
                    attrs["SpaceBefore"] = 0
                st.para(style, runs_of(el), **attrs)
                prev_style = style

    for i, kind in enumerate(plan):
        if i < 2:
            continue
        j = owner[i]
        st = story_of_part[j]
        sec = parts[j]
        if kind == "opener":
            top = 133.6 - 34
            pages[i]["master"] = m_open
        else:
            top = TOP
            has_label = sec.find(".//div[@class='ch-label']") is not None
            pages[i]["master"] = m_ws if has_label else m_part
        f = frame(st, top)
        frames_of[st.sid].append(f)
        pages[i]["items"].append(f)
    for frames in frames_of.values():
        thread(frames)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    doc.write(OUT, margins, "The Declutter Beyond Toolkit")
    from build_book_idml import fix_links
    fix_links(OUT_DIR / "Links")
    return doc, plan


if __name__ == "__main__":
    doc, plan = build()
    print(f"{OUT.name}: {len(plan)} pages, {len(doc.stories)} stories")
