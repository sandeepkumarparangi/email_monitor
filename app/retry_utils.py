from __future__ import annotations

import functools
import logging
import time
from typing import Callable, Iterable, Tuple, Type


def with_retry(
    retries: int = 3,
    initial_delay_seconds: float = 1.0,
    backoff_factor: float = 2.0,
    retry_exceptions: Tuple[Type[BaseException], ...] = (Exception,),
) -> Callable:
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay_seconds
            last_error: BaseException | None = None
            for attempt in range(1, retries + 1):
                try:
                    return func(*args, **kwargs)
                except retry_exceptions as exc:
                    last_error = exc
                    logging.warning(
                        "Retryable error in %s attempt=%s/%s error=%s",
                        func.__name__,
                        attempt,
                        retries,
                        exc,
                    )
                    if attempt < retries:
                        time.sleep(delay)
                        delay *= backoff_factor
            raise RuntimeError(f"Failed after {retries} retries in {func.__name__}") from last_error

        return wrapper

    return decorator

