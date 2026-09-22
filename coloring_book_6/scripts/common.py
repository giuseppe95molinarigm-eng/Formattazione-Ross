"""Shared helpers: config loading, paths, logging, secret-safe Replicate auth."""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
TOKEN_ENV = "REPLICATE_API_TOKEN"


# ── config ────────────────────────────────────────────────────────────────
def load_config(path: str | Path | None = None) -> dict[str, Any]:
    cfg_path = Path(path) if path else ROOT / "config.yaml"
    with open(cfg_path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    cfg["_root"] = str(ROOT)
    return cfg


def p(cfg: dict, key: str) -> Path:
    """Resolve a path from config['paths'] against the project root."""
    return ROOT / cfg["paths"][key]


def rel(path: Path | str) -> str:
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def active_profile(cfg: dict) -> dict[str, Any]:
    """The model profile currently selected in config.yaml."""
    name = cfg["image_generation"]["active_profile"]
    try:
        prof = dict(cfg["model_profiles"][name])
    except KeyError:
        raise SystemExit(
            f"config.yaml: active_profile '{name}' has no entry under model_profiles"
        )
    prof["_name"] = name
    # `image_generation.model` stays authoritative so a user can override the
    # slug without touching the profile block.
    prof.setdefault("slug", cfg["image_generation"]["model"])
    return prof


# ── json io ───────────────────────────────────────────────────────────────
def read_json(path: Path | str, default: Any = None) -> Any:
    path = Path(path)
    if not path.exists():
        if default is not None:
            return default
        raise SystemExit(f"missing required file: {rel(path)}")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path | str, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    tmp.replace(path)  # atomic: a crash mid-write never corrupts state


# ── secrets ───────────────────────────────────────────────────────────────
_SECRET_RE = re.compile(r"r8_[A-Za-z0-9]{8,}")


class _Redactor(logging.Filter):
    """Belt-and-braces: strips anything token-shaped out of every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _SECRET_RE.sub("r8_***REDACTED***", record.msg)
        return True


def redact(text: str) -> str:
    return _SECRET_RE.sub("r8_***REDACTED***", str(text))


def require_token() -> str:
    """Load REPLICATE_API_TOKEN from the environment (populated from .env).

    The token is never returned into any file, log line or metadata record.
    """
    load_dotenv(ROOT / ".env")
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        raise SystemExit(
            f"{TOKEN_ENV} is not set.\n"
            f"  Create {rel(ROOT / '.env')} containing:\n"
            f"    {TOKEN_ENV}=your_replicate_api_token_here\n"
            f"  (copy .env.example and paste your token from replicate.com/account)"
        )
    os.environ[TOKEN_ENV] = token
    return token


def token_fingerprint() -> str:
    """Safe-to-print proof that a token is configured. Never the token itself."""
    load_dotenv(ROOT / ".env")
    t = os.environ.get(TOKEN_ENV, "")
    if not t:
        return "<not set>"
    return f"{t[:3]}…{t[-2:]} (length {len(t)})"


# ── logging ───────────────────────────────────────────────────────────────
def get_logger(name: str, cfg: dict | None = None) -> logging.Logger:
    log = logging.getLogger(name)
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S")

    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    sh.addFilter(_Redactor())
    log.addHandler(sh)

    log_dir = ROOT / (cfg["paths"]["log_dir"] if cfg else "logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_dir / "pipeline.log", encoding="utf-8")
    fh.setFormatter(fmt)
    fh.addFilter(_Redactor())
    log.addHandler(fh)
    return log


# ── ids ───────────────────────────────────────────────────────────────────
def img_name(entry_id: int) -> str:
    """Zero-padded production filename: 1 -> '001.png', 101 -> '101.png'."""
    return f"{entry_id:03d}.png"


def parse_range(start: int | None, end: int | None, total: int) -> list[int]:
    s = 1 if start is None else int(start)
    e = total if end is None else int(end)
    if not (1 <= s <= e <= total):
        raise SystemExit(f"invalid range {s}..{e} (valid: 1..{total})")
    return list(range(s, e + 1))
