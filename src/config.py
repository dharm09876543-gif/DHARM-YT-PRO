"""Configuration loading and validation for DHARM YT PRO."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
VALID_PRIVACY = {"public", "unlisted", "private"}
SLOT_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ConfigError(ValueError):
    """Raised when configuration is invalid."""


def load_yaml(name: str) -> dict[str, Any]:
    """Load config/<name>.yaml, falling back to <name>.example.yaml."""
    real = CONFIG_DIR / f"{name}.yaml"
    path = real if real.exists() else CONFIG_DIR / f"{name}.example.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _check_tz(tz: str, where: str, errors: list[str]) -> None:
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        errors.append(f"{where}: timezone '{tz}' galat hai (jaise Asia/Kolkata)")


def validate_settings(s: dict) -> list[str]:
    errors: list[str] = []
    _check_tz(s.get("app", {}).get("timezone", ""), "settings.app", errors)
    up = s.get("uploads", {})
    if up.get("default_privacy") not in VALID_PRIVACY:
        errors.append("settings.uploads.default_privacy public/unlisted/private hona chahiye")
    mcu = up.get("max_concurrent_uploads", 1)
    if not isinstance(mcu, int) or not 1 <= mcu <= 5:
        errors.append("settings.uploads.max_concurrent_uploads 1 se 5 ke beech ho")
    q = s.get("quota", {})
    if q.get("warning_threshold_units", 0) > q.get("daily_limit_units", 0):
        errors.append("settings.quota.warning_threshold_units daily limit se zyada nahi ho sakta")
    if s.get("drive", {}).get("cleanup_mode") != "trash":
        errors.append("settings.drive.cleanup_mode sirf 'trash' allowed hai (permanent delete band)")
    return errors


def validate_channels(c: dict) -> list[str]:
    errors: list[str] = []
    seen_keys, seen_ids = set(), set()
    chans = c.get("channels") or []
    if not chans:
        errors.append("channels: kam se kam ek channel chahiye")
    for i, ch in enumerate(chans):
        where = f"channels[{i}] ({ch.get('key', '?')})"
        key = ch.get("key")
        if not key:
            errors.append(f"{where}: 'key' zaroori hai")
        elif key in seen_keys:
            errors.append(f"{where}: key dobara aaya")
        seen_keys.add(key)
        cid = ch.get("channel_id") or ""
        if cid:
            if not cid.startswith("UC") or len(cid) != 24:
                errors.append(f"{where}: channel_id 'UC' se shuru aur 24 akshar ka hota hai")
            if cid in seen_ids:
                errors.append(f"{where}: channel_id dobara aaya")
            seen_ids.add(cid)
        if not ch.get("drive_folder_id"):
            errors.append(f"{where}: drive_folder_id zaroori hai")
        _check_tz(ch.get("timezone", "Asia/Kolkata"), where, errors)
        priv = (ch.get("defaults") or {}).get("privacy", "private")
        if priv not in VALID_PRIVACY:
            errors.append(f"{where}: defaults.privacy galat hai")
    return errors


def validate_schedules(s: dict) -> list[str]:
    errors: list[str] = []
    sch = s.get("scheduler", {})
    _check_tz(sch.get("timezone", ""), "scheduler", errors)
    def slots_ok(slots, where):
        for slot in slots or []:
            if not SLOT_RE.match(str(slot)):
                errors.append(f"{where}: slot '{slot}' HH:MM format mein ho")
        if len(set(slots or [])) != len(slots or []):
            errors.append(f"{where}: duplicate slots")
    slots_ok(sch.get("slots"), "scheduler.slots")
    for k, v in (sch.get("overrides") or {}).items():
        slots_ok((v or {}).get("slots"), f"scheduler.overrides.{k}")
    return errors


def validate_all() -> list[str]:
    return (validate_settings(load_yaml("settings"))
            + validate_channels(load_yaml("channels"))
            + validate_schedules(load_yaml("schedules")))


@dataclass
class Env:
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///data/dharm_yt.db"))
    token_key: str = field(default_factory=lambda: os.getenv("TOKEN_ENCRYPTION_KEY", ""))
    app_env: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
