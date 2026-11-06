"""Classify Google API errors: retryable, quota, or permanent."""
from __future__ import annotations

import json
import socket

RETRYABLE_STATUS = {500, 502, 503, 504}
QUOTA_REASONS = {"quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded", "userRateLimitExceeded"}
CHANNEL_LIMIT_REASONS = {"uploadLimitExceeded"}


def http_status(e) -> int | None:
    resp = getattr(e, "resp", None)
    st = getattr(resp, "status", None)
    try:
        return int(st) if st is not None else None
    except (TypeError, ValueError):
        return None


def error_reasons(e) -> set[str]:
    content = getattr(e, "content", b"") or b""
    try:
        data = json.loads(content.decode() if isinstance(content, bytes) else content)
        err = data.get("error", {})
        reasons = {x.get("reason") for x in err.get("errors", []) if x.get("reason")}
        for d in err.get("details", []) or []:
            if d.get("reason"):
                reasons.add(d["reason"])
        return reasons
    except (ValueError, AttributeError):
        return set()


def is_retryable(e: Exception) -> bool:
    if isinstance(e, (TimeoutError, socket.timeout, ConnectionError)):
        return True
    try:
        import httplib2
        if isinstance(e, httplib2.HttpLib2Error):
            return True
    except ImportError:  # pragma: no cover
        pass
    st = http_status(e)
    if st in RETRYABLE_STATUS:
        return True
    return st == 429 and not (error_reasons(e) & {"quotaExceeded", "dailyLimitExceeded"})


def is_quota_exceeded(e: Exception) -> bool:
    return http_status(e) in (403, 429) and bool(error_reasons(e) & {"quotaExceeded", "dailyLimitExceeded"})


def is_channel_limit(e: Exception) -> bool:
    return bool(error_reasons(e) & CHANNEL_LIMIT_REASONS)


def is_session_gone(e: Exception) -> bool:
    """Resumable session expire/invalid (404/410) - a new session is needed (after reconcile)."""
    return http_status(e) in (404, 410)
