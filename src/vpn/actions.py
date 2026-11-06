"""GitHub Actions helpers for the per-channel upload matrix (.github/workflows/upload.yml).

- build_matrix: enabled + connected channels -> [{"channel_id", "vpn_profile"}] (no names, no secrets).
  GitHub allows at most 256 jobs per matrix; with more channels a rotating window is used
  (offset = github.run_number) so every channel gets its turn.
- select_wg_secret: pick WG_CONF_<PROFILE> out of `toJSON(secrets)` and hand it to later steps through
  $GITHUB_ENV, after registering every line of it with ::add-mask:: so it can never appear in logs.
  The value itself is never printed.
"""
from __future__ import annotations

import json
import secrets as _secrets

from src.vpn.wireguard import env_var_for

GITHUB_MATRIX_MAX = 256


def build_matrix(channels: list[dict], max_jobs: int = GITHUB_MATRIX_MAX, offset: int = 0) -> tuple[list[dict], int]:
    """Returns (matrix include list, total eligible). Sorted by channel_id for stable windows."""
    max_jobs = max(1, min(GITHUB_MATRIX_MAX, int(max_jobs)))
    ok = sorted((c for c in channels if c.get("enabled") and c.get("auth_status") == "active"),
                key=lambda c: c["channel_id"])
    total = len(ok)
    if total > max_jobs:
        start = (int(offset) * max_jobs) % total
        ok = (ok[start:] + ok[:start])[:max_jobs]
    return [{"channel_id": c["channel_id"], "vpn_profile": c.get("vpn_profile") or ""} for c in ok], total


def mask_commands(value: str) -> list[str]:
    """::add-mask:: lines for a multi-line secret (GitHub masks per line; whole value + every line + every
    'Key = value' right-hand side)."""
    parts = set()
    for line in value.splitlines():
        line = line.strip()
        if not line:
            continue
        parts.add(line)
        if "=" in line:
            rhs = line.split("=", 1)[1].strip()
            if len(rhs) >= 4:
                parts.add(rhs)
    return [f"::add-mask::{p}" for p in sorted(parts, key=len, reverse=True)]


def select_wg_secret(secrets_json: str, profile: str) -> tuple[str, str | None]:
    """(env var name, value or None). Never raises on bad JSON (returns None)."""
    var = env_var_for(profile)
    try:
        data = json.loads(secrets_json or "{}")
    except ValueError:
        return var, None
    val = data.get(var) if isinstance(data, dict) else None
    return var, (val if isinstance(val, str) and val.strip() else None)


def github_env_block(var: str, value: str) -> str:
    """Multi-line $GITHUB_ENV entry with a random delimiter that cannot occur in the value."""
    while True:
        delim = "WG_EOF_" + _secrets.token_hex(16)
        if delim not in value:
            break
    return f"{var}<<{delim}\n{value.rstrip()}\n{delim}\n"
