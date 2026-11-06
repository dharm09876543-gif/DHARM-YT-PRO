"""Logging that hides secrets."""
import logging
import re

_SECRET_PATTERNS = [
    re.compile(r"ya29\.[\w\-.]+"),                 # Google access token
    re.compile(r"1//[\w\-]+"),                     # Google refresh token
    re.compile(r"(?i)(privatekey\s*=\s*)\S+"),     # WireGuard
    re.compile(r"(?i)(password|secret|token)=([^&\s]+)"),
]


def redact(text: str) -> str:
    for p in _SECRET_PATTERNS:
        text = p.sub(lambda m: (m.group(1) if m.lastindex else "") + "***", text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record):
        record.msg = redact(str(record.msg))
        return True


def get_logger(name: str = "dharm_yt") -> logging.Logger:
    log = logging.getLogger(name)
    if not log.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        h.addFilter(RedactingFilter())
        log.addHandler(h)
        log.setLevel(logging.INFO)
    return log
