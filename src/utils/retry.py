"""Exponential backoff helper."""
import random
import time


def backoff_delays(max_retries: int = 5, base: float = 2.0, cap: float = 300.0):
    for attempt in range(1, max_retries + 1):
        yield min(cap, base ** attempt) * (0.5 + random.random() / 2)


def retry(fn, is_retryable, max_retries=5, sleep=time.sleep):
    last = None
    for delay in [0, *backoff_delays(max_retries)]:
        if delay:
            sleep(delay)
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            if not is_retryable(e):
                raise
            last = e
    raise last
