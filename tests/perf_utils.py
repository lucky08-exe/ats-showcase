"""Shared helper for hardening wall-clock ``@pytest.mark.perf`` tests.

Pattern: warm up the exact callable under test (lazy-init/cache cost), then take
``repeats`` perf_counter samples and return the median.
"""

import statistics
import time
from collections.abc import Callable


def median_elapsed_ms(fn: Callable[[], object], repeats: int = 3, warmup: int = 1) -> float:
    """Return the median wall-clock time of ``fn()`` in milliseconds.

    Calls ``fn`` ``warmup`` times first (discarded), then ``repeats`` times, timing
    each call with ``time.perf_counter()``. ``fn`` takes no arguments and should do
    exactly the operation being budgeted.
    """
    for _ in range(warmup):
        fn()
    samples: list[float] = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    return statistics.median(samples)
