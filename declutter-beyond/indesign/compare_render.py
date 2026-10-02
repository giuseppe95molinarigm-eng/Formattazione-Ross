#!/usr/bin/env python3
"""Compare the text of a rendering of the IDML (e.g. from Scribus) with the
approved PDF, page range by page range: reports text missing from the
rendering (overset) and where each section starts."""
import difflib
import re
import sys

import pymupdf


def words(pdf, skip_heads=True):
    d = pymupdf.open(pdf)
    out = []                     # (word, page)
    for i, p in enumerate(d):
        lines = []
        for b in p.get_text("dict")["blocks"]:
            if b["type"] != 0:
                continue
            for l in b["lines"]:
                y = l["spans"][0]["origin"][1]
                if skip_heads and (y < 60 or y > 600):
                    continue
                lines.append((y, l["spans"][0]["bbox"][0], "".join(s["text"] for s in l["spans"])))
        txt = "\n".join(t for _, _, t in sorted(lines))
        txt = re.sub(r"(\w)[-‐­]\n(\w)", r"\1\2", txt)
        txt = txt.replace("​", "").replace(" ", " ")
        for w in re.findall(r"[A-Za-z0-9’']+", txt):
            out.append((w.lower().replace("’", "'"), i + 1))
    return out


ref, ren = words(sys.argv[1]), words(sys.argv[2])
sm = difflib.SequenceMatcher(None, [w for w, _ in ref], [w for w, _ in ren], autojunk=False)
missing = extra = 0
for tag, a1, a2, b1, b2 in sm.get_opcodes():
    if tag == "equal":
        continue
    if a2 - a1 > 0:
        missing += a2 - a1
    if b2 - b1 > 0:
        extra += b2 - b1
    if (a2 - a1) + (b2 - b1) > 2:
        print(f"{tag}: approved p.{ref[a1][1] if a1 < len(ref) else '-'} "
              f"[{' '.join(w for w, _ in ref[a1:a2])[:90]}]  render p.{ren[b1][1] if b1 < len(ren) else '-'} "
              f"[{' '.join(w for w, _ in ren[b1:b2])[:90]}]")
print(f"approved words {len(ref)}, rendered words {len(ren)}, missing {missing}, extra {extra}")
