"""odt.cache — content-addressable cache for LLM calls.

Why this matters at scale:
  - At 1M+ tokens of input, the same chunk text can appear across runs
    (Boss iterates on prompts, swaps tasks, rerun similar inputs).
  - Identical (prompt, model, num_ctx, temperature) → identical output.
  - Cache hits cost: 0 tokens, 0ms (after disk read).
  - Cache miss: same as before.

Cache key = sha256(prompt + model + num_ctx + temperature)
Cache value = the JSON response from Ollama, stored as a file.

This is the difference between iterating on a 1M-token corpus once a day
(expensive) and iterating ten times an hour (free after the first).
"""

from __future__ import annotations
import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

from . import config as cfg


CACHE_DIR = cfg.ROOT / ".odt_cache"
CACHE_VERSION = 1


def _key(prompt: str, *, model: str, num_ctx: int, temperature: float) -> str:
    h = hashlib.sha256()
    h.update(f"v{CACHE_VERSION}\n".encode())
    h.update(f"model={model}\n".encode())
    h.update(f"ctx={num_ctx}\n".encode())
    h.update(f"temp={temperature:.3f}\n".encode())
    h.update(prompt.encode("utf-8"))
    return h.hexdigest()


def _cache_path(key: str) -> Path:
    # Shard by first 2 chars so we don't blow up a single dir
    return CACHE_DIR / key[:2] / f"{key}.json"


def get(prompt: str, *, model: str, num_ctx: int, temperature: float) -> dict | None:
    if not cfg.CFG.map_cache_enabled:
        return None
    k = _key(prompt, model=model, num_ctx=num_ctx, temperature=temperature)
    p = _cache_path(k)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def put(prompt: str, value: dict, *, model: str, num_ctx: int, temperature: float) -> None:
    if not cfg.CFG.map_cache_enabled:
        return
    k = _key(prompt, model=model, num_ctx=num_ctx, temperature=temperature)
    p = _cache_path(k)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "key": k,
        "model": model,
        "num_ctx": num_ctx,
        "temperature": temperature,
        "value": value,
    }
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def stats() -> dict:
    """Return cache size + entry count."""
    if not CACHE_DIR.exists():
        return {"entries": 0, "size_bytes": 0}
    n = 0
    s = 0
    for p in CACHE_DIR.rglob("*.json"):
        n += 1
        try:
            s += p.stat().st_size
        except OSError:
            pass
    return {"entries": n, "size_bytes": s, "path": str(CACHE_DIR)}


def clear() -> int:
    """Wipe the cache. Returns count of entries removed."""
    if not CACHE_DIR.exists():
        return 0
    n = 0
    for p in CACHE_DIR.rglob("*.json"):
        try:
            p.unlink()
            n += 1
        except OSError:
            pass
    return n
