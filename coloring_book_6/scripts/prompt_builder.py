"""Assemble the final generation prompt for each illustration.

Structure (per the production brief):
  [A] master style   [B] character consistency   [C] scene
  [D] composition    [E] negative / exclusion requirements

A Spanish manuscript sentence is NEVER sent to the image model — the authored
English scene description is. That keeps the Spanish text out of the artwork.
"""
from __future__ import annotations

import re
from pathlib import Path

from .common import ROOT, load_config, p, read_json, write_json

BLOCK_RE = re.compile(r"^\[([A-Z0-9_]+(?::[A-Z_0-9]+)?)\]\s*$")

DEFAULT_WARDROBE = (
    "He wears the collection's signature outfit: a short-sleeved t-shirt with one "
    "single plain outlined five-point star centred on the chest, knee-length shorts "
    "with a simple rolled cuff, short socks and chunky rounded sneakers. Every "
    "garment is outline only, left white so a child can colour it, and carries no "
    "writing, lettering, numbers or logos of any kind."
)

DEFAULT_SUPPORTING = (
    "Only the one main boy appears in this illustration. Do not add any other "
    "children or people, and do not draw a second copy of him."
)

FULLBODY_CLAUSE = (
    ", and when the whole body is shown neither the hands nor the feet are cropped"
)


def load_blocks(path: Path) -> dict[str, str]:
    """Read master_prompt.txt into {block_name: text}, dropping comments."""
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if line.lstrip().startswith("#"):
            continue
        m = BLOCK_RE.match(line.strip())
        if m:
            current = m.group(1)
            blocks[current] = []
            continue
        if current and line.strip():
            blocks[current].append(line.strip())
    return {k: " ".join(v) for k, v in blocks.items()}


def _fill(template: str, subs: dict[str, str]) -> str:
    out = template
    for key, val in subs.items():
        out = out.replace("{{" + key + "}}", val)
    leftover = re.findall(r"\{\{(\w+)\}\}", out)
    if leftover:
        raise SystemExit(f"prompt template has unfilled placeholders: {leftover}")
    return out


def build_one(entry: dict, scene: dict, blocks: dict[str, str], cfg: dict) -> dict:
    """Return the full prompt record for a single illustration."""
    is_full_body = "full-body" in scene.get("framing", "").lower()

    subs = {
        "WARDROBE": scene.get("wardrobe") or DEFAULT_WARDROBE,
        "EXPRESSION": scene.get("expression", "cheerful and bright"),
        "SUPPORTING_CAST": scene.get("supporting_cast") or DEFAULT_SUPPORTING,
        "SCENE": scene["scene"],
        "FRAMING": scene.get("framing", ""),
        "POSE": scene.get("pose", ""),
        "FULLBODY_CLAUSE": FULLBODY_CLAUSE if is_full_body else "",
        "BLANK_SURFACES": scene.get("blank_surfaces", ""),
        "EXTRA_EXCLUSIONS": scene.get("extra_exclusions", ""),
    }

    # A mirror/reflection scene legitimately shows the character twice.
    if scene.get("allow_reflection"):
        subs["SUPPORTING_CAST"] = (
            "Apart from the boy's own reflection inside the mirror, no other person "
            "appears in this illustration."
        )

    parts = [
        _fill(blocks["A:STYLE"], subs),
        _fill(blocks["B:CHARACTER"], subs),
        _fill(blocks["B2:SUPPORTING_CAST"], subs),
        _fill(blocks["C:SCENE"], subs),
        _fill(blocks["D:COMPOSITION"], subs),
        _fill(blocks["E:EXCLUSIONS"], subs),
    ]

    use_refs = cfg["image_generation"].get("use_reference_images", False)
    if use_refs:
        parts.insert(0, blocks["F:REFERENCE_ROLE_INSTRUCTIONS"])

    prompt = "\n\n".join(x.strip() for x in parts if x.strip())

    return {
        "id": entry["id"],
        "section": entry["section"],
        "source_text": entry["text"],          # Spanish, verbatim, for the record
        "concept": scene.get("concept", ""),
        "scene_description": scene["scene"],
        "framing": scene.get("framing", ""),
        "pose": scene.get("pose", ""),
        "expression": scene.get("expression", ""),
        "prompt": prompt,
        "prompt_chars": len(prompt),
        "uses_reference_images": bool(use_refs),
        "allow_reflection": bool(scene.get("allow_reflection")),
    }


def build(cfg: dict, ids: list[int] | None = None) -> dict[int, dict]:
    entries = {e["id"]: e for e in read_json(p(cfg, "entries"))["entries"]}
    scenes = read_json(p(cfg, "scenes"))["scenes"]
    blocks = load_blocks(p(cfg, "master_prompt"))

    wanted = ids or sorted(int(k) for k in scenes)
    built: dict[int, dict] = {}
    missing: list[int] = []
    for i in wanted:
        if str(i) not in scenes:
            missing.append(i)
            continue
        built[i] = build_one(entries[i], scenes[str(i)], blocks, cfg)

    if missing:
        raise SystemExit(
            "no scene authored yet for id(s): "
            + ", ".join(f"{m:03d}" for m in missing)
            + "\n  Scenes are designed batch-by-batch; author them in prompts/scenes.json."
        )
    return built


def main(cfg: dict | None = None, ids: list[int] | None = None,
         quiet: bool = False) -> dict:
    cfg = cfg or load_config()
    built = build(cfg, ids)

    # merge into the persistent prompt store, never dropping other batches
    store = read_json(p(cfg, "generated_prompts"), default={"prompts": {}})
    store["prompts"].update({str(k): v for k, v in built.items()})
    write_json(p(cfg, "generated_prompts"), store)

    if not quiet:
        lens = [v["prompt_chars"] for v in built.values()]
        print(f"built {len(built)} prompts "
              f"(chars: min {min(lens)}, max {max(lens)}, mean {sum(lens)//len(lens)})")
        print(f"reference conditioning: "
              f"{'ON' if cfg['image_generation']['use_reference_images'] else 'OFF'}")
        print(f"stored -> {cfg['paths']['generated_prompts']}")
    return built


if __name__ == "__main__":
    main()
