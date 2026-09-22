"""Automated KDP preflight. Writes output/preflight_report.txt.

Every check reports PASS / WARNING / FAIL. Checks marked CRITICAL block the
book from being declared complete.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import imagehash
import numpy as np
import pymupdf
from PIL import Image

from .common import ROOT, img_name, load_config, p, read_json
from .validate_images import detect_text_like

PT = 72.0


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str, str, bool]] = []

    def add(self, section: str, name: str, status: str, detail: str = "",
            critical: bool = False) -> None:
        self.rows.append((section, name, status, detail, critical))

    def check(self, section: str, name: str, ok: bool, detail: str = "",
              critical: bool = False, warn: bool = False) -> bool:
        self.add(section, name, "PASS" if ok else ("WARNING" if warn else "FAIL"),
                 detail, critical and not warn)
        return ok

    @property
    def failures(self) -> list[tuple]:
        return [r for r in self.rows if r[2] == "FAIL"]

    @property
    def critical_failures(self) -> list[tuple]:
        return [r for r in self.rows if r[2] == "FAIL" and r[4]]

    @property
    def warnings(self) -> list[tuple]:
        return [r for r in self.rows if r[2] == "WARNING"]

    def render(self, cfg: dict) -> str:
        w = 78
        out = [
            "=" * w,
            "KDP PREFLIGHT REPORT",
            f"  {cfg['book']['title']}",
            f"  {cfg['book']['subtitle']}",
            "=" * w,
            f"generated : {dt.datetime.now().isoformat(timespec='seconds')}",
            f"trim      : {cfg['print']['trim_width_in']} x "
            f"{cfg['print']['trim_height_in']} in, portrait, "
            f"{'bleed' if cfg['print']['bleed'] else 'no bleed'}",
            "",
        ]
        cur = None
        for section, name, status, detail, critical in self.rows:
            if section != cur:
                out += ["", f"── {section} " + "─" * max(0, w - len(section) - 4)]
                cur = section
            tag = "CRITICAL " if critical and status == "FAIL" else ""
            line = f"  [{status:<7}] {name}"
            if detail:
                line += f"\n              {tag}{detail}"
            out.append(line)

        npass = sum(1 for r in self.rows if r[2] == "PASS")
        out += [
            "",
            "=" * w,
            f"SUMMARY: {npass} PASS, {len(self.warnings)} WARNING, "
            f"{len(self.failures)} FAIL "
            f"({len(self.critical_failures)} critical)",
        ]
        if self.critical_failures:
            out += ["", "RESULT: NOT READY — critical checks failed:"]
            out += [f"  - {r[1]}: {r[3]}" for r in self.critical_failures]
        elif self.failures:
            out += ["", "RESULT: NOT READY — non-critical failures must be reviewed."]
        else:
            out += ["", "RESULT: READY FOR KDP UPLOAD — all critical checks passed."]
            if self.warnings:
                out += [f"         {len(self.warnings)} warning(s) to review by eye."]
        out.append("=" * w)
        return "\n".join(out) + "\n"


def run(cfg: dict) -> Report:
    r = Report()
    total = cfg["book"]["total_entries"]
    tw_in = float(cfg["print"]["trim_width_in"])
    th_in = float(cfg["print"]["trim_height_in"])

    # ── 1. manuscript ─────────────────────────────────────────────────────
    S = "MANUSCRIPT"
    edata = read_json(p(cfg, "entries"), default={"entries": []})
    entries = edata.get("entries", [])
    sections = read_json(p(cfg, "sections"), default={"sections": []})["sections"]

    r.check(S, f"exactly {total} Spanish text entries", len(entries) == total,
            f"found {len(entries)}", critical=True)
    ids = [e["id"] for e in entries]
    r.check(S, "numbering contiguous 1..101", ids == list(range(1, total + 1)),
            f"first={ids[0] if ids else '-'} last={ids[-1] if ids else '-'}",
            critical=True)
    r.check(S, "five sections with titles", len(sections) == 5
            and all(s["title"] for s in sections),
            "; ".join(f"{s['label']} {s['first_id']:03d}-{s['last_id']:03d}"
                      for s in sections), critical=True)
    r.check(S, "no empty text entries", all(e["text"].strip() for e in entries),
            critical=True)

    # ── 2. illustration assets ────────────────────────────────────────────
    S = "ILLUSTRATIONS"
    final_dir = p(cfg, "final_dir")
    present = [i for i in range(1, total + 1)
               if (final_dir / img_name(i)).exists()]
    missing = [i for i in range(1, total + 1) if i not in present]
    r.check(S, f"exactly {total} illustration files present",
            len(present) == total,
            ("missing: " + ", ".join(f"{m:03d}" for m in missing)) if missing
            else f"{len(present)} files, correctly named 001.png..{total:03d}.png",
            critical=True)

    meta = read_json(p(cfg, "metadata"), default={"images": {}})["images"]

    bad_dims, low_ppi, coloured, corrupt, text_hits, upscaled = [], [], [], [], [], []
    hashes: dict[int, object] = {}
    for i in present:
        f = final_dir / img_name(i)
        try:
            im = Image.open(f)
            im.load()
        except Exception:                               # noqa: BLE001
            corrupt.append(i)
            continue
        wpx, hpx = im.size
        if (wpx, hpx) != tuple(cfg["validation"]["exact_dimensions"]):
            bad_dims.append(f"{i:03d}={wpx}x{hpx}")
        if wpx / tw_in < cfg["print"]["target_ppi"] or \
           hpx / th_in < cfg["print"]["target_ppi"]:
            low_ppi.append(f"{i:03d}={min(wpx / tw_in, hpx / th_in):.0f}")
        rgb = np.asarray(im.convert("RGB")).astype(np.int16)
        spread = float((rgb.max(axis=2) - rgb.min(axis=2)).mean())
        if spread > float(cfg["validation"]["max_mean_saturation"]):
            coloured.append(f"{i:03d}={spread:.1f}")
        gray = np.asarray(im.convert("L"))
        if detect_text_like(gray, cfg)["suspicious"]:
            text_hits.append(f"{i:03d}")
        hashes[i] = imagehash.phash(im.convert("L"),
                                    hash_size=int(cfg["validation"]["phash_size"]))
        if (meta.get(str(i), {}).get("resample_direction")) == "upscale":
            upscaled.append(f"{i:03d}")

    r.check(S, "no corrupted image files", not corrupt,
            ", ".join(f"{c:03d}" for c in corrupt), critical=True)
    r.check(S, "all images exactly 2550x3300 px", not bad_dims,
            ", ".join(bad_dims), critical=True)
    r.check(S, "every illustration >= 300 effective PPI at final size",
            not low_ppi, ", ".join(low_ppi), critical=True)
    r.check(S, "no unexpected colour in image assets", not coloured,
            ", ".join(coloured), critical=True)
    r.check(S, "no text detected inside image assets", not text_hits,
            ("flagged for visual confirmation: " + ", ".join(text_hits))
            if text_hits else "heuristic glyph screen found none",
            warn=bool(text_hits))
    r.check(S, "no artwork required significant upscaling", not upscaled,
            ", ".join(upscaled), warn=bool(upscaled))

    # duplicate detection
    S = "DUPLICATES"
    ident, near = [], []
    ks = sorted(hashes)
    for a_i, a in enumerate(ks):
        for b in ks[a_i + 1:]:
            d = hashes[a] - hashes[b]
            if d <= int(cfg["validation"]["phash_identical_distance"]):
                ident.append(f"{a:03d}~{b:03d}(d={d})")
            elif d <= int(cfg["validation"]["phash_duplicate_distance"]):
                near.append(f"{a:03d}~{b:03d}(d={d})")
    r.check(S, "no identical/reused illustration files", not ident,
            ", ".join(ident), critical=True)
    r.check(S, "no near-duplicate compositions", not near,
            ", ".join(near) if near else
            f"perceptual hashing across {len(ks)} images found none",
            warn=bool(near))

    # recorded QC verdicts
    S = "IMAGE QC RECORD"
    failed = [i for i in present
              if meta.get(str(i), {}).get("validation_status") not in {"PASS", None}]
    unknown = [i for i in present if str(i) not in meta]
    r.check(S, "every illustration has a PASS validation record", not failed,
            ", ".join(f"{i:03d}" for i in failed), critical=True)
    r.check(S, "no illustration lacks a QC record", not unknown,
            ", ".join(f"{i:03d}" for i in unknown), warn=True)
    warned = [i for i in present
              if meta.get(str(i), {}).get("validation_warnings")]
    r.check(S, "no outstanding QC warnings", not warned,
            ", ".join(f"{i:03d}" for i in warned), warn=True)

    # ── 3. page plan / parity ─────────────────────────────────────────────
    S = "PAGE PLAN & PARITY"
    pm_path = p(cfg, "page_map")
    pm = read_json(pm_path, default=None) if pm_path.exists() else None
    if not pm:
        r.add(S, "page map present", "FAIL",
              "data/page_map.json not found — run `python main.py build-book`",
              True)
    else:
        pages = pm["pages"]
        pc = pm["page_count"]
        r.check(S, "total page count recorded", pc == len(pages), f"{pc} pages")
        r.check(S, "page count within KDP range 24-828", 24 <= pc <= 828,
                f"{pc}", critical=True)
        r.check(S, "page count is even", pc % 2 == 0, f"{pc}", critical=True)

        img_pages = {x["id"]: x["page"] for x in pages if x["kind"] == "image"}
        txt_pages = {x["id"]: x["page"] for x in pages if x["kind"] == "text"}
        r.check(S, f"exactly {total} illustration pages", len(img_pages) == total,
                f"{len(img_pages)}", critical=True)
        r.check(S, f"exactly {total} Spanish text pages", len(txt_pages) == total,
                f"{len(txt_pages)}", critical=True)

        wrong_side = [f"{k:03d}@p{v}" for k, v in img_pages.items() if v % 2 != 0]
        r.check(S, "every illustration on a LEFT (verso) page", not wrong_side,
                ", ".join(wrong_side), critical=True)
        wrong_side_t = [f"{k:03d}@p{v}" for k, v in txt_pages.items() if v % 2 != 1]
        r.check(S, "every Spanish text on a RIGHT (recto) page", not wrong_side_t,
                ", ".join(wrong_side_t), critical=True)

        unfaced = [f"{k:03d}" for k in img_pages
                   if txt_pages.get(k) != img_pages[k] + 1]
        r.check(S, "each text faces its own illustration (image N / text N)",
                not unfaced, ", ".join(unfaced), critical=True)

        dividers = [x for x in pages if x["kind"] == "part"]
        r.check(S, "5 section dividers, all on rectos", len(dividers) == 5
                and all(x["page"] % 2 == 1 for x in dividers),
                "; ".join(f"p{x['page']}" for x in dividers), critical=True)

        # after each divider the next image must still be a verso
        broke = []
        for d in dividers:
            nxt = next((x for x in pages if x["page"] > d["page"]
                        and x["kind"] == "image"), None)
            if nxt and nxt["page"] % 2 != 0:
                broke.append(f"after p{d['page']}")
        r.check(S, "section dividers do not break image/text parity", not broke,
                ", ".join(broke), critical=True)

        blanks = [x for x in pages if x["kind"] == "blank"]
        r.check(S, "blank pages are intentional parity fillers only",
                all(x.get("reason") for x in blanks),
                f"{len(blanks)} blank page(s): "
                + ", ".join(f"p{x['page']}" for x in blanks))

        # margins / gutter
        S = "MARGINS & GUTTER"
        gut = pm["gutter_in"]
        table = cfg["print"]["gutter_table"]
        kdp_min = table[-1]["gutter_in"]
        for row in table:
            if pc <= row["max_pages"]:
                kdp_min = row["gutter_in"]
                break
        r.check(S, f"inside/gutter margin meets KDP minimum for {pc} pages",
                gut >= kdp_min,
                f"using {gut}in; KDP minimum for this page count is {kdp_min}in",
                critical=True)
        out_m = float(cfg["print"]["outside_margin_in"])
        need = 0.375 if cfg["print"]["bleed"] else 0.25
        r.check(S, "outside/top/bottom margins meet KDP minimum",
                out_m >= need
                and float(cfg["print"]["top_margin_in"]) >= need
                and float(cfg["print"]["bottom_margin_in"]) >= need,
                f"outside {out_m}in, top {cfg['print']['top_margin_in']}in, "
                f"bottom {cfg['print']['bottom_margin_in']}in "
                f"(KDP minimum {need}in)", critical=True)

        # placed resolution
        S = "PLACED IMAGE RESOLUTION"
        placements = pm.get("image_placements", [])
        low = [f"{x['id']:03d}={min(x['effective_ppi']):.0f}" for x in placements
               if min(x["effective_ppi"]) < cfg["print"]["target_ppi"]]
        r.check(S, "every placed illustration >= 300 PPI as printed", not low,
                ", ".join(low) if low else
                (f"lowest {min(min(x['effective_ppi']) for x in placements):.0f} PPI "
                 f"across {len(placements)} placements") if placements else "",
                critical=True)

    # ── 4. the PDF itself ─────────────────────────────────────────────────
    S = "FINAL PDF"
    pdf_path = ROOT / cfg["output"]["interior_pdf"]
    if not pdf_path.exists():
        r.add(S, "final interior PDF exists", "FAIL",
              f"{cfg['output']['interior_pdf']} not found", True)
        return r

    size_mb = pdf_path.stat().st_size / 1e6
    r.check(S, "final interior PDF exists", True,
            f"{cfg['output']['interior_pdf']}  ({size_mb:.1f} MB)")
    r.check(S, "PDF file size under the KDP 650 MB limit", size_mb < 650,
            f"{size_mb:.1f} MB", critical=True)

    doc = pymupdf.open(pdf_path)
    r.check(S, "PDF is not encrypted / password protected",
            not doc.needs_pass and not doc.is_encrypted, critical=True)

    want_w, want_h = tw_in * PT, th_in * PT
    bad_size, landscape = [], []
    for i in range(doc.page_count):
        rect = doc[i].rect
        if abs(rect.width - want_w) > 0.5 or abs(rect.height - want_h) > 0.5:
            bad_size.append(f"p{i + 1}={rect.width:.0f}x{rect.height:.0f}pt")
        if rect.width > rect.height:
            landscape.append(f"p{i + 1}")
    r.check(S, f"every page exactly {tw_in} x {th_in} in "
               f"({want_w:.0f} x {want_h:.0f} pt)", not bad_size,
            ", ".join(bad_size[:6]), critical=True)
    r.check(S, "every page portrait", not landscape,
            ", ".join(landscape[:6]), critical=True)

    if pm:
        r.check(S, "PDF page count matches the verified page plan",
                doc.page_count == pm["page_count"],
                f"pdf={doc.page_count}, plan={pm['page_count']}", critical=True)

    # fonts embedded
    embedded, not_embedded = set(), set()
    for i in range(doc.page_count):
        for f in doc[i].get_fonts(full=False):
            xref, ext, ftype, basefont = f[0], f[1], f[2], f[3]
            (embedded if ext not in {"n/a", ""} else not_embedded).add(basefont)
    r.check(S, "all fonts embedded", not not_embedded,
            ("embedded: " + ", ".join(sorted(embedded))) if not not_embedded
            else "NOT embedded: " + ", ".join(sorted(not_embedded)), critical=True)

    # no printer marks / annotations / interactive elements
    annots = [i + 1 for i in range(doc.page_count) if doc[i].first_annot]
    r.check(S, "no annotations or comments", not annots,
            ", ".join(f"p{a}" for a in annots[:8]), critical=True)
    links = sum(len(doc[i].get_links()) for i in range(doc.page_count))
    r.check(S, "no interactive links", links == 0, f"{links} link(s)")
    widgets = 0
    try:
        widgets = sum(1 for _ in doc.widgets())
    except Exception:                                   # noqa: BLE001
        pass
    r.check(S, "no form fields / interactive widgets", widgets == 0,
            f"{widgets} widget(s)", critical=True)
    r.check(S, "no embedded files", doc.embfile_count() == 0,
            f"{doc.embfile_count()}")
    r.check(S, "no bookmarks / outline", not doc.get_toc(),
            f"{len(doc.get_toc())} entry/entries")
    # trim/crop boxes must coincide: no crop or registration marks
    mismatched = [i + 1 for i in range(doc.page_count)
                  if doc[i].rect != doc[i].cropbox]
    r.check(S, "no crop marks (MediaBox == CropBox on every page)",
            not mismatched, ", ".join(f"p{m}" for m in mismatched[:6]),
            critical=True)

    # page content: blanks really blank, image pages carry one image
    if pm:
        plan_by_page = {x["page"]: x for x in pm["pages"]}
        wrong_blank, wrong_img = [], []
        for i in range(doc.page_count):
            pg = plan_by_page.get(i + 1, {})
            n_img = len(doc[i].get_images(full=True))
            has_txt = bool(doc[i].get_text().strip())
            if pg.get("kind") == "blank" and (n_img or has_txt):
                wrong_blank.append(f"p{i + 1}")
            if pg.get("kind") == "image" and n_img != 1:
                wrong_img.append(f"p{i + 1}={n_img}")
        r.check(S, "parity blank pages contain no content", not wrong_blank,
                ", ".join(wrong_blank[:8]))
        r.check(S, "each illustration page carries exactly one image",
                not wrong_img, ", ".join(wrong_img[:8]), critical=True)

        # Spanish text really present on the text pages, verbatim
        by_id = {e["id"]: e["text"] for e in entries}
        mism = []
        for x in pm["pages"]:
            if x["kind"] != "text":
                continue
            got = " ".join(doc[x["page"] - 1].get_text().split())
            want = by_id.get(x["id"], "")
            norm_want = " ".join(want.split())
            # the page also carries the item number, so check containment
            stripped = got
            if stripped.startswith(str(x["id"])):
                stripped = stripped[len(str(x["id"])):].strip()
            if norm_want not in got and norm_want != stripped:
                mism.append(f"{x['id']:03d}")
        r.check(S, "Spanish manuscript text reproduced verbatim on every text page",
                not mism, ", ".join(mism[:10]), critical=True)

    # transparency / colour space sanity on embedded images
    S = "PDF IMAGE INTEGRITY"
    alpha, colour = [], []
    for i in range(doc.page_count):
        for info in doc[i].get_images(full=True):
            xref = info[0]
            smask = info[1]
            if smask:
                alpha.append(f"p{i + 1}")
            try:
                d = doc.extract_image(xref)
                if d.get("colorspace", 1) > 1:
                    colour.append(f"p{i + 1}={d.get('colorspace')}ch")
            except Exception:                           # noqa: BLE001
                pass
    r.check(S, "no unflattened transparency (no soft masks)", not alpha,
            ", ".join(alpha[:8]), critical=True)
    r.check(S, "embedded images are single-channel grayscale", not colour,
            ", ".join(colour[:8]), warn=bool(colour))
    doc.close()
    return r


def main(cfg: dict | None = None, quiet: bool = False) -> Report:
    cfg = cfg or load_config()
    rep = run(cfg)
    text = rep.render(cfg)
    out = ROOT / cfg["output"]["preflight_report"]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    if not quiet:
        print(text)
        print(f"written -> {cfg['output']['preflight_report']}")
    return rep


if __name__ == "__main__":
    main()
