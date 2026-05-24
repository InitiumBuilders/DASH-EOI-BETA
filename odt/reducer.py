"""odt.reducer — tree reduction over per-chunk summaries.

Merges children k-at-a-time up the tree. Each merge is one LLM call.
"""

from __future__ import annotations
import asyncio
import json
import math
from pathlib import Path
from typing import Any

import aiohttp

from . import worker as W


REDUCE_FANOUT = 4  # merge this many children per reducer call


def fmt_children(children: list[dict]) -> str:
    """Render children list as compact JSON array string for the prompt."""
    return json.dumps(children, ensure_ascii=False, indent=2)


async def reduce_pair_or_group(
    session: aiohttp.ClientSession,
    children: list[dict],
    task: str,
    reducer_template: str,
    *,
    host: str,
    model: str,
) -> dict:
    """Call the reducer on a group of children, return merged summary dict."""
    if len(children) == 1:
        return children[0]
    prompt = W.render(
        reducer_template,
        task=task,
        k=len(children),
        children=fmt_children(children),
    )
    result = await W.call_json(
        session,
        prompt,
        host=host,
        model=model,
        num_ctx=16384,
        timeout=180,
    )
    if not result.ok or result.parsed is None:
        # Degrade gracefully: pass through a union of facts and weights
        return _fallback_merge(children)
    merged = result.parsed
    # Ensure schema
    merged.setdefault("summary", "")
    merged.setdefault("key_facts", [])
    merged.setdefault("concerns", [])
    merged.setdefault("actions", [])
    merged.setdefault("systems", [])
    merged.setdefault("weight", max((c.get("weight", 1) for c in children), default=1))
    return merged


def _fallback_merge(children: list[dict]) -> dict:
    """If the reducer call fails, produce a best-effort union locally."""
    def collect(field: str) -> list:
        out: list = []
        seen = set()
        for c in children:
            for item in c.get(field, []) or []:
                if isinstance(item, str) and item not in seen:
                    seen.add(item)
                    out.append(item)
                elif not isinstance(item, str):
                    out.append(item)
        return out

    return {
        "summary": " | ".join((c.get("summary") or "")[:80] for c in children if c.get("summary"))[:600],
        "key_facts": collect("key_facts"),
        "concerns": ["[FALLBACK_MERGE] reducer failed"] + collect("concerns"),
        "actions": collect("actions"),
        "systems": collect("systems"),
        "weight": max((c.get("weight", 1) for c in children), default=1),
    }


async def tree_reduce(
    session: aiohttp.ClientSession,
    leaves: list[dict],
    task: str,
    reducer_template: str,
    *,
    host: str,
    model: str,
    fanout: int = REDUCE_FANOUT,
    out_dir: Path | None = None,
    on_progress=None,
) -> tuple[dict, list[list[dict]]]:
    """Reduce a list of summary dicts up to a single root via tree merging.

    Returns (root_dict, levels) where levels[0] = leaves, levels[-1] = [root].
    """
    levels: list[list[dict]] = [leaves]
    level_idx = 0
    while len(levels[-1]) > 1:
        current = levels[-1]
        # Group into chunks of `fanout`
        groups = [current[i : i + fanout] for i in range(0, len(current), fanout)]
        next_level: list[dict] = []
        for group_idx, group in enumerate(groups):
            merged = await reduce_pair_or_group(
                session, group, task, reducer_template, host=host, model=model
            )
            next_level.append(merged)
            if out_dir is not None:
                level_dir = out_dir / f"level_{level_idx + 1}"
                level_dir.mkdir(parents=True, exist_ok=True)
                (level_dir / f"merged_{group_idx:03d}.json").write_text(
                    json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            if on_progress:
                on_progress(level_idx + 1, group_idx + 1, len(groups))
        levels.append(next_level)
        level_idx += 1
        if level_idx > 10:
            # Safety: should never need more than log_fanout(N) levels
            break
    root = levels[-1][0]
    if out_dir is not None:
        (out_dir / "root.json").write_text(
            json.dumps(root, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return root, levels
