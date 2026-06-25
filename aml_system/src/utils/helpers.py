"""Shared helpers used across AML modules."""

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


# ── Config Loading ───────────────────────────────────────────────────────────

_CONFIG_CACHE: dict | None = None


def load_config(config_path: str = "config/config.yaml") -> dict:
    """Load and cache the YAML configuration file."""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is None:
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path.resolve()}")
        with open(path, "r", encoding="utf-8") as f:
            _CONFIG_CACHE = yaml.safe_load(f)
    return _CONFIG_CACHE


def reload_config(config_path: str = "config/config.yaml") -> dict:
    """Force-reload config (useful in tests)."""
    global _CONFIG_CACHE
    _CONFIG_CACHE = None
    return load_config(config_path)


# ── ID Generation ────────────────────────────────────────────────────────────

def generate_id(prefix: str = "") -> str:
    """Generate a short unique ID with optional prefix."""
    uid = str(uuid.uuid4()).replace("-", "")[:12].upper()
    return f"{prefix}{uid}" if prefix else uid


def generate_alert_id() -> str:
    return generate_id("ALT-")


def generate_case_id() -> str:
    return generate_id("CASE-")


def generate_sar_id() -> str:
    return generate_id("SAR-")


# ── Date / Time Utilities ────────────────────────────────────────────────────

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def format_date(dt: datetime | None, fmt: str = "%Y-%m-%d") -> str:
    if dt is None:
        return "N/A"
    return dt.strftime(fmt)


def format_currency(amount: float, currency: str = "USD") -> str:
    return f"{currency} {amount:,.2f}"


# ── Output Directories ───────────────────────────────────────────────────────

def ensure_dir(path: str | Path) -> Path:
    """Create directory (and parents) if it doesn't exist."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


# ── Pretty-print tables ──────────────────────────────────────────────────────

def print_section(title: str, width: int = 70) -> None:
    print("\n" + "═" * width)
    print(f"  {title}")
    print("═" * width)


def print_kv(key: str, value: Any, indent: int = 2) -> None:
    print(f"{' ' * indent}{key:<35} {value}")
