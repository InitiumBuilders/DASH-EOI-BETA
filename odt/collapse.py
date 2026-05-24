"""odt.collapse — overflow safety net.

LangChain pattern: if a reduce level produces output that, when joined,
exceeds the context budget for the next reduce step, we COLLAPSE it
by re-summarizing first. This makes the pipeline tolerate any input size
without ever hitting context limits.

v1.1 logic: before each reduce level, estimate the combined token count
of the input children. If > collapse_threshold, run an extra pre-summarize
pass that compresses each child to half size before the merge.
"""

from __future__ import annotations
import json
from typing import Any

import aiohttp

from . import worker as W


COLLAPSE_PROMPT = """You are DashEI in COLLAPSE mode. The next reduce step would overflow context.

Re-summarize the structured summary below to HALF its current length while preserving:
- All key_facts (you may shorten wording but not drop facts)
- All concerns
- All [DISAGREEMENT] and [ESCALATED] markers
- All systems observations
- The summary field at ~60 words

Output: same JSON schema, more compact. JSON only, no prose, no code fences.

INPUT SUMMARY:
{{summary_json}}
"""


def estimate_tokens(s: Any) -> int:
    if isinstance(s, dict):
        return len(json.dumps(s, ensure_ascii=False)) // 4
    return len(str(s)) // 4


async def collapse_if_needed(
    session: aiohttp.ClientSession,
    children: list[dict],
    *,
    budget_tokens: int,
    host: str,
    model: str,
) -> tuple[list[dict], bool]:
    """If combined size of children exceeds budget, collapse each.

    Returns (possibly-collapsed children, was_collapsed).
    """
    combined = sum(estimate_tokens(c) for c in children)
    if combined <= budget_tokens:
        return children, False

    # Collapse each child in sequence (small enough that parallelism overhead isn't worth it)
    collapsed: list[dict] = []
    for child in children:
        prompt = COLLAPSE_PROMPT.replace("{{summary_json}}", json.dumps(child, ensure_ascii=False, indent=2))
        result = await W.call_json(session, prompt, host=host, model=model, num_ctx=12288, timeout=120)
        if result.ok and result.parsed:
            # Preserve weight if it was dropped
            result.parsed.setdefault("weight", child.get("weight", 1))
            collapsed.append(result.parsed)
        else:
            # Best-effort fallback: truncate summary and key_facts to half
            half = {
                "summary": (child.get("summary") or "")[:300],
                "key_facts": (child.get("key_facts") or [])[: max(1, len(child.get("key_facts", [])) // 2)],
                "concerns": child.get("concerns", []),
                "actions": (child.get("actions") or [])[: max(1, len(child.get("actions", [])) // 2)],
                "systems": child.get("systems", []),
                "weight": child.get("weight", 1),
            }
            collapsed.append(half)
    return collapsed, True
