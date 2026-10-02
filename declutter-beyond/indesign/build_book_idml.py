#!/usr/bin/env python3
"""Build the InDesign source (IDML) of "Declutter Beyond" (6 x 9 in).

Content and structure come from output/book.html (the same source as the
approved PDF, client edits included).  The page plan (which page is an
opener, a phase divider, a blank page...) comes from the approved PDF, so the
InDesign document has the same pages, masters and section numbering.

Typography follows Book 1 ("Declutter Your Home, Calm Your Life", InDesign):
EB Garamond 12/16 body, Avenir Book/Medium/Black display, League Gothic and
Adobe Caslon Pro Italic on the title page; text 100% K, running heads 80% K,
labels 60% K, rules 40% K.
"""
import re
import sys
from pathlib import Path

import lxml.html
import pymupdf
from PIL import Image

HERE = Path(__file__).resolve().parent
BOOK = HERE.parent
sys.path.insert(0, str(HERE))
from idml import Document, PAGE  # noqa: E402

HTML = BOOK / "output" / "book.html"
PDF = BOOK / "output" / "Declutter_Beyond_Interior_6x9.pdf"
OUT_DIR = BOOK / "indesign" / "Declutter_Beyond_InDesign"
OUT = OUT_DIR / "Declutter_Beyond_Interior_6x9.idml"

SERIF, SANS, GOTHIC, CASLON = "EB Garamond", "Avenir", "League Gothic", "Adobe Caslon Pro"
W, H = 432.0, 648.0
TOP, BOTTOM = 63.0, 596.0                 # body frame (first baseline 79, 33 lines)
RECTO_X, VERSO_X = (72.0, 384.0), (50.4, 362.4)
OPENER_TOP, BACK_TOP, NOTE_TOP = 113.0, 112.7, 135.7
THIN = " "
LSEP = " "                           # InDesign forced line break


# ---------------------------------------------------------------------------
# styles
# ---------------------------------------------------------------------------
def define_styles(doc):
    k80 = doc.color("K=80", (0, 0, 0, 80))
    k60 = doc.color("K=60", (0, 0, 0, 60))
    k40 = doc.color("K=40", (0, 0, 0, 40))
    black = "Color/Black"
    base = "$ID/[No paragraph style]"
    common = dict(AppliedLanguage="$ID/English: USA", FillColor=black, Composer="HL Composer",
                  KeepFirstLines=2, KeepLastLines=2, KeepLinesTogether="true",
                  Hyphenation="false", Tracking=0, Ligatures="true", KerningMethod="$ID/Optical")

    body = dict(common, PointSize=12, FontStyle="Regular", Leading=16, Justification="LeftJustified",
                FirstLineIndent=14.4, Hyphenation="true", HyphenateWordsLongerThan=8,
                HyphenateAfterFirst=3, HyphenateBeforeLast=3, HyphenateLadderLimit=1,
                HyphenationZone=36, HyphenateCapitalizedWords="false", HyphenateLastWord="false",
                MinimumWordSpacing=80, DesiredWordSpacing=100, MaximumWordSpacing=133,
                MinimumLetterSpacing=-2, DesiredLetterSpacing=0, MaximumLetterSpacing=2,
                KerningMethod="$ID/Metrics")
    ps = doc.paragraph_style
    ps("Body", base, SERIF, **body)
    ps("Body No Indent", "Body", SERIF, **dict(body, FirstLineIndent=0))
    ps("Body Drop Cap", "Body", SERIF, **dict(body, FirstLineIndent=0, DropCapCharacters=1,
                                               DropCapLines=2, SpaceBefore=16))
    ps("Body Item", "Body", SERIF, **dict(body, FirstLineIndent=0, SpaceBefore=4))
    centered = dict(body, Justification="CenterAlign", FirstLineIndent=0, Hyphenation="false")
    ps("Centered", "Body", SERIF, **dict(centered, SpaceBefore=8, SpaceAfter=8))
    ps("Key Line", "Body", SERIF, **dict(centered, FontStyle="Italic", LeftIndent=18, RightIndent=18,
                                         SpaceBefore=10, SpaceAfter=10, BalanceRaggedLines="FullyBalanced"))
    ps("Script", "Body", SERIF, **dict(body, FontStyle="Italic", Justification="LeftAlign",
                                       FirstLineIndent=0, LeftIndent=21.6, RightIndent=21.6,
                                       Hyphenation="false", SpaceBefore=8, SpaceAfter=8))
    ps("Quote", "Script", SERIF, **dict(body, Justification="LeftAlign", FirstLineIndent=0,
                                        LeftIndent=21.6, RightIndent=21.6, Hyphenation="false",
                                        SpaceBefore=8, SpaceAfter=8))
    ps("Numbered List", "Body", SERIF, tabs=[("LeftAlign", 32.4, "")],
       **dict(body, LeftIndent=32.4, FirstLineIndent=-18, SpaceAfter=4))
    head = dict(common, Justification="LeftAlign", FirstLineIndent=0, KeepWithNext=2)
    ps("Heading 1", base, SANS, **dict(head, FontStyle="Medium", PointSize=14, Leading=16.8,
                                       SpaceBefore=24, SpaceAfter=6))
    ps("Heading 2", base, SANS, **dict(head, FontStyle="Black", PointSize=11, Leading=14,
                                       SpaceBefore=14, SpaceAfter=2.7))
    ps("Run-in Head", "Body", SERIF, **dict(head, FontStyle="Bold", PointSize=12, Leading=16,
                                            SpaceBefore=10))
    ps("Figure", base, SERIF, **dict(common, Justification="CenterAlign", PointSize=12,
                                     SpaceBefore=18, SpaceAfter=10, KeepWithNext=1))

    # chapter / section openings
    ps("Chapter Label", base, SANS, **dict(common, FontStyle="Black", PointSize=16, Leading=20,
                                           Justification="CenterAlign", FillColor=k60, KeepWithNext=3))
    ps("Chapter Title", base, SANS, **dict(common, FontStyle="Book", PointSize=22, Leading=30.4,
                                           Justification="CenterAlign", SpaceBefore=4.7, KeepWithNext=3,
                                           BalanceRaggedLines="FullyBalanced"))
    ps("Flourish", base, SERIF, **dict(common, Justification="CenterAlign", PointSize=12, Leading=11.2,
                                       SpaceBefore=26, SpaceAfter=19.3, KeepWithNext=2))
    ps("Epigraph", "Body", SERIF, **dict(centered, FontStyle="Italic", LeftIndent=18, RightIndent=18,
                                         SpaceBefore=4, SpaceAfter=10, BalanceRaggedLines="FullyBalanced"))
    back = dict(common, FontStyle="Black", PointSize=16, Leading=20, Justification="CenterAlign",
                SpaceAfter=33.7, KeepWithNext=3, RuleBelow="true", RuleBelowLineWeight=0.75,
                RuleBelowOffset=7.7, RuleBelowWidth="TextWidth", RuleBelowColor=k60, RuleBelowTint=100)
    ps("Back Title", base, SANS, **back)
    ps("Back Subtitle", base, SANS, **dict(head, FontStyle="Medium", PointSize=14, Leading=16.8,
                                           Capitalization="AllCaps", SpaceBefore=12, SpaceAfter=6))
    ps("Note Lead", "Key Line", SERIF, **dict(centered, FontStyle="Italic", LeftIndent=18, RightIndent=18,
                                              SpaceBefore=9, SpaceAfter=22, BalanceRaggedLines="FullyBalanced"))

    # phase dividers
    ps("Phase Number", base, SANS, **dict(common, FontStyle="Black", PointSize=30, Leading=36,
                                          Justification="CenterAlign", RuleBelow="true",
                                          RuleBelowLineWeight=2, RuleBelowOffset=15.1,
                                          RuleBelowWidth="ColumnWidth", RuleBelowColor=k40, RuleBelowTint=100))
    ps("Phase Name", base, SANS, **dict(common, FontStyle="Book", PointSize=28, Leading=40,
                                        Justification="CenterAlign", SpaceBefore=18.3))

    # front matter
    ps("Book Title", base, GOTHIC, **dict(common, FontStyle="Regular", PointSize=45, Leading=54,
                                          Justification="CenterAlign", Tracking=11))
    ps("Book Subtitle", base, CASLON, **dict(common, FontStyle="Italic", PointSize=16, Leading=23.2,
                                             Justification="CenterAlign"))
    ps("Book Author", base, GOTHIC, **dict(common, FontStyle="Regular", PointSize=28.3, Leading=34,
                                           Justification="CenterAlign", Tracking=14))
    ps("Book Publisher", base, SERIF, **dict(common, FontStyle="Regular", PointSize=14, Leading=17,
                                             Justification="CenterAlign"))
    ps("Copyright", base, SERIF, **dict(body, PointSize=10.5, Leading=14, FirstLineIndent=0,
                                        SpaceAfter=9, Hyphenation="false"))
    ps("Copyright Head", "Copyright", SERIF, **dict(body, PointSize=10.5, Leading=14, FirstLineIndent=0,
                                                    FontStyle="Bold", SpaceBefore=5, SpaceAfter=4,
                                                    Hyphenation="false", KeepWithNext=2))
    tab = [("RightAlign", 312, ".")]
    toc = dict(common, Justification="LeftAlign", FirstLineIndent=0)
    ps("TOC Title", "Back Title", SANS, **dict(back, SpaceAfter=52.4))
    ps("TOC Section", base, SANS, tabs=tab, **dict(toc, FontStyle="Medium", PointSize=10.5, Leading=13,
                                                    SpaceBefore=8, SpaceAfter=5))
    ps("TOC Phase", "TOC Section", SANS, tabs=tab, **dict(toc, FontStyle="Medium", PointSize=10.5,
                                                          Leading=13, SpaceBefore=8, SpaceAfter=5,
                                                          KeepWithNext=2))
    ps("TOC Entry", base, SERIF, tabs=tab, **dict(toc, FontStyle="Regular", PointSize=11, Leading=16,
                                                  LeftIndent=18, SpaceAfter=4.5))

    # running heads and folios
    ps("Running Head Verso", base, SERIF, **dict(common, FontStyle="Italic", PointSize=9, Leading=12,
                                                 Justification="LeftAlign", FillColor=k80))
    ps("Running Head Recto", "Running Head Verso", SERIF,
       **dict(common, FontStyle="Italic", PointSize=9, Leading=12, Justification="RightAlign", FillColor=k80))
    ps("Folio", base, SERIF, **dict(common, FontStyle="Bold", PointSize=10, Leading=12,
                                    Justification="CenterAlign"))

    cs = doc.character_style
    cs("Bold", SERIF, FontStyle="Bold")
    cs("Italic", SERIF, FontStyle="Italic")
    cs("Bold Italic", SERIF, FontStyle="Bold Italic")
    cs("Folio", SERIF, FontStyle="Bold", PointSize=10, FillColor=black)
    cs("TOC Phase Label", SANS, FontStyle="Black")
    return k80


# ---------------------------------------------------------------------------
# HTML -> runs
# ---------------------------------------------------------------------------
def runs_of(el, bold=False, ital=False, small=False, skip_marker=False):
    """Flatten an element's text into (text, char_style, attrs) runs."""
    out = []

    def emit(text, b, i, sm):
        if not text:
            return
        text = re.sub(r"[ \t\r\n]+", " ", text)
        style = "Bold Italic" if (b and i) else "Bold" if b else "Italic" if i else None
        attrs = {"PointSize": 10} if sm else {}
        if out and out[-1][1] == style and out[-1][2] == attrs:
            out[-1] = (out[-1][0] + text, style, attrs)
        else:
            out.append((text, style, attrs))

    def walk(node, b, i, sm):
        emit(node.text, b, i, sm)
        for ch in node:
            cls = (ch.get("class") or "").split()
            if ch.tag == "br":
                emit(LSEP, b, i, sm)
            elif ch.tag == "span" and "marker" in cls:
                emit((ch.text_content() or "") + "\t", b, i, sm)
            else:
                walk(ch, b or ch.tag == "strong", i or ch.tag == "em", sm or "note-url" in cls)
            emit(ch.tail, b, i, sm)

    walk(el, bold, ital, small)
    if out:                                           # no space around forced breaks / ends
        t, s, at = out[0]
        out[0] = (t.lstrip(" "), s, at)
        t, s, at = out[-1]
        out[-1] = (t.rstrip(" "), s, at)
    return [(t.replace(" " + LSEP, LSEP).replace(LSEP + " ", LSEP), s, at) for t, s, at in out if t]


def graphic(img, links):
    """Inline graphic description for an <img> of book.html."""
    src = (BOOK / "output" / img.get("src")).resolve()
    style = img.get("style") or ""
    m = re.search(r"width:([\d.]+)pt;height:([\d.]+)pt", style)
    if m:
        w, h = float(m.group(1)), float(m.group(2))
        if w > 309:                       # an inline graphic must be narrower than the column
            w, h = 309, h * 309 / w
    else:                                             # the flourish (sized in CSS)
        w, h = 36.5, 11.2
    name = src.name if src.name not in links or links[src.name] == src else src.parent.name + "_" + src.name
    links[name] = src
    with Image.open(src) as im:
        pw, ph = im.size
    return {"file": name, "path": src, "w": w, "h": h, "px_w": pw, "px_h": ph}


# CSS margins (top, bottom) of each block type, used to reproduce collapsed
# margins with InDesign's space before / after
SPACING = {
    "Body": (0, 0), "Body No Indent": (0, 0), "Body Item": (4, 0), "Centered": (8, 8),
    "Key Line": (10, 10), "Script": (8, 8), "Quote": (8, 8), "Heading 1": (24, 6),
    "Heading 2": (14, 2.7), "Run-in Head": (10, 0), "Figure": (18, 10), "Numbered List": (0, 4),
}
FIXED = {"Chapter Label", "Chapter Title", "Flourish", "Epigraph", "Body Drop Cap", "Back Title",
         "Back Subtitle", "Note Lead"}


def section_story(doc, sec, links):
    """Convert one <section class="chap ..."> into a story."""
    st = doc.story()
    paras = []                                         # (style, runs, attrs)
    rh = sec.find("./div[@class='rhr']")
    is_back = "back" in (sec.get("class") or "")
    is_note = "note" in (sec.get("class") or "")
    for el in sec:
        cls = (el.get("class") or "").split()
        if el.tag == "div" and "rhr" in cls:
            continue
        if el.tag == "header":                         # chapter opening
            for h in el:
                hc = (h.get("class") or "").split()
                if "ch-label" in hc:
                    paras.append(("Chapter Label", [(h.text_content().strip(), None, {})], {}))
                elif "ch-title" in hc:
                    parts = [p.strip() for p in re.split(r"<br\s*/?>", lxml.html.tostring(h, encoding="unicode"))]
                    texts = [lxml.html.fromstring(p).text_content().strip() if p.strip() else "" for p in parts]
                    texts = [t for t in texts if t]
                    runs = []
                    for k, t in enumerate(texts):
                        if k:
                            runs.append((" ", None, {}))
                        runs.append((t, None, {"NoBreak": "true"} if len(texts) > 1 else {}))
                    paras.append(("Chapter Title", runs, {}))
                elif h.tag == "img":
                    paras.append(("Flourish", [graphic(h, links)], {}))
            continue
        if el.tag == "h1" and "back-title" in cls:
            paras.append(("Back Title", [(el.text_content().strip(), None, {})], {}))
            continue
        if el.tag == "p" and "back-sub" in cls:
            # running-head source: the sub-title in title case, shown in caps by the style
            paras.append(("Back Subtitle", [(rh.text_content().strip(), None, {})], {}))
            continue
        if el.tag == "figure":
            paras.append(("Figure", [graphic(el.find(".//img"), links)],
                          {"_qr": "qr" in cls}))
            continue
        if el.tag == "ol":
            items = el.findall("li")
            for k, li in enumerate(items):
                paras.append(("Numbered List", runs_of(li),
                              {"_first": k == 0, "_last": k == len(items) - 1}))
            continue
        if el.tag in ("h2", "h3"):
            paras.append(("Heading 1" if el.tag == "h2" else "Heading 2",
                          [(el.text_content().strip(), None, {})], {}))
            continue
        if el.tag != "p":
            continue
        if "epigraph" in cls:
            style = "Epigraph"
        elif "dropcap" in cls:
            style = "Body Drop Cap"
        elif "keyline" in cls:
            style = "Note Lead" if is_note else "Key Line"
        elif "script" in cls:
            style = "Script"
        elif "quote" in cls:
            style = "Quote"
        elif "center" in cls:
            style = "Centered"
        elif "boldhead" in cls:
            style = "Run-in Head"
        elif "item" in cls:
            style = "Body Item"
        elif "noindent" in cls:
            style = "Body No Indent"
        else:
            style = "Body"
        attrs = {}
        if style == "Body Item" and is_back:
            attrs["LeftIndent"] = 14.4
        paras.append((style, runs_of(el), attrs))

    # collapsed CSS margins -> local space-before overrides where needed
    prev = None
    for style, runs, attrs in paras:
        a = {k: v for k, v in attrs.items() if not k.startswith("_")}
        if style not in FIXED and prev is not None and prev not in FIXED:
            mt, _ = SPACING.get(style, (0, 0))
            _, pmb = SPACING.get(prev, (0, 0))
            if style == "Numbered List":
                mt = 10 if attrs.get("_first") else 0
            if style == "Run-in Head" and prev in ("Heading 1", "Heading 2"):
                mt = 2
            if style == "Heading 2" and prev == "Heading 1":
                mt = 4
            if prev in ("Heading 1", "Heading 2", "Run-in Head") and style in ("Key Line", "Script", "Quote", "Centered"):
                mt = 0
            want = max(mt, pmb) - pmb
            if want != SPACING.get(style, (0, 0))[0]:
                a["SpaceBefore"] = round(want, 2)
        if style == "Numbered List" and attrs.get("_last"):
            a["SpaceAfter"] = 10
        if style == "Figure" and attrs.get("_qr"):
            a["SpaceBefore"], a["SpaceAfter"] = 16, 8
        if style == "Figure":
            a["Leading"] = runs[0]["h"]            # the line is exactly the image height
        st.para(style, runs, **a)
        prev = style
    return st


# ---------------------------------------------------------------------------
# page plan from the approved PDF
# ---------------------------------------------------------------------------
def page_plan():
    d = pymupdf.open(PDF)
    plan = []
    for i, p in enumerate(d):
        if i == 0:
            plan.append("title"); continue
        if i == 1:
            plan.append("copyright"); continue
        if i in (2, 3):
            plan.append("toc"); continue
        txt = p.get_text().strip()
        if not txt:
            plan.append("blank"); continue
        if txt.startswith("PHASE"):
            plan.append("phase"); continue
        foot = [s for b in p.get_text("dict")["blocks"] if b["type"] == 0 for l in b["lines"]
                for s in l["spans"] if s["origin"][1] > 600 and s["text"].strip()]
        plan.append("opener" if foot else "body")
    return plan


# ---------------------------------------------------------------------------
def build():
    root = lxml.html.parse(str(HTML)).getroot()
    body = root.find("body")
    sections = [s for s in body if s.tag == "section"]
    title_sec, copy_sec, toc_sec = sections[:3]
    main = sections[3:]
    plan = page_plan()

    doc = Document(W, H, facing=True)
    define_styles(doc)
    for style, ps in (("Regular", "EBGaramond-Regular"), ("Italic", "EBGaramond-Italic"),
                      ("Bold", "EBGaramond-Bold"), ("Bold Italic", "EBGaramond-BoldItalic")):
        doc.font(SERIF, style, ps)
    for style in ("Book", "Medium", "Black"):
        doc.font(SANS, style, "Avenir-" + style, "TrueType")
    doc.font(GOTHIC, "Regular", "LeagueGothic-Regular")
    doc.font(CASLON, "Italic", "ACaslonPro-Italic", "OpenTypeCFF")
    doc.add_variable("Chapter Title", "Chapter Title")
    doc.add_variable("Appendix Title", "Back Subtitle")

    def margins(side):
        return (66.7, 48, 53.3, 72) if side == "R" else (66.7, 69.6, 53.3, 50.4)

    def xs(side):
        return RECTO_X if side == "R" else VERSO_X

    def frame(story, top, bottom=BOTTOM):
        """Item producer for one text frame; threading filled in later."""
        rec = {"story": story.sid, "top": top, "bottom": bottom, "id": doc.uid("tf"), "prev": None, "next": None}

        def produce(side):
            x0, x1 = xs(side)
            return doc.frame_xml(side, rec["story"], rec["prev"], rec["next"], (x0, rec["top"], x1, rec["bottom"]),
                                 rec["id"])
        produce.rec = rec
        return produce

    def thread(frames):
        recs = [f.rec for f in frames]
        for k, r in enumerate(recs):
            r["prev"] = recs[k - 1]["id"] if k else None
            r["next"] = recs[k + 1]["id"] if k + 1 < len(recs) else None

    # ---- masters
    def head_verso(side):
        st = doc.story()
        st.para("Running Head Verso", [(PAGE + THIN * 2 + "•" + THIN * 2, "Folio", {}),
                                       ("Declutter Beyond", None, {})])
        x0, x1 = xs(side)
        return doc.frame_xml(side, st.sid, None, None, (x0, 34.1, x1, 50), doc.uid("tf"))

    def head_recto(var):
        def produce(side):
            st = doc.story()
            st.para("Running Head Recto", [("", None, {"_variable": var}),
                                           (THIN * 2 + "•" + THIN * 2 + PAGE, "Folio", {})])
            x0, x1 = xs(side)
            return doc.frame_xml(side, st.sid, None, None, (x0, 34.1, x1, 50), doc.uid("tf"))
        return produce

    def foot_folio(side):
        st = doc.story()
        st.para("Folio", [(PAGE, None, {})])
        x0, x1 = xs(side)
        return doc.frame_xml(side, st.sid, None, None, (x0, 600, x1, 616), doc.uid("tf"))

    m_body = doc.master("A", "Body", [head_verso], [head_recto("Chapter Title")])
    m_open = doc.master("B", "Opener", [foot_folio], [foot_folio])
    m_appx = doc.master("C", "Appendix", [head_verso], [head_recto("Appendix Title")])

    links = {}
    pages = [doc.page() for _ in plan]
    doc.section(0, "LowerRoman", 1)
    doc.section(4, "Arabic", 1)

    # ---- title page
    p = pages[0]
    for style, text, base, lead in (("Book Title", "DECLUTTER" + LSEP + "BEYOND", 99.7, 54),
                                    ("Book Subtitle", None, 245.7, 23.2),
                                    ("Book Author", "ALEX LEE", 530.4, 34),
                                    ("Book Publisher", "PURPOSEFUL LIVING PRESS", 560.7, 17)):
        st = doc.story()
        if text is None:
            sub = title_sec.find("./div[@class='tp-sub']")
            text = LSEP.join(t.strip() for t in sub.itertext() if t.strip())
        st.para(style, [(text, None, {})])
        p["items"].append(frame(st, base - lead, base - lead + 140))
    p["items"].append(lambda side: doc.line_xml(side, 139.8, 198.45, 316.2, 0.5, "Color/Black"))

    # ---- copyright (left page)
    st = doc.story()
    for el in copy_sec:
        st.para("Copyright Head" if "cp-head" in (el.get("class") or "") else "Copyright", runs_of(el))
    pages[1]["items"].append(frame(st, 76.4 - 14))

    # ---- TOC
    starts = {}
    sec_iter = iter(main)
    current = None
    owner = []
    for i, kind in enumerate(plan):
        if kind in ("phase", "opener"):
            current = next(sec_iter)
            starts[current.get("id")] = i
        owner.append(current if kind in ("phase", "opener", "body") else None)
    st = doc.story()
    st.para("TOC Title", [("TABLE OF CONTENTS", None, {})])
    for el in toc_sec.findall("p"):
        cls = el.get("class")
        a_ = el.find("a")
        target = a_.get("href")[1:]
        num = str(starts[target] - 3)
        runs = runs_of(a_)
        if cls == "toc-phase":
            runs = [(t, "TOC Phase Label" if s == "Bold" else None, at) for t, s, at in runs]
            st.para("TOC Phase", runs)
        else:
            st.para("TOC Section" if cls == "toc-top" else "TOC Entry", runs + [("\t" + num, None, {})])
    f1, f2 = frame(st, BACK_TOP), frame(st, 89.7 - 13)
    thread([f1, f2])
    pages[2]["items"].append(f1)
    pages[3]["items"].append(f2)
    pages[2]["master"] = pages[3]["master"] = m_open

    # ---- main matter
    sec_frames = {}
    for i, kind in enumerate(plan):
        if i < 4 or kind == "blank":
            continue
        sec = owner[i]
        sid = sec.get("id")
        cls = sec.get("class") or ""
        if kind == "phase":
            st = doc.story()
            st.para("Phase Number", [(sec.find("./div[@class='phase-num']").text_content().strip(), None, {})])
            name = sec.find("./p")
            text = LSEP.join(t.strip() for t in name.itertext() if t.strip())
            st.para("Phase Name", [(text, None, {})])
            pages[i]["items"].append(frame(st, 256.0 - 36))
            continue
        if sid not in sec_frames:
            sec_frames[sid] = (section_story(doc, sec, links), [])
        story, frames = sec_frames[sid]
        if kind == "opener":
            top = NOTE_TOP if "note" in cls else BACK_TOP if "back" in cls else OPENER_TOP
            pages[i]["master"] = m_open
        else:
            top = TOP
            appendix = any("back-sub" in (e.get("class") or "") for e in sec)
            pages[i]["master"] = m_appx if appendix else m_body
        f = frame(story, top)
        frames.append(f)
        pages[i]["items"].append(f)
    for story, frames in sec_frames.values():
        thread(frames)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    doc.write(OUT, margins, "Declutter Beyond")
    fix_links(OUT_DIR / "Links")
    return doc, plan


def fix_links(folder):
    for f in folder.glob("*.png"):
        with Image.open(f) as im:
            im.load()
            im.save(f, dpi=(72, 72))


if __name__ == "__main__":
    doc, plan = build()
    print(f"{OUT.name}: {len(plan)} pages, {len(doc.stories)} stories, {len(doc.links)} linked images")
