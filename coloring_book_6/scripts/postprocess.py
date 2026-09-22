"""Turn a raw Replicate output into the production 2550x3300 print asset.

Pipeline:
    load -> grayscale -> trim to the ink bounding box -> scale the artwork to
    fit inside an inset "art box" (aspect preserved, never stretched) ->
    paste centred on a pure-white 2550x3300 canvas -> gentle level cleanup.

Two properties matter and are guaranteed by construction:

  * the final asset is EXACTLY 2550x3300 px, i.e. a true 300 PPI 8.5x11in page
    (pixel dimensions, not merely DPI metadata);
  * no line work can ever sit inside the print-safe margin or be clipped at an
    edge, because the artwork is fitted into a box inset from the trim.

Aspect ratio is reached by centring inside the canvas, never by distortion.
Because the model is driven at 4K (taller than 3300 px) the scale step is a
DOWNSCALE, which sharpens line art rather than softening it.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

RESAMPLE = {
    "LANCZOS": Image.LANCZOS,
    "BICUBIC": Image.BICUBIC,
    "BILINEAR": Image.BILINEAR,
    "NEAREST": Image.NEAREST,
}


def _ink_bbox(im: Image.Image, threshold: int) -> tuple[int, int, int, int] | None:
    arr = np.asarray(im)
    ink = arr < threshold
    if not ink.any():
        return None
    rows = np.flatnonzero(ink.any(axis=1))
    cols = np.flatnonzero(ink.any(axis=0))
    return int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1


def _clean_levels(im: Image.Image, black_point: int, white_point: int) -> Image.Image:
    """Push near-white to pure white and near-black to pure black.

    The ramp between the two points preserves antialiasing, so printed contours
    stay smooth instead of turning into jagged 1-bit stair-steps.
    """
    if white_point <= black_point:
        return im
    span = white_point - black_point
    lut = [
        0 if v <= black_point
        else 255 if v >= white_point
        else int(round((v - black_point) / span * 255))
        for v in range(256)
    ]
    return im.point(lut)


def process(raw_path: Path | str, out_path: Path | str, cfg: dict) -> dict:
    """Run the full raw -> production conversion. Returns a report dict."""
    pp = cfg["postprocess"]
    tw = int(cfg["print"]["target_width_px"])
    th = int(cfg["print"]["target_height_px"])
    ppi = int(cfg["print"]["target_ppi"])

    raw_path, out_path = Path(raw_path), Path(out_path)
    src = Image.open(raw_path)
    report: dict = {
        "source_output_dimensions": f"{src.size[0]}x{src.size[1]}",
        "source_mode": src.mode,
    }

    im = src.convert("L")

    # ── 1. trim away the empty border so the artwork itself is isolated ──
    if pp.get("autotrim_to_ink", True):
        box = _ink_bbox(im, int(pp["autotrim_threshold"]))
        if box:
            im = im.crop(box)
            report["autotrimmed"] = True
        else:
            report["autotrimmed"] = False
            report["warning"] = "no ink found in raw output"
    report["after_trim"] = f"{im.size[0]}x{im.size[1]}"

    # ── 2. fit the artwork inside the inset art box, aspect preserved ────
    margin_px = int(round(float(pp.get("art_margin_in", 0.35)) * ppi))
    box_w, box_h = tw - 2 * margin_px, th - 2 * margin_px
    aw, ah = im.size
    scale = min(box_w / aw, box_h / ah)
    new_w, new_h = max(1, int(round(aw * scale))), max(1, int(round(ah * scale)))

    report["art_box"] = f"{box_w}x{box_h}"
    report["resample_scale"] = round(scale, 4)
    report["resample_direction"] = (
        "downscale" if scale < 0.999 else ("none" if scale <= 1.001 else "upscale")
    )
    # A mild upscale of line art is visually harmless; a large one means the
    # model returned an undersized image and real detail is being invented.
    if scale > 1.25:
        report["upscale_warning"] = (
            f"artwork upscaled {scale:.2f}x — the raw output "
            f"({src.size[0]}x{src.size[1]}) is too small for true 300 PPI; "
            f"raise output_resolution in config.yaml"
        )

    filt = RESAMPLE.get(str(pp.get("resample_filter", "LANCZOS")).upper(), Image.LANCZOS)
    if (new_w, new_h) != (aw, ah):
        im = im.resize((new_w, new_h), filt)

    # ── 3. centre on a pure-white 8.5x11 canvas ──────────────────────────
    canvas = Image.new("L", (tw, th), 255)
    canvas.paste(im, ((tw - new_w) // 2, (th - new_h) // 2))
    im = canvas
    report["artwork_placed"] = f"{new_w}x{new_h}"
    report["internal_margin_px"] = {
        "left_right": (tw - new_w) // 2,
        "top_bottom": (th - new_h) // 2,
    }

    # ── 4. level cleanup ─────────────────────────────────────────────────
    im = _clean_levels(im, int(pp["black_point"]), int(pp["white_point"]))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    im.save(
        out_path,
        format="PNG",
        optimize=False,
        compress_level=int(pp.get("png_compress_level", 6)),
        dpi=(ppi, ppi),
    )
    report["final_dimensions"] = f"{tw}x{th}"
    report["final_mode"] = im.mode
    report["final_bytes"] = out_path.stat().st_size
    return report
