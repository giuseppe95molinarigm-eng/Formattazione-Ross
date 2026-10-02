#!/usr/bin/env python3
"""Structural checks for a generated IDML package.

- zip layout: `mimetype` first and stored uncompressed
- every XML part well-formed
- every reference resolves: stories, threaded frames, paragraph/character
  styles, swatches, masters, text variables, sections, StoryList
- text frames thread in both directions consistently
"""
import re
import sys
import zipfile
from lxml import etree


def check(path):
    errors = []
    z = zipfile.ZipFile(path)
    infos = z.infolist()
    if infos[0].filename != "mimetype" or infos[0].compress_type != zipfile.ZIP_STORED:
        errors.append("mimetype must be the first entry, stored")
    if z.read("mimetype") != b"application/vnd.adobe.indesign-idml-package":
        errors.append("bad mimetype")

    trees = {}
    for i in infos:
        if i.filename.endswith(".xml"):
            try:
                trees[i.filename] = etree.fromstring(z.read(i.filename))
            except etree.XMLSyntaxError as e:
                errors.append(f"{i.filename}: {e}")
    if errors:
        return errors

    dm = trees["designmap.xml"]
    ns = "{http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging}"
    for el in dm.iter():
        if el.tag.startswith(ns) and el.get("src") and el.get("src") not in trees:
            errors.append(f"designmap refers to missing {el.get('src')}")

    def all_selfs(tag):
        return {e.get("Self") for t in trees.values() for e in t.iter(tag)}

    pstyles = all_selfs("ParagraphStyle")
    cstyles = all_selfs("CharacterStyle")
    swatches = all_selfs("Color") | all_selfs("Swatch") | all_selfs("Tint") | all_selfs("Gradient")
    stories = {e.get("Self") for t in trees.values() for e in t.iter("Story", "XmlStory")}
    frames = {e.get("Self"): e for t in trees.values() for e in t.iter("TextFrame")}
    masters = all_selfs("MasterSpread")
    pages = all_selfs("Page")
    variables = all_selfs("TextVariable")

    story_list = set(dm.get("StoryList").split())
    if story_list != stories:
        errors.append(f"StoryList mismatch: missing {stories - story_list}, extra {story_list - stories}")

    for t in trees.values():
        for e in t.iter("ParagraphStyleRange"):
            if e.get("AppliedParagraphStyle") not in pstyles:
                errors.append(f"unknown paragraph style {e.get('AppliedParagraphStyle')}")
        for e in t.iter("CharacterStyleRange"):
            if e.get("AppliedCharacterStyle") not in cstyles:
                errors.append(f"unknown character style {e.get('AppliedCharacterStyle')}")
        for e in t.iter():
            for key in ("FillColor", "StrokeColor"):
                v = e.get(key)
                if v and v not in swatches:
                    errors.append(f"unknown swatch {v} on {e.tag}")
            if e.tag == "Page" and e.get("AppliedMaster") not in masters | {"n"}:
                errors.append(f"unknown master {e.get('AppliedMaster')}")
            if e.tag == "TextVariableInstance" and e.get("AssociatedTextVariable") not in variables:
                errors.append(f"unknown variable {e.get('AssociatedTextVariable')}")
            if e.tag == "Section" and e.get("PageStart") not in pages:
                errors.append(f"section starts on unknown page {e.get('PageStart')}")
            for sub in ("RuleBelowColor", "RuleAboveColor"):
                if e.tag == sub and e.get("type") == "object" and e.text not in swatches:
                    errors.append(f"unknown rule colour {e.text}")
    for fid, f in frames.items():
        if f.get("ParentStory") not in stories:
            errors.append(f"frame {fid}: unknown story {f.get('ParentStory')}")
        for key, back in (("NextTextFrame", "PreviousTextFrame"), ("PreviousTextFrame", "NextTextFrame")):
            other = f.get(key)
            if other != "n":
                if other not in frames:
                    errors.append(f"frame {fid}: {key} {other} missing")
                elif frames[other].get(back) != fid:
                    errors.append(f"frame {fid}: thread not reciprocal")
                elif frames[other].get("ParentStory") != f.get("ParentStory"):
                    errors.append(f"frame {fid}: threaded to another story")
    # every story is shown in at least one frame (except the backing story)
    shown = {f.get("ParentStory") for f in frames.values()}
    for s in stories - shown:
        if not s.startswith("uBacking"):
            errors.append(f"story {s} has no frame")
    selfs = [e.get("Self") for t in trees.values() for e in t.iter() if e.get("Self")]
    dup = {s for s in selfs if selfs.count(s) > 1} if len(selfs) < 20000 else set()
    if dup:
        errors.append(f"duplicate Self ids: {sorted(dup)[:10]}")
    n_pages = len([1 for t in trees.values() for e in t.iter("Page") if t.tag.endswith("Spread") and "Master" not in t.tag])
    return errors, n_pages, len(stories), len(frames)


if __name__ == "__main__":
    res = check(sys.argv[1])
    if isinstance(res, list):
        print("\n".join(res)); sys.exit(1)
    errors, n_pages, n_st, n_fr = res
    print(f"pages {n_pages}, stories {n_st}, text frames {n_fr}")
    print("\n".join(errors) if errors else "no structural errors")
    sys.exit(1 if errors else 0)
