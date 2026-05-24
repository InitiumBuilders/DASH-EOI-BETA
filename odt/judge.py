"""odt.judge — LLM-as-judge quality scorer.

After synthesis, ask the model to score the draft on 4 axes:
  - faithful   : every claim is supported by the digest
  - clear      : a tired reader gets the takeaway in 30s
  - restrained : no filler, no slop, no padding
  - signal     : the answer surprises with insight, not just summary

Each axis: 0-10. Total: 0-40. We flag for escalation when total < threshold*4.
We deliberately ask a different temperature/persona than the synthesizer to
reduce same-model bias (the "use a different voice to grade your own work"
trick from constitutional AI).
"""

from __future__ import annotations
import json
from pathlib import Path

import aiohttp

from . import worker as W


JUDGE_PROMPT = """You are an outlier-tier reviewer. You did NOT write the answer below — you are judging it.

Score the answer on four axes, 0-10 each. Be honest. Be exacting. Outlier work earns 9-10; competent work earns 6-8; slop earns 0-5.

Axes:
  faithful   : every factual claim is grounded in the digest
  clear      : a tired reader gets the takeaway in 30 seconds
  restrained : no filler, no AI slop, no decorative bullets, no "in conclusion"
  signal     : the answer surprises with insight, not just summarizes the input

Output JSON only. No prose. No code fences. Schema:
{
  "faithful": <int 0-10>,
  "clear": <int 0-10>,
  "restrained": <int 0-10>,
  "signal": <int 0-10>,
  "total": <int 0-40>,
  "verdict": "outlier" | "competent" | "needs_work",
  "top_critique": "<one sentence: the single sharpest critique>",
  "top_strength": "<one sentence: the single strongest thing about this answer>"
}

TASK:
{{task}}

DIGEST (what the answer was built from):
{{digest}}

ANSWER (the work being judged):
{{answer}}
"""


async def judge_answer(
    session: aiohttp.ClientSession,
    *,
    task: str,
    digest: dict,
    answer: str,
    host: str,
    model: str,
    num_ctx: int = 8192,
    timeout: int = 60,
) -> dict:
    """Return the judge's verdict dict. Fallback to a neutral verdict on failure."""
    # Compact digest to fit in judge window
    compact = {
        "summary": digest.get("summary", "")[:600],
        "key_facts": (digest.get("key_facts") or [])[:10],
        "concerns": digest.get("concerns", []),
    }
    prompt = (
        JUDGE_PROMPT.replace("{{task}}", task[:500])
        .replace("{{digest}}", json.dumps(compact, ensure_ascii=False, indent=2))
        .replace("{{answer}}", answer[:6000])
    )
    res = await W.call_json(
        session, prompt, host=host, model=model,
        num_ctx=num_ctx, timeout=timeout, temperature=0.2,  # cooler for grading
    )
    if not res.ok or not res.parsed:
        return {
            "faithful": 5, "clear": 5, "restrained": 5, "signal": 5, "total": 20,
            "verdict": "needs_work",
            "top_critique": "Judge unavailable; manual review needed.",
            "top_strength": "(judge failed)",
            "_error": res.error,
        }
    v = res.parsed
    # Sanity: ensure total matches axes
    axes = ["faithful", "clear", "restrained", "signal"]
    for a in axes:
        v.setdefault(a, 0)
        v[a] = max(0, min(10, int(v[a] or 0)))
    v["total"] = sum(v[a] for a in axes)
    if "verdict" not in v:
        v["verdict"] = (
            "outlier" if v["total"] >= 32 else
            "competent" if v["total"] >= 24 else
            "needs_work"
        )
    return v
