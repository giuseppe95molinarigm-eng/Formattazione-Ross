"""Automated QC for every production illustration.

Two layers:
  1. deterministic pixel checks (dimensions, orientation, aspect, whiteness,
     neutrality, contrast, safe margins, edge clipping, duplicate hashing)
  2. a heuristic TEXT DETECTOR that looks for the signature of stray glyphs —
     rows of small, similarly-sized, evenly-baselined ink blobs.

Layer 2 is a screening aid, not a substitute for the human batch review: the
contact sheet exists precisely so a person confirms scene relevance, anatomy
and style. Anything suspicious is raised as a WARNING so it reaches the eye.
"""
from __future__ import annotations

from pathlib import Path

import imagehash
import numpy as np
from PIL import Image
from scipy import ndimage

from .common import ROOT, img_name, load_config, p, read_json, write_json


# ── layer 2: stray-glyph screening ────────────────────────────────────────
def detect_text_like(gray: np.ndarray, cfg: dict) -> dict:
    """Look for clusters of ink blobs sharing a baseline AND tightly spaced.

    Calibrated against the previous book's real pages. The decisive signal is
    the mean centre-to-centre gap divided by the mean glyph height:

        rendered text  : 0.8 – 1.3   (letters nearly touch)
        star/dot confetti and line-art detail : 5.6 – 11.9  (widely scattered)

    Height consistency alone is not enough, because the collection's confetti
    stars are also uniform in size — it is the tight spacing that betrays type.
    """
    h, w = gray.shape
    ink = gray < 128
    labels, n = ndimage.label(ink)
    if n == 0:
        return {"suspicious": False, "clusters": [], "blob_count": 0,
                "glyph_sized_blobs": 0}

    objs = ndimage.find_objects(labels)
    # glyph-sized blobs: 0.35%-12% of page height, so both body copy and large
    # display type are caught (the reference title page runs to 6.7%).
    lo, hi = 0.0035 * h, 0.12 * h
    glyphs = []
    for sl in objs:
        bh = sl[0].stop - sl[0].start
        bw = sl[1].stop - sl[1].start
        if lo <= bh <= hi and lo * 0.25 <= bw <= hi * 1.8:
            ar = bw / max(bh, 1)
            if 0.10 <= ar <= 3.5:
                glyphs.append(
                    {
                        "cx": (sl[1].start + sl[1].stop) / 2,
                        "h": bh,
                        "w": bw,
                        "bottom": sl[0].stop,
                    }
                )

    # group blobs by shared baseline (bottom edge within a small tolerance)
    tol = max(4.0, 0.006 * h)
    clusters: list[list[dict]] = []
    for g in sorted(glyphs, key=lambda d: d["bottom"]):
        for c in clusters:
            if abs(c[0]["bottom"] - g["bottom"]) <= tol:
                c.append(g)
                break
        else:
            clusters.append([g])

    hits = []
    for c in clusters:
        if len(c) < 5:                      # a "word" needs several glyphs
            continue
        c = sorted(c, key=lambda d: d["cx"])
        heights = np.array([g["h"] for g in c], dtype=float)
        gaps = np.diff([g["cx"] for g in c])
        if len(gaps) == 0 or heights.mean() <= 0:
            continue
        h_cv = float(heights.std() / heights.mean())
        g_cv = float(gaps.std() / max(gaps.mean(), 1e-9))
        gap_over_h = float(gaps.mean() / heights.mean())
        span = c[-1]["cx"] - c[0]["cx"]

        if (
            h_cv < 0.35                     # letters on a line share a height
            and 0.45 <= gap_over_h <= 2.2   # and sit tightly together
            and span > 0.06 * w             # over a meaningful run
        ):
            hits.append(
                {
                    "glyphs": len(c),
                    "baseline_y": int(c[0]["bottom"]),
                    "x_span_px": int(span),
                    "height_cv": round(h_cv, 3),
                    "gap_cv": round(g_cv, 3),
                    "gap_over_height": round(gap_over_h, 2),
                }
            )

    return {
        "suspicious": bool(hits),
        "clusters": sorted(hits, key=lambda d: -d["glyphs"])[:6],
        "blob_count": int(n),
        "glyph_sized_blobs": len(glyphs),
    }


def detect_anatomy_risk(gray: np.ndarray, max_side: int = 900) -> dict:
    """Very coarse structural screen: count large separate figure masses.

    Many large disconnected masses can indicate duplicated or detached limbs.
    Reported as information for the reviewer, never an automatic rejection.

    The morphology runs on a downsampled copy: at 8.4 megapixels the closing
    would dominate the whole validation pass, and this check only needs
    page-scale structure, not pixel detail.
    """
    h, w = gray.shape
    step = max(1, int(np.ceil(max(h, w) / max_side)))
    small = gray[::step, ::step]
    sh, sw = small.shape

    ink = small < 128
    filled = ndimage.binary_fill_holes(ndimage.binary_closing(ink, np.ones((3, 3))))
    labels, n = ndimage.label(filled)
    if n == 0:
        return {"large_masses": 0, "areas_pct": [], "downsample_step": step}
    sizes = ndimage.sum(filled, labels, range(1, n + 1))
    total = sh * sw
    big = sorted((s / total * 100 for s in sizes if s / total > 0.004), reverse=True)
    return {
        "large_masses": len(big),
        "areas_pct": [round(float(x), 2) for x in big[:8]],
        "downsample_step": step,
    }


# ── layer 1: deterministic checks ─────────────────────────────────────────
def validate_one(
    entry_id: int, path: Path | str, cfg: dict, record: dict | None = None
) -> dict:
    v = cfg["validation"]
    path = Path(path)
    failures: list[str] = []
    warnings: list[str] = []
    stats: dict = {}

    # 7. valid image file
    try:
        with Image.open(path) as probe:
            probe.verify()
        im = Image.open(path)
        im.load()
    except Exception as exc:                            # noqa: BLE001
        return {
            "id": entry_id,
            "status": "FAIL",
            "failures": [f"unreadable/corrupt image file: {type(exc).__name__}"],
            "warnings": [],
            "stats": {},
        }

    # 10/11. filename matches the required id
    if path.name != img_name(entry_id):
        failures.append(f"filename {path.name} != required {img_name(entry_id)}")

    w, h = im.size
    stats["dimensions"] = f"{w}x{h}"

    # 1. exact pixel dimensions
    ew, eh = v["exact_dimensions"]
    if (w, h) != (ew, eh):
        failures.append(f"dimensions {w}x{h} != required {ew}x{eh}")

    # 2. portrait orientation
    if v.get("require_portrait", True) and h <= w:
        failures.append(f"not portrait ({w}x{h})")

    # 3. aspect ratio
    aspect = w / h
    want = cfg["print"]["trim_width_in"] / cfg["print"]["trim_height_in"]
    stats["aspect"] = round(aspect, 5)
    if abs(aspect - want) > float(v["aspect_tolerance"]):
        failures.append(f"aspect {aspect:.4f} != {want:.4f} "
                        f"(tolerance {v['aspect_tolerance']})")

    # effective print resolution (never trust DPI metadata alone)
    eff_x = w / cfg["print"]["trim_width_in"]
    eff_y = h / cfg["print"]["trim_height_in"]
    stats["effective_ppi"] = [round(eff_x, 1), round(eff_y, 1)]
    if min(eff_x, eff_y) < cfg["print"]["target_ppi"]:
        failures.append(f"effective resolution {min(eff_x, eff_y):.0f} PPI "
                        f"< {cfg['print']['target_ppi']} PPI at final size")

    # 5. no unexpected colour.
    # A single-channel image has zero channel spread by definition, so the
    # expensive RGB expansion is skipped for the grayscale production assets.
    if im.mode in {"L", "1", "LA"}:
        spread = 0.0
    else:
        rgb = np.asarray(im.convert("RGB"))[::4, ::4].astype(np.int16)
        spread = float((rgb.max(axis=2) - rgb.min(axis=2)).mean())
    stats["channel_spread"] = round(spread, 3)
    if spread > float(v["max_mean_saturation"]):
        failures.append(f"unexpected colour: mean channel spread {spread:.2f} "
                        f"> {v['max_mean_saturation']}")
    if im.mode not in {"L", "1", "LA"}:
        warnings.append(f"image mode is {im.mode}; grayscale 'L' is preferred")

    gray = np.asarray(im.convert("L"))

    # 4. mostly white background
    white_frac = float((gray >= 244).mean())
    ink_frac = float((gray < 128).mean())
    stats["white_fraction"] = round(white_frac, 4)
    stats["ink_fraction"] = round(ink_frac, 4)
    if white_frac < float(v["min_white_fraction"]):
        failures.append(f"background not white enough ({white_frac:.3f} < "
                        f"{v['min_white_fraction']})")
    if white_frac > float(v["max_white_fraction"]):
        failures.append(f"image is effectively blank (white {white_frac:.4f} > "
                        f"{v['max_white_fraction']})")
    if ink_frac < float(v["min_ink_fraction"]):
        failures.append(f"too little line work (ink {ink_frac:.4f} < "
                        f"{v['min_ink_fraction']})")
    if ink_frac > float(v["max_ink_fraction"]):
        failures.append(f"too much ink / dark background (ink {ink_frac:.4f} > "
                        f"{v['max_ink_fraction']})")

    # 6. sufficient black/white contrast
    g_min, g_max = int(gray.min()), int(gray.max())
    rng = g_max - g_min
    stats["contrast_range"] = rng
    if rng < int(v["min_contrast_range"]):
        failures.append(f"insufficient contrast (range {rng} < "
                        f"{v['min_contrast_range']})")

    # midtone share: catches greyscale shading creeping in
    mid = float(((gray >= 60) & (gray < 244)).mean())
    stats["midtone_fraction"] = round(mid, 4)
    if mid > 0.14:
        warnings.append(f"high midtone share ({mid:.3f}) — check for grey shading")

    # 8. safe print margins: no ink in the outer frame
    band = int(round(float(v["safe_margin_in"]) * cfg["print"]["target_ppi"]))
    if band * 2 < min(w, h):
        frame = np.ones_like(gray, dtype=bool)
        frame[band:h - band, band:w - band] = False
        frame_ink = float((gray < 128)[frame].mean())
        stats["safe_margin_ink"] = round(frame_ink, 5)
        if frame_ink > 0.0:
            failures.append(f"line work inside the {v['safe_margin_in']}in safe "
                            f"margin ({frame_ink * 100:.3f}% of the frame band)")

    # 9. no obvious clipping at the canvas edge
    eb = int(v["edge_clip_band_px"])
    edges = {
        "top": gray[:eb, :], "bottom": gray[-eb:, :],
        "left": gray[:, :eb], "right": gray[:, -eb:],
    }
    clipped = {k: round(float((a < 128).mean()), 5) for k, a in edges.items()}
    stats["edge_ink"] = clipped
    hot = [k for k, val in clipped.items() if val > float(v["edge_clip_max_ink"])]
    if hot:
        failures.append(f"artwork appears clipped at the {', '.join(hot)} edge(s)")

    # perceptual hash for duplicate detection
    ph = imagehash.phash(im.convert("L"), hash_size=int(v["phash_size"]))
    stats["phash"] = str(ph)

    # layer 2 screening
    text = detect_text_like(gray, cfg)
    stats["text_screen"] = text
    if text["suspicious"]:
        biggest = text["clusters"][0]
        warnings.append(
            f"POSSIBLE TEXT: {biggest['glyphs']} glyph-like blobs on a shared "
            f"baseline at y={biggest['baseline_y']} — inspect this image closely"
        )

    ana = detect_anatomy_risk(gray)
    stats["structure"] = ana
    if ana["large_masses"] > 6:
        warnings.append(f"{ana['large_masses']} separate large masses — check for "
                        f"detached or duplicated limbs")

    status = "FAIL" if failures else ("WARNING" if warnings else "PASS")
    # Warnings must not block the pipeline; only hard failures do.
    if status == "WARNING":
        status = "PASS"

    return {
        "id": entry_id,
        "status": status,
        "failures": failures,
        "warnings": warnings,
        "stats": stats,
    }


# ── 12. duplicate detection across the whole set ──────────────────────────
def check_duplicates(results: dict[int, dict], cfg: dict) -> list[dict]:
    v = cfg["validation"]
    hashes = {
        i: imagehash.hex_to_hash(r["stats"]["phash"])
        for i, r in results.items()
        if r.get("stats", {}).get("phash")
    }
    flags: list[dict] = []
    ids = sorted(hashes)
    for a_i, a in enumerate(ids):
        for b in ids[a_i + 1:]:
            d = hashes[a] - hashes[b]
            if d <= int(v["phash_identical_distance"]):
                flags.append({"a": a, "b": b, "distance": int(d), "level": "FAIL",
                              "note": "images are effectively identical — "
                                      "likely a reused or copied file"})
            elif d <= int(v["phash_duplicate_distance"]):
                flags.append({"a": a, "b": b, "distance": int(d), "level": "WARNING",
                              "note": "near-duplicate composition — confirm the "
                                      "two scenes are genuinely different"})
    return flags


# ── driver ────────────────────────────────────────────────────────────────
def main(
    cfg: dict | None = None,
    start: int | None = None,
    end: int | None = None,
    ids: list[int] | None = None,
    quiet: bool = False,
) -> dict:
    cfg = cfg or load_config()
    from .common import parse_range

    total = cfg["book"]["total_entries"]
    if ids is None:
        ids = parse_range(start, end, total)

    final_dir = p(cfg, "final_dir")
    prompts = read_json(p(cfg, "generated_prompts"), default={"prompts": {}})["prompts"]

    results: dict[int, dict] = {}
    missing: list[int] = []
    for i in ids:
        f = final_dir / img_name(i)
        if not f.exists():
            missing.append(i)
            continue
        results[i] = validate_one(i, f, cfg, prompts.get(str(i)))

    dupes = check_duplicates(results, cfg)

    # fold duplicate FAILs back into the per-image verdicts
    for d in dupes:
        if d["level"] == "FAIL":
            for k in ("a", "b"):
                results[d[k]]["failures"].append(
                    f"identical to {d['b' if k == 'a' else 'a']:03d} "
                    f"(phash distance {d['distance']})"
                )
                results[d[k]]["status"] = "FAIL"
        else:
            for k in ("a", "b"):
                results[d[k]]["warnings"].append(
                    f"near-duplicate of {d['b' if k == 'a' else 'a']:03d} "
                    f"(phash distance {d['distance']})"
                )

    # keep generation_metadata in step with the latest verdicts
    meta_path = p(cfg, "metadata")
    meta = read_json(meta_path, default={"model_runs": [], "images": {}})
    for i, r in results.items():
        rec = meta["images"].setdefault(str(i), {"id": i})
        rec["validation_status"] = r["status"]
        rec["validation_failures"] = r["failures"]
        rec["validation_warnings"] = r["warnings"]
        rec["validation_stats"] = r["stats"]
    write_json(meta_path, meta)

    if not quiet:
        _report(results, missing, dupes, ids)

    return {"results": results, "missing": missing, "duplicates": dupes}


def _report(results, missing, dupes, ids) -> None:
    print(f"{'id':>4}  {'status':<8}{'dims':<11}{'PPI':<6}{'white':<8}{'ink':<8}notes")
    print("-" * 92)
    for i in sorted(results):
        r = results[i]
        s = r["stats"]
        ppi = min(s.get("effective_ppi", [0, 0]))
        note = ""
        if r["failures"]:
            note = "FAIL: " + "; ".join(r["failures"])[:52]
        elif r["warnings"]:
            note = "warn: " + "; ".join(r["warnings"])[:52]
        print(f"{i:>4}  {r['status']:<8}{s.get('dimensions',''):<11}"
              f"{ppi:<6.0f}{s.get('white_fraction',0):<8.3f}"
              f"{s.get('ink_fraction',0):<8.3f}{note}")
    print("-" * 92)
    npass = sum(1 for r in results.values() if r["status"] == "PASS")
    print(f"validated {len(results)}/{len(ids)}: {npass} PASS, "
          f"{len(results) - npass} FAIL")
    if missing:
        print(f"MISSING images: {', '.join(f'{m:03d}' for m in missing)}")
    if dupes:
        print("\nduplicate screening:")
        for d in dupes:
            print(f"  {d['level']:<8}{d['a']:03d} vs {d['b']:03d}  "
                  f"distance {d['distance']}  — {d['note']}")
    else:
        print("duplicate screening: no duplicates or near-duplicates found")


if __name__ == "__main__":
    main()
