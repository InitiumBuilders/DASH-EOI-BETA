"""odt.pool — bounded async parallel pool for Outlier-Deep-Think.

Runs N concurrent workers against Ollama. Preserves input order in output.
Each task is a coroutine; the pool just bounds concurrency.
"""

from __future__ import annotations
import asyncio
from typing import Awaitable, Callable, TypeVar


T = TypeVar("T")
R = TypeVar("R")


async def run_pool(
    items: list[T],
    work: Callable[[T], Awaitable[R]],
    *,
    concurrency: int = 2,
    on_progress: Callable[[int, int, R], None] | None = None,
) -> list[R]:
    """Run `work(item)` for each item with at most `concurrency` in flight.

    Returns results in the same order as items.
    """
    sem = asyncio.Semaphore(max(1, concurrency))
    results: list[R | None] = [None] * len(items)
    done_count = 0
    lock = asyncio.Lock()

    async def _run(i: int, item: T):
        nonlocal done_count
        async with sem:
            res = await work(item)
        results[i] = res
        async with lock:
            done_count += 1
            if on_progress:
                on_progress(done_count, len(items), res)

    await asyncio.gather(*[_run(i, it) for i, it in enumerate(items)])
    return [r for r in results]  # type: ignore[misc]
