"""odt.status — one-command dashboard.

Usage: python -m odt.status
"""
from __future__ import annotations
import json
from pathlib import Path

from . import config as cfg
from . import quality as Q
from . import cache as CACHE
from . import tokenize as T


def fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def main():
    print("\033[1m═══ DASH-EOI status ═══\033[0m")
    C = cfg.CFG
    runs_dir = cfg.ROOT / "runs"
    lessons_dir = cfg.ROOT / "lessons"

    # Runtime
    print("\n\033[36m▸ Runtime\033[0m")
    print(f"  ROOT:           {cfg.ROOT}")
    print(f"  Ollama host:    {C.ollama_host}")
    print(f"  Model:          {C.model}")
    tok = T.info()
    print(f"  Tokenizer:      {tok['mode']}{' (configured: ' + tok['configured'] + ')' if tok['mode'] != tok['configured'] else ''}")
    print(f"  Concurrency:    {C.map_concurrency} workers")
    print(f"  Cache:          {'enabled' if C.map_cache_enabled else 'disabled'}")
    print(f"  Streaming reduce: {'on' if C.reduce_streaming else 'off'}")

    # Cache stats
    print("\n\033[36m▸ Cache\033[0m")
    cs = CACHE.stats()
    print(f"  Entries:        {cs['entries']}")
    print(f"  Size:           {fmt_bytes(cs.get('size_bytes', 0))}")

    # Quality
    print("\n\033[36m▸ Quality\033[0m")
    records = Q.load_records()
    if not records:
        print("  No judged runs yet.")
    else:
        floor = Q.compute_floor(records)
        trend = Q.trend(records)
        print(f"  Floor:          \033[1m{floor['floor']}/40\033[0m  (P50 of last {min(20, floor['count'])} runs)")
        print(f"  Stretch:        {floor['stretch']}/40  (P90)")
        print(f"  Trend:          {trend['trend']}  (recent {trend['recent_mean']} vs historical {trend['historical_mean']})")
        print(f"  Runs scored:    {floor['count']}")
        print("\n  Last 5:")
        for r in records[-5:]:
            v = r["verdict"]
            color = "\033[32m" if v == "outlier" else "\033[33m" if v == "competent" else "\033[31m"
            print(f"    {r['ts']}  {r['total']:>2}/40  {color}{v:<10}\033[0m  {r['task'][:55]}")

    # Runs
    if runs_dir.exists():
        runs = sorted(runs_dir.iterdir())
        print(f"\n\033[36m▸ Runs\033[0m  ({len(runs)} on disk)")
        for r in runs[-3:]:
            m = r / "manifest.json"
            if m.exists():
                try:
                    d = json.loads(m.read_text())
                    print(f"  {r.name}")
                    print(f"    class={d.get('class')}  chunks={d.get('chunks')}  wall={d.get('wall_time_s')}s")
                except Exception:
                    pass

    print()


if __name__ == "__main__":
    main()
