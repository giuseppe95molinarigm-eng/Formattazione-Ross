"""Replicate image generation: the only module that spends money.

Design rules enforced here:
  * the API token is read from the environment, never from source or metadata
  * an existing image that already PASSED validation is SKIPPED (resumable,
    crash-safe, and it protects approved artwork from accidental overwrite)
  * --force is required to replace an existing asset
  * every attempt is priced and confirmed before any call is made
  * rejected attempts are preserved for comparison, never deleted
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import io
import os
import time
from pathlib import Path

import requests

from .common import (
    ROOT,
    active_profile,
    rel,
    get_logger,
    img_name,
    load_config,
    p,
    read_json,
    redact,
    require_token,
    write_json,
)
from .postprocess import process
from .validate_images import validate_one

log = get_logger(__name__)


# ── metadata store ────────────────────────────────────────────────────────
def load_metadata(cfg: dict) -> dict:
    return read_json(p(cfg, "metadata"), default={"model_runs": [], "images": {}})


def save_metadata(cfg: dict, meta: dict) -> None:
    write_json(p(cfg, "metadata"), meta)


def is_complete(cfg: dict, entry_id: int, meta: dict) -> bool:
    """True when a production asset exists AND its recorded status is PASS."""
    final = p(cfg, "final_dir") / img_name(entry_id)
    if not final.exists():
        return False
    rec = meta["images"].get(str(entry_id))
    return bool(rec and rec.get("validation_status") == "PASS")


# ── payload construction ──────────────────────────────────────────────────
def build_input(prompt: str, cfg: dict, prof: dict, ref_handles: list) -> dict:
    """Assemble the model input dict strictly from the profile's declared schema.

    Only fields the profile declares are sent, so no unsupported parameter is
    ever invented for a model that does not accept it.
    """
    payload: dict = {"prompt": prompt}

    if prof.get("aspect_ratio"):
        payload["aspect_ratio"] = prof["aspect_ratio"]
    if prof.get("output_resolution"):
        payload["output_resolution"] = prof["output_resolution"]
    for k, v in (prof.get("extra_input") or {}).items():
        payload[k] = v

    if ref_handles and prof.get("supports_reference_images"):
        field = prof.get("reference_field")
        if field:
            payload[field] = ref_handles[: int(prof.get("max_reference_images", 3))]

    return payload


def open_references(cfg: dict, prof: dict) -> list:
    """Open the style-reference images as file handles for upload."""
    if not cfg["image_generation"].get("use_reference_images"):
        return []
    if not prof.get("supports_reference_images"):
        log.warning(
            "profile %s does not support reference images; falling back to the "
            "master style prompt alone", prof["_name"]
        )
        return []
    limit = min(
        int(cfg["image_generation"].get("reference_count", 3)),
        int(prof.get("max_reference_images", 3)),
    )
    handles = []
    for relpath in cfg["image_generation"]["reference_images"][:limit]:
        path = ROOT / relpath
        if not path.exists():
            log.warning("reference image missing, skipped: %s", relpath)
            continue
        handles.append(path)
    return handles


# ── one image ─────────────────────────────────────────────────────────────
def _download(url: str, dest: Path, timeout: int) -> None:
    r = requests.get(url, timeout=timeout, stream=True)
    r.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as fh:
        for chunk in r.iter_content(65536):
            fh.write(chunk)


def _save_output(output, dest: Path, timeout: int) -> None:
    """Persist whatever shape the client returned (FileOutput / URL / bytes)."""
    item = output[0] if isinstance(output, list) and output else output
    if hasattr(item, "read"):                       # replicate FileOutput
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as fh:
            fh.write(item.read())
        return
    if isinstance(item, (bytes, bytearray)):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(item)
        return
    url = getattr(item, "url", None) or str(item)
    _download(url, dest, timeout)


def generate_one(
    entry_id: int,
    record: dict,
    cfg: dict,
    prof: dict,
    ref_handles: list,
    force: bool = False,
) -> dict:
    """Generate, post-process and validate one illustration. Returns metadata."""
    import replicate

    ig = cfg["image_generation"]
    raw_dir = p(cfg, "raw_dir")
    final_dir = p(cfg, "final_dir")
    rej_dir = p(cfg, "rejected_dir")
    max_attempts = int(ig.get("max_attempts", 3))
    timeout = int(ig.get("request_timeout_s", 300))
    backoff = list(ig.get("retry_backoff_s", [2, 4, 8, 16]))

    prompt = record["prompt"]
    attempts_log: list[dict] = []
    final_path = final_dir / img_name(entry_id)

    for attempt in range(1, max_attempts + 1):
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        raw_path = raw_dir / f"{entry_id:03d}_a{attempt}_{stamp}.png"
        att: dict = {"attempt": attempt, "started": stamp}

        # ── the PAID call. Only a failure here is worth retrying. ────────
        try:
            handles = [open(h, "rb") for h in ref_handles]
            try:
                payload = build_input(prompt, cfg, prof, handles)
                t0 = time.time()
                output = replicate.run(prof["slug"], input=payload)
                att["seconds"] = round(time.time() - t0, 1)
            finally:
                for h in handles:
                    h.close()
        except Exception as exc:                        # noqa: BLE001
            att["error"] = redact(f"{type(exc).__name__}: {exc}")
            att["stage"] = "api_call"
            attempts_log.append(att)
            log.error("%03d attempt %d — API call failed: %s",
                      entry_id, attempt, att["error"])
            if attempt < max_attempts:
                wait = backoff[min(attempt - 1, len(backoff) - 1)]
                log.info("retrying %03d in %ss", entry_id, wait)
                time.sleep(wait)
            continue

        # ── past this point the call is already paid for. A local error ──
        # ── must NOT trigger another one: fail fast and keep the raw    ──
        # ── output so it can be reprocessed for free.                   ──
        try:
            _save_output(output, raw_path, timeout)
            att["raw_file"] = rel(raw_path)

            rep = process(raw_path, final_path, cfg)
            att.update(rep)

            verdict = validate_one(entry_id, final_path, cfg, record)
            att["validation_status"] = verdict["status"]
            att["validation_failures"] = verdict["failures"]
            att["validation_warnings"] = verdict["warnings"]
        except Exception as exc:                        # noqa: BLE001
            att["error"] = redact(f"{type(exc).__name__}: {exc}")
            att["stage"] = "local_processing"
            att["local_failure"] = True
            attempts_log.append(att)
            log.error(
                "%03d attempt %d — the image was generated and PAID FOR but "
                "local processing failed: %s", entry_id, attempt, att["error"]
            )
            log.error(
                "%03d raw output kept at %s — fix the cause and run "
                "`python main.py reprocess --id %d` (free, no new API call)",
                entry_id, att.get("raw_file", raw_path), entry_id,
            )
            break

        if verdict["status"] == "PASS":
            attempts_log.append(att)
            log.info("%03d PASS on attempt %d (%s)", entry_id, attempt,
                     rep.get("resample_direction"))
            break

        # failed QC: keep the attempt for comparison, then retry
        rej_dir.mkdir(parents=True, exist_ok=True)
        keep = rej_dir / f"{entry_id:03d}_a{attempt}_{stamp}_FAIL.png"
        if final_path.exists():
            final_path.replace(keep)
        att["rejected_file"] = rel(keep)
        log.warning("%03d attempt %d FAILED QC: %s", entry_id, attempt,
                    "; ".join(verdict["failures"]))
        attempts_log.append(att)

        if attempt < max_attempts:
            wait = backoff[min(attempt - 1, len(backoff) - 1)]
            time.sleep(wait)

    last = attempts_log[-1] if attempts_log else {}
    status = last.get("validation_status", "FAIL")

    return {
        "id": entry_id,
        "section": record["section"],
        "source_text": record["source_text"],
        "scene_description": record["scene_description"],
        "prompt": prompt,
        "model": prof["slug"],
        "generation_parameters": {
            k: v
            for k, v in build_input(prompt, cfg, prof, ["<reference images>"]).items()
            if k != "prompt"
        },
        "source_output_dimensions": last.get("source_output_dimensions", ""),
        "final_dimensions": last.get("final_dimensions", ""),
        "resample_direction": last.get("resample_direction", ""),
        "validation_status": status,
        "validation_failures": last.get("validation_failures", []),
        "validation_warnings": last.get("validation_warnings", []),
        "attempts": len(attempts_log),
        "attempt_log": attempts_log,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "uses_reference_images": bool(ref_handles),
    }


# ── cost preview ──────────────────────────────────────────────────────────
def plan(cfg: dict, ids: list[int], force: bool) -> dict:
    meta = load_metadata(cfg)
    prompts = read_json(p(cfg, "generated_prompts"), default={"prompts": {}})["prompts"]

    todo, skip, unprompted = [], [], []
    for i in ids:
        if str(i) not in prompts:
            unprompted.append(i)
        elif is_complete(cfg, i, meta) and not force:
            skip.append(i)
        else:
            todo.append(i)

    prof = active_profile(cfg)
    unit = float(prof.get("price_usd_per_image") or 0)
    max_attempts = int(cfg["image_generation"].get("max_attempts", 3))
    return {
        "todo": todo,
        "skip": skip,
        "unprompted": unprompted,
        "model": prof["slug"],
        "profile": prof["_name"],
        "unit_price_usd": unit,
        "calls_min": len(todo),
        "calls_max": len(todo) * max_attempts,
        "cost_min_usd": round(len(todo) * unit, 2),
        "cost_max_usd": round(len(todo) * max_attempts * unit, 2),
        "cost_expected_usd": round(len(todo) * unit * 1.15, 2),
    }


def print_plan(pl: dict, cfg: dict) -> None:
    prof = active_profile(cfg)
    print("\n" + "=" * 72)
    print("BATCH PLAN — nothing has been generated yet")
    print("=" * 72)
    print(f"  model              : {pl['model']}  (profile: {pl['profile']})")
    print(f"  aspect / resolution: {prof.get('aspect_ratio')} / "
          f"{prof.get('output_resolution', 'default')}")
    print(f"  reference images   : "
          f"{'ON — ' + str(len(cfg['image_generation']['reference_images'])) + ' style refs' if cfg['image_generation']['use_reference_images'] else 'OFF'}")
    print(f"  to generate        : {len(pl['todo'])} "
          f"{'→ ' + ', '.join(f'{i:03d}' for i in pl['todo']) if pl['todo'] else ''}")
    if pl["skip"]:
        print(f"  already PASSED     : {len(pl['skip'])} (skipped; use --force to replace)"
              f"  → {', '.join(f'{i:03d}' for i in pl['skip'])}")
    if pl["unprompted"]:
        print(f"  NO PROMPT YET      : {', '.join(f'{i:03d}' for i in pl['unprompted'])}")
    print("-" * 72)
    print(f"  paid API calls     : {pl['calls_min']} minimum, "
          f"up to {pl['calls_max']} if every image needs all retries")
    print(f"  unit price         : ${pl['unit_price_usd']:.3f} per image")
    print(f"  estimated cost     : ${pl['cost_min_usd']:.2f} best case, "
          f"~${pl['cost_expected_usd']:.2f} expected, "
          f"${pl['cost_max_usd']:.2f} worst case")
    print("=" * 72)


# ── batch driver ──────────────────────────────────────────────────────────
def main(
    cfg: dict | None = None,
    start: int | None = None,
    end: int | None = None,
    ids: list[int] | None = None,
    force: bool = False,
    yes: bool = False,
    dry_run: bool = False,
) -> dict:
    cfg = cfg or load_config()
    total = cfg["book"]["total_entries"]
    if ids is None:
        from .common import parse_range
        ids = parse_range(start, end, total)

    pl = plan(cfg, ids, force)
    print_plan(pl, cfg)

    if pl["unprompted"]:
        raise SystemExit(
            "Refusing to start: some ids have no authored prompt yet.\n"
            "  Author their scenes in prompts/scenes.json, then run "
            "`python main.py prompts`."
        )
    if dry_run:
        print("\n--dry-run: stopping before any paid call.")
        return {"planned": pl, "results": {}}
    if not pl["todo"]:
        print("\nNothing to do — every requested image already exists and passed.")
        return {"planned": pl, "results": {}}

    if not yes:
        ans = input(
            f"\nProceed and spend up to ${pl['cost_max_usd']:.2f} on Replicate? "
            "[y/N] "
        ).strip().lower()
        if ans not in {"y", "yes"}:
            print("Aborted. No API calls were made.")
            return {"planned": pl, "results": {}}

    require_token()                       # fails loudly before any work starts
    prof = active_profile(cfg)
    ref_handles = open_references(cfg, prof)
    prompts = read_json(p(cfg, "generated_prompts"))["prompts"]
    meta = load_metadata(cfg)

    workers = max(1, int(cfg["image_generation"].get("parallel_workers", 1)))
    results: dict[int, dict] = {}

    log.info("generating %d image(s) with %s (%d worker(s))",
             len(pl["todo"]), prof["slug"], workers)

    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                generate_one, i, prompts[str(i)], cfg, prof, ref_handles, force
            ): i
            for i in pl["todo"]
        }
        for fut in cf.as_completed(futures):
            i = futures[fut]
            try:
                rec = fut.result()
            except Exception as exc:                    # noqa: BLE001
                log.error("%03d crashed: %s", i, redact(str(exc)))
                rec = {
                    "id": i,
                    "validation_status": "FAIL",
                    "validation_failures": [redact(str(exc))],
                    "attempts": 0,
                }
            results[i] = rec
            # persist after every image so a crash never loses finished work
            meta["images"][str(i)] = rec
            save_metadata(cfg, meta)

    meta.setdefault("model_runs", []).append(
        {
            "at": dt.datetime.now().isoformat(timespec="seconds"),
            "model": prof["slug"],
            "profile": prof["_name"],
            "ids": pl["todo"],
            "unit_price_usd": pl["unit_price_usd"],
        }
    )
    save_metadata(cfg, meta)

    ok = [i for i, r in results.items() if r.get("validation_status") == "PASS"]
    bad = sorted(set(results) - set(ok))
    print(f"\ngenerated {len(results)}: {len(ok)} PASS, {len(bad)} FAIL")
    if bad:
        print("  needs attention: " + ", ".join(f"{i:03d}" for i in bad))
        for i in bad:
            for f in results[i].get("validation_failures", []):
                print(f"    {i:03d}  {f}")
    return {"planned": pl, "results": results}


if __name__ == "__main__":
    main()


# ── free recovery: re-run post-processing on already-paid-for raw output ──
def reprocess(cfg: dict, ids: list[int], quiet: bool = False) -> dict:
    """Re-derive production assets from saved raw output. Makes NO API call.

    Use after a local post-processing or validation failure, or after changing
    the postprocess settings in config.yaml: the Replicate output has already
    been paid for, so there is no reason to buy it twice.
    """
    raw_dir = p(cfg, "raw_dir")
    final_dir = p(cfg, "final_dir")
    prompts = read_json(p(cfg, "generated_prompts"), default={"prompts": {}})["prompts"]
    meta = load_metadata(cfg)

    results: dict[int, dict] = {}
    for i in ids:
        candidates = sorted(raw_dir.glob(f"{i:03d}_a*.png"))
        if not candidates:
            results[i] = {"status": "NO_RAW",
                          "detail": f"no saved raw output in {rel(raw_dir)}"}
            continue
        newest = candidates[-1]                 # timestamped, so last == latest
        final_path = final_dir / img_name(i)
        try:
            rep = process(newest, final_path, cfg)
            verdict = validate_one(i, final_path, cfg, prompts.get(str(i)))
        except Exception as exc:                        # noqa: BLE001
            results[i] = {"status": "ERROR", "detail": redact(str(exc))}
            continue

        rec = meta["images"].setdefault(str(i), {"id": i})
        rec.update(
            {
                "source_output_dimensions": rep.get("source_output_dimensions", ""),
                "final_dimensions": rep.get("final_dimensions", ""),
                "resample_direction": rep.get("resample_direction", ""),
                "validation_status": verdict["status"],
                "validation_failures": verdict["failures"],
                "validation_warnings": verdict["warnings"],
                "reprocessed_from": rel(newest),
                "reprocessed_at": dt.datetime.now().isoformat(timespec="seconds"),
            }
        )
        results[i] = {"status": verdict["status"],
                      "detail": "; ".join(verdict["failures"]),
                      "raw": rel(newest)}
    save_metadata(cfg, meta)

    if not quiet:
        print("reprocessed from saved raw output — no API calls, no charge\n")
        print(f"{'id':>4}  {'status':<9}source / problem")
        print("-" * 72)
        for i in sorted(results):
            r = results[i]
            print(f"{i:>4}  {r['status']:<9}{r.get('raw') or r.get('detail', '')}")
        print("-" * 72)
        ok = sum(1 for r in results.values() if r["status"] == "PASS")
        print(f"{ok}/{len(results)} now PASS")
    return results
