#!/usr/bin/env python3
"""¡Ya tengo 6 años! — production CLI.

    python main.py parse                      # manuscript -> structured JSON
    python main.py analyze-refs               # measure the collection style
    python main.py prompts                     # assemble generation prompts
    python main.py doctor                      # check Replicate auth + schema
    python main.py plan --start 1 --end 20     # what WOULD be generated + cost
    python main.py generate --start 1 --end 20 # paid: generate a batch
    python main.py validate --start 1 --end 20
    python main.py contact-sheet --start 1 --end 20
    python main.py regenerate --id 7
    python main.py status
    python main.py build-book
    python main.py preflight
"""
from __future__ import annotations

import argparse
import sys

from scripts.common import ROOT, active_profile, img_name, load_config, p, read_json


def _range_args(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("--start", type=int, help="first entry id (default 1)")
    sp.add_argument("--end", type=int, help="last entry id (default 101)")
    sp.add_argument("--id", type=int, action="append", dest="ids",
                    help="a single id; repeatable (overrides --start/--end)")


def cmd_parse(a, cfg):
    from scripts.parse_manuscript import main as run
    res = run(cfg)
    return 1 if res["problems"] else 0


def cmd_analyze(a, cfg):
    from scripts.analyze_references import main as run
    run(cfg)
    return 0


def cmd_prompts(a, cfg):
    from scripts.prompt_builder import main as run
    run(cfg, ids=a.ids)
    return 0


def cmd_doctor(a, cfg):
    """Verify Replicate configuration and print the live model input schema.

    This makes a metadata-only request: it does NOT generate an image and does
    NOT cost anything.
    """
    import json
    import os

    from scripts.common import require_token, token_fingerprint

    prof = active_profile(cfg)
    print("── configuration ─────────────────────────────────────────────")
    print(f"  model            : {prof['slug']}")
    print(f"  profile          : {prof['_name']}")
    print(f"  aspect_ratio     : {prof.get('aspect_ratio')}")
    print(f"  output_resolution: {prof.get('output_resolution', '(model default)')}")
    print(f"  reference images : "
          f"{'ON' if cfg['image_generation']['use_reference_images'] else 'OFF'}"
          f" (field: {prof.get('reference_field')}, "
          f"max {prof.get('max_reference_images')})")
    print(f"  token            : {token_fingerprint()}   [read from .env]")

    missing = [r for r in cfg["image_generation"]["reference_images"]
               if not (ROOT / r).exists()]
    print(f"  reference files  : "
          f"{'all present' if not missing else 'MISSING ' + ', '.join(missing)}")

    try:
        require_token()
        import replicate
    except SystemExit as exc:
        print(f"\n  FAIL: {exc}")
        return 1
    except ImportError:
        print("\n  FAIL: the `replicate` package is not installed "
              "(pip install -r requirements.txt)")
        return 1

    print("\n── live model schema (no image generated, no charge) ─────────")
    try:
        client = replicate.Client(api_token=os.environ["REPLICATE_API_TOKEN"])
        owner, name = prof["slug"].split("/", 1)
        model = client.models.get(f"{owner}/{name}")
        ver = model.latest_version
        schema = (ver.openapi_schema["components"]["schemas"]["Input"]["properties"]
                  if ver else {})
        print(f"  resolved version : {ver.id[:12] if ver else '?'}…")
        print(f"  {'field':<24}{'type':<10}default / allowed")
        print("  " + "-" * 62)
        for k, v in sorted(schema.items(), key=lambda kv: kv[1].get("x-order", 99)):
            t = v.get("type", v.get("allOf", [{}])[0].get("$ref", "?"))
            extra = ""
            if "default" in v:
                extra = f"default={v['default']}"
            if "enum" in v:
                extra += ("  " if extra else "") + "enum=" + ",".join(
                    str(x) for x in v["enum"][:12])
            print(f"  {k:<24}{str(t):<10}{extra}")

        # cross-check everything the pipeline intends to send
        from scripts.generate_images import build_input
        payload = build_input("<prompt>", cfg, prof, ["<ref>"])
        unknown = [k for k in payload if k not in schema]
        print("\n  fields this pipeline will send: "
              + ", ".join(sorted(payload)))
        if unknown:
            print(f"  WARNING: not in the live schema -> {', '.join(unknown)}")
            print("  Fix model_profiles in config.yaml before generating.")
            return 1
        ar = schema.get("aspect_ratio", {}).get("enum")
        if ar and prof.get("aspect_ratio") not in ar:
            print(f"  WARNING: aspect_ratio '{prof.get('aspect_ratio')}' is not in "
                  f"{ar}")
            return 1
        print("  OK: every field the pipeline sends exists in the live schema.")
        return 0
    except Exception as exc:                            # noqa: BLE001
        from scripts.common import redact
        print(f"  could not reach the Replicate API: {redact(exc)}")
        print("  (Auth and payload wiring are still configured; re-run `doctor` "
              "from a machine with network access to api.replicate.com.)")
        return 1


def cmd_plan(a, cfg):
    from scripts.common import parse_range
    from scripts.generate_images import plan, print_plan
    ids = a.ids or parse_range(a.start, a.end, cfg["book"]["total_entries"])
    print_plan(plan(cfg, ids, a.force), cfg)
    return 0


def cmd_generate(a, cfg):
    from scripts.generate_images import main as run
    res = run(cfg, start=a.start, end=a.end, ids=a.ids, force=a.force,
              yes=a.yes, dry_run=a.dry_run)
    bad = [i for i, r in res["results"].items()
           if r.get("validation_status") != "PASS"]
    return 1 if bad else 0


def cmd_regenerate(a, cfg):
    if not a.ids:
        print("regenerate needs at least one --id")
        return 2
    from scripts.generate_images import main as run
    res = run(cfg, ids=sorted(set(a.ids)), force=True, yes=a.yes,
              dry_run=a.dry_run)
    bad = [i for i, r in res["results"].items()
           if r.get("validation_status") != "PASS"]
    return 1 if bad else 0


def cmd_validate(a, cfg):
    from scripts.validate_images import main as run
    res = run(cfg, start=a.start, end=a.end, ids=a.ids)
    bad = [i for i, r in res["results"].items() if r["status"] != "PASS"]
    return 1 if (bad or res["missing"]) else 0


def cmd_contact(a, cfg):
    from scripts.create_contact_sheet import main as run
    run(cfg, start=a.start, end=a.end, ids=a.ids)
    return 0


def cmd_status(a, cfg):
    total = cfg["book"]["total_entries"]
    final_dir = p(cfg, "final_dir")
    meta = read_json(p(cfg, "metadata"), default={"images": {}})["images"]
    scenes = read_json(p(cfg, "scenes"), default={"scenes": {}})["scenes"]
    sections = read_json(p(cfg, "sections"), default={"sections": []})["sections"]

    print(f"{cfg['book']['title']} — production status\n")
    print(f"{'batch':<8}{'range':<11}{'scenes':<9}{'images':<9}{'PASS':<7}status")
    print("-" * 62)
    batches = [(s["first_id"], s["last_id"]) for s in sections] or [(1, total)]
    for n, (lo, hi) in enumerate(batches, 1):
        rng = range(lo, hi + 1)
        sc = sum(1 for i in rng if str(i) in scenes)
        im = sum(1 for i in rng if (final_dir / img_name(i)).exists())
        ok = sum(1 for i in rng
                 if meta.get(str(i), {}).get("validation_status") == "PASS")
        n_ = hi - lo + 1
        state = ("complete" if ok == n_ else
                 "in progress" if im else
                 "scenes ready" if sc == n_ else "not started")
        print(f"{n:<8}{f'{lo:03d}-{hi:03d}':<11}{f'{sc}/{n_}':<9}"
              f"{f'{im}/{n_}':<9}{f'{ok}/{n_}':<7}{state}")
    print("-" * 62)
    done = sum(1 for i in range(1, total + 1)
               if meta.get(str(i), {}).get("validation_status") == "PASS")
    print(f"approved illustrations: {done}/{total}")
    pdf = ROOT / cfg["output"]["interior_pdf"]
    print(f"interior PDF          : "
          f"{'built — ' + str(round(pdf.stat().st_size / 1e6, 1)) + ' MB' if pdf.exists() else 'not built yet'}")
    return 0


def cmd_build(a, cfg):
    from scripts.build_pdf import main as run
    run(cfg)
    return 0


def cmd_preflight(a, cfg):
    from scripts.preflight import main as run
    rep = run(cfg)
    return 1 if rep.critical_failures else 0


COMMANDS = {
    "parse": cmd_parse,
    "analyze-refs": cmd_analyze,
    "prompts": cmd_prompts,
    "doctor": cmd_doctor,
    "plan": cmd_plan,
    "generate": cmd_generate,
    "regenerate": cmd_regenerate,
    "validate": cmd_validate,
    "contact-sheet": cmd_contact,
    "status": cmd_status,
    "build-book": cmd_build,
    "preflight": cmd_preflight,
}


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="main.py",
        description="Production pipeline for '¡Ya tengo 6 años!' (KDP 8.5x11).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--config", help="path to config.yaml")
    sub = ap.add_subparsers(dest="command", required=True)

    for name in ("parse", "analyze-refs", "status", "build-book", "preflight"):
        sub.add_parser(name)

    for name in ("prompts", "validate", "contact-sheet"):
        sp = sub.add_parser(name)
        _range_args(sp)

    sp = sub.add_parser("plan")
    _range_args(sp)
    sp.add_argument("--force", action="store_true")

    for name in ("generate", "regenerate"):
        sp = sub.add_parser(name)
        _range_args(sp)
        sp.add_argument("--force", action="store_true",
                        help="replace images that already exist and passed")
        sp.add_argument("--yes", action="store_true",
                        help="skip the cost confirmation prompt")
        sp.add_argument("--dry-run", action="store_true",
                        help="show the plan and stop before any paid call")

    sub.add_parser("doctor")
    return ap


def main() -> int:
    ap = build_parser()
    a = ap.parse_args()
    cfg = load_config(a.config)
    for attr in ("start", "end", "ids", "force", "yes", "dry_run"):
        if not hasattr(a, attr):
            setattr(a, attr, None if attr in {"start", "end", "ids"} else False)
    if a.command == "regenerate":
        a.force = True
    return COMMANDS[a.command](a, cfg)


if __name__ == "__main__":
    sys.exit(main())
