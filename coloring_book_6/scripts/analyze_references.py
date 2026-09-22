"""Measure the collection's visual language from the previous book's artwork.

Produces data/reference_style_analysis.json: objective targets (ink coverage,
internal margins, line-weight distribution, neutrality) that the validator then
uses to keep the new book inside the same visual envelope.
"""
from __future__ import annotations

import glob
from pathlib import Path

import numpy as np
from PIL import Image

from .common import ROOT, load_config, p, write_json


def _stroke_widths(ink: np.ndarray, samples: int = 400) -> dict:
    """Approximate line weight via horizontal run-lengths of ink."""
    runs: list[int] = []
    h = ink.shape[0]
    rows = np.linspace(0, h - 1, samples).astype(int)
    for r in rows:
        row = ink[r]
        if not row.any():
            continue
        # run-length encode the True stretches
        d = np.diff(row.astype(np.int8))
        starts = np.flatnonzero(d == 1) + 1
        ends = np.flatnonzero(d == -1) + 1
        if row[0]:
            starts = np.r_[0, starts]
        if row[-1]:
            ends = np.r_[ends, len(row)]
        n = min(len(starts), len(ends))
        runs.extend((ends[:n] - starts[:n]).tolist())
    runs = [r for r in runs if 0 < r <= 120]  # ignore filled blobs
    if not runs:
        return {}
    a = np.array(runs)
    return {
        "median_px": float(np.median(a)),
        "p10_px": float(np.percentile(a, 10)),
        "p90_px": float(np.percentile(a, 90)),
        "mean_px": round(float(a.mean()), 2),
    }


def analyze_one(path: Path) -> dict:
    im = Image.open(path)
    w, h = im.size
    rgb = im.convert("RGB")
    arr = np.asarray(rgb).astype(np.int16)
    gray = np.asarray(im.convert("L"))

    # colour neutrality: mean spread between channels
    chan_spread = float((arr.max(axis=2) - arr.min(axis=2)).mean())

    ink = gray < 128
    white = gray >= 244
    mid = (gray >= 60) & (gray < 244)  # true grey => shading (should be tiny)

    rows = np.flatnonzero(ink.any(axis=1))
    cols = np.flatnonzero(ink.any(axis=0))
    bbox = (
        {
            "top_px": int(rows[0]),
            "bottom_px": int(h - 1 - rows[-1]),
            "left_px": int(cols[0]),
            "right_px": int(w - 1 - cols[-1]),
        }
        if len(rows) and len(cols)
        else {}
    )

    return {
        "file": path.name,
        "width": w,
        "height": h,
        "aspect": round(w / h, 5),
        "ppi_at_8_5in": round(w / 8.5, 1),
        "ink_fraction": round(float(ink.mean()), 5),
        "white_fraction": round(float(white.mean()), 5),
        "midtone_fraction": round(float(mid.mean()), 5),
        "channel_spread": round(chan_spread, 3),
        "contrast_range": int(gray.max() - gray.min()),
        "ink_bbox_margins": bbox,
        "stroke_width": _stroke_widths(ink),
    }


def main(cfg: dict | None = None, quiet: bool = False) -> dict:
    cfg = cfg or load_config()
    ref_dir = ROOT / "references" / "reference_images"
    files = sorted(
        f
        for f in ref_dir.glob("*.png")
        if "_thumb" not in f.name
    )
    if not files:
        raise SystemExit(f"no reference PNGs in {ref_dir}")

    per_image = [analyze_one(f) for f in files]

    # Text-only pages (rasterised type in the previous book) sit in a narrow
    # central band; artwork pages fill most of the canvas. Separate them so the
    # style envelope is measured from ARTWORK only.
    def is_art(d: dict) -> bool:
        m = d.get("ink_bbox_margins") or {}
        if not m:
            return False
        return m["top_px"] < 600 and m["bottom_px"] < 600

    art = [d for d in per_image if is_art(d)]
    text_pages = [d for d in per_image if not is_art(d)]

    def band(vals: list[float]) -> dict:
        a = np.array(vals, dtype=float)
        return {
            "min": round(float(a.min()), 5),
            "max": round(float(a.max()), 5),
            "mean": round(float(a.mean()), 5),
        }

    envelope = {
        "artwork_sample_count": len(art),
        "text_page_sample_count": len(text_pages),
        "native_dimensions": sorted({(d["width"], d["height"]) for d in art}),
        "ink_fraction": band([d["ink_fraction"] for d in art]),
        "white_fraction": band([d["white_fraction"] for d in art]),
        "midtone_fraction": band([d["midtone_fraction"] for d in art]),
        "channel_spread": band([d["channel_spread"] for d in art]),
        "internal_margin_px": {
            k: band([d["ink_bbox_margins"][k] for d in art])
            for k in ("top_px", "bottom_px", "left_px", "right_px")
        },
        "primary_contour_px": band(
            [d["stroke_width"]["p90_px"] for d in art if d.get("stroke_width")]
        ),
        "interior_detail_px": band(
            [d["stroke_width"]["median_px"] for d in art if d.get("stroke_width")]
        ),
    }

    observed = {
        "style_notes": [
            "Pure black line art on pure white; no colour, no grey shading.",
            "Thick, confident primary contours; thinner interior detail lines.",
            "Large closed areas sized for a 6-year-old's crayon.",
            "Background filled with simple star / dot / 4-point-sparkle confetti.",
            "Protagonist wears a t-shirt with a single five-point star emblem.",
            "Concept 'insets' drawn as a plain circular vignette, never a label.",
            "Supporting props may carry simple cute faces (tooth, teddy bear).",
            "Clocks/rulers show tick marks only — never numerals.",
            "Subject reads instantly at arm's length; one clear focal action.",
        ],
        "confirmed_no_written_language": True,
        "trim_native_px": [2550, 3300],
    }

    out = {
        "envelope": envelope,
        "observed": observed,
        "per_image": per_image,
    }
    write_json(p(cfg, "style_analysis"), out)

    if not quiet:
        e = envelope
        print(f"analysed {len(files)} reference pages "
              f"({len(art)} artwork, {len(text_pages)} text)")
        print(f"native size        : {e['native_dimensions']}")
        print(f"ink fraction       : {e['ink_fraction']['min']:.3f} – "
              f"{e['ink_fraction']['max']:.3f} (mean {e['ink_fraction']['mean']:.3f})")
        print(f"white fraction     : {e['white_fraction']['min']:.3f} – "
              f"{e['white_fraction']['max']:.3f}")
        print(f"grey/midtone       : mean {e['midtone_fraction']['mean']:.4f} "
              f"(near-zero == no shading)")
        print(f"channel spread     : mean {e['channel_spread']['mean']:.2f} "
              f"(0 == perfectly neutral)")
        m = e["internal_margin_px"]
        print(f"internal margins px: top {m['top_px']['mean']:.0f}  "
              f"bottom {m['bottom_px']['mean']:.0f}  "
              f"left {m['left_px']['mean']:.0f}  right {m['right_px']['mean']:.0f}")
        print(f"primary contour px : {e['primary_contour_px']['mean']:.1f}")
        print(f"interior detail px : {e['interior_detail_px']['mean']:.1f}")

    return out


if __name__ == "__main__":
    main()
