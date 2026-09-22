"""Parse the Spanish .docx manuscript into data/entries.json + data/sections.json.

The manuscript is the SINGLE SOURCE OF TRUTH. Text is copied verbatim:
no rewriting, translating, shortening, expanding or correcting.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from docx import Document

from .common import ROOT, get_logger, load_config, p, write_json

log = get_logger(__name__)

NUM_RE = re.compile(r"^(\d{1,3})\.$")            # a standalone "17." marker
PART_BODY_RE = re.compile(r"^Parte\s+(\d+)\s*$")  # in-body "Parte 3"
PART_TOC_RE = re.compile(r"^Parte\s+(\d+)\s*[–\-—]\s*(.+?)\s*$")  # TOC line


def _paragraphs(docx_path: Path) -> list[str]:
    doc = Document(str(docx_path))
    return [unicodedata.normalize("NFC", par.text).strip() for par in doc.paragraphs]


def parse(cfg: dict) -> tuple[list[dict], list[dict], dict]:
    docx_path = p(cfg, "manuscript")
    if not docx_path.exists():
        raise SystemExit(f"manuscript not found: {docx_path}")

    paras = _paragraphs(docx_path)

    # ── 1. section titles come from the table-of-contents block ───────────
    toc: dict[int, str] = {}
    for line in paras:
        m = PART_TOC_RE.match(line)
        if m:
            toc.setdefault(int(m.group(1)), m.group(2).strip())

    # ── 2. walk the body: "N." marker followed by its Spanish text ────────
    entries: list[dict] = []
    current_part = 0
    pending_id: int | None = None
    front: list[str] = []
    seen_first_marker = False

    for line in paras:
        if not line:
            continue

        mb = PART_BODY_RE.match(line)
        if mb:
            current_part = int(mb.group(1))
            pending_id = None
            continue

        # TOC lines must not be mistaken for body content
        if PART_TOC_RE.match(line):
            continue

        mn = NUM_RE.match(line)
        if mn:
            pending_id = int(mn.group(1))
            seen_first_marker = True
            continue

        if pending_id is not None:
            entries.append(
                {
                    "id": pending_id,
                    "section": current_part,
                    "text": line,               # VERBATIM manuscript wording
                    "char_count": len(line),
                    "word_count": len(line.split()),
                }
            )
            pending_id = None
        elif not seen_first_marker:
            front.append(line)

    # ── 3. numbered text can spill over several paragraphs; join if so ────
    merged: dict[int, dict] = {}
    for e in entries:
        if e["id"] in merged:
            merged[e["id"]]["text"] += " " + e["text"]
            merged[e["id"]]["char_count"] = len(merged[e["id"]]["text"])
            merged[e["id"]]["word_count"] = len(merged[e["id"]]["text"].split())
            log.warning("entry %s spanned multiple paragraphs — joined", e["id"])
        else:
            merged[e["id"]] = e
    entries = [merged[k] for k in sorted(merged)]

    # ── 4. build sections with their real ranges ──────────────────────────
    sections: list[dict] = []
    for part in sorted({e["section"] for e in entries}):
        ids = [e["id"] for e in entries if e["section"] == part]
        sections.append(
            {
                "section": part,
                "label": f"Parte {part}",
                "title": toc.get(part, ""),
                "full_title": f"Parte {part} – {toc.get(part, '')}".rstrip(" –"),
                "first_id": min(ids),
                "last_id": max(ids),
                "count": len(ids),
            }
        )

    meta = {
        "source_file": docx_path.name,
        "front_matter_lines": front,
        "entry_count": len(entries),
        "section_count": len(sections),
    }
    return entries, sections, meta


def verify(entries: list[dict], sections: list[dict], cfg: dict) -> list[str]:
    """Structural checks. Returns a list of problems (empty == all good)."""
    problems: list[str] = []
    expected_total = cfg["book"]["total_entries"]

    if len(entries) != expected_total:
        problems.append(f"expected {expected_total} entries, found {len(entries)}")

    ids = [e["id"] for e in entries]
    if ids != list(range(1, len(ids) + 1)):
        missing = sorted(set(range(1, expected_total + 1)) - set(ids))
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if missing:
            problems.append(f"missing ids: {missing}")
        if dupes:
            problems.append(f"duplicate ids: {dupes}")

    if len(sections) != 5:
        problems.append(f"expected 5 sections, found {len(sections)}")

    for s in sections:
        if not s["title"]:
            problems.append(f"section {s['section']} has no title in the TOC block")

    for e in entries:
        if not e["text"]:
            problems.append(f"entry {e['id']} has empty text")

    # sections must tile 1..101 with no gap or overlap
    cursor = 1
    for s in sections:
        if s["first_id"] != cursor:
            problems.append(
                f"section {s['section']} starts at {s['first_id']}, expected {cursor}"
            )
        cursor = s["last_id"] + 1
    if cursor - 1 != len(entries):
        problems.append(f"sections end at {cursor - 1}, expected {len(entries)}")

    return problems


def main(cfg: dict | None = None, quiet: bool = False) -> dict:
    cfg = cfg or load_config()
    entries, sections, meta = parse(cfg)
    problems = verify(entries, sections, cfg)

    write_json(p(cfg, "entries"), {"meta": meta, "entries": entries})
    write_json(p(cfg, "sections"), {"sections": sections})

    if not quiet:
        print(f"parsed {len(entries)} entries from {meta['source_file']}")
        print(f"{'part':<6}{'range':<12}{'n':<5}title")
        print("-" * 68)
        for s in sections:
            rng = f"{s['first_id']:03d}-{s['last_id']:03d}"
            print(f"{s['section']:<6}{rng:<12}{s['count']:<5}{s['title']}")
        print("-" * 68)
        if problems:
            print("\nPROBLEMS:")
            for pr in problems:
                print(f"  FAIL  {pr}")
        else:
            print("\nstructure OK: 101 entries, 5 sections, contiguous numbering")

    return {"entries": entries, "sections": sections, "problems": problems}


if __name__ == "__main__":
    main()
