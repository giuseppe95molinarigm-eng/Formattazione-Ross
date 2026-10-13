"""Read the V11 PDF as lines of styled runs (shared by the EPUB builder)."""
import pymupdf


def kind(span):
    f = span["font"].split("+")[-1]
    return f, round(span["size"], 1)


def page_lines(page):
    """Lines in reading order, without running heads/folios. Each line:
    dict(y, x0, x1, size, font, runs=[(text, bold, italic)]). Spurious spaces
    produced by ligature glyphs (their box lies inside the previous glyph)
    are dropped."""
    out = []
    raw = page.get_text("rawdict")
    for b in raw["blocks"]:
        if b["type"] != 0:
            continue
        for l in b["lines"]:
            spans = [s for s in l["spans"] if s["chars"]]
            if not spans:
                continue
            y = spans[0]["origin"][1]
            if y < 60 or y > 600:
                continue
            runs = []
            prev_x1 = None
            for s in spans:
                if s["color"] == 0xFFFFFF:
                    continue
                f = s["font"].split("+")[-1]
                bold = "Bold" in f or "Black" in f
                ital = "Italic" in f
                txt = ""
                for c in s["chars"]:
                    ch = c["c"]
                    if ch == " " and prev_x1 is not None and c["bbox"][0] < prev_x1 - 0.5:
                        continue                      # ligature artefact
                    txt += ch
                    if ch != " ":
                        prev_x1 = c["bbox"][2]
                if runs and runs[-1][1] == bold and runs[-1][2] == ital and runs[-1][3] == s["size"]:
                    runs[-1] = (runs[-1][0] + txt, bold, ital, s["size"])
                else:
                    runs.append((txt, bold, ital, s["size"]))
            lig = {"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl"}
            runs = [("".join(lig.get(ch, ch) for ch in t), b_, i_, z) for t, b_, i_, z in runs]
            text = "".join(r[0] for r in runs)
            if not text.strip():
                continue
            first = next(s for s in spans if "".join(c["c"] for c in s["chars"]).strip() and s["color"] != 0xFFFFFF)
            out.append(dict(y=round(y, 1), x0=round(l["bbox"][0], 1), x1=round(l["bbox"][2], 1),
                            size=round(first["size"], 1), font=first["font"].split("+")[-1],
                            runs=runs, text=text))
    out.sort(key=lambda l: (l["y"], l["x0"]))
    # merge pieces of the same baseline (bullet glyph + text, number + tab + text)
    merged = []
    for l in out:
        if merged and abs(merged[-1]["y"] - l["y"]) < 0.6 and l["size"] < 30 and merged[-1]["size"] < 30:
            m = merged[-1]
            m["runs"] = m["runs"] + [(" ", False, False, 12)] + l["runs"]
            m["text"] = m["text"] + " " + l["text"]
            m["x1"] = l["x1"]
        else:
            merged.append(l)
    return merged
