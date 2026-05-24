"""odt.evolve — A/B prompt mutation runner.

Lessons propose prompt mutations. This module tests them.

Strategy:
  1. the operator (or DashEI) writes worker_v2.md (or any _vN+1 variant).
  2. evolve.compare(run_id, prompt_name) replays the same input through both
     versions and scores them via the LLM judge.
  3. The winner gets a "PROMOTED" marker and v(N+1) becomes the active prompt.

This is the closed-loop evolution mechanism that makes ODT exponential.
"""

from __future__ import annotations
import asyncio
import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

import aiohttp

from . import config as cfg
from . import judge as J
from . import worker as W


PROMPTS_DIR = cfg.ROOT / "odt" / "prompts"
EVOLUTION_LOG = cfg.ROOT / "lessons" / "_evolution.jsonl"


@dataclass
class TrialResult:
    prompt_version: str
    judge_total: int
    verdict: str
    wall_time_s: float
    answer_chars: int


async def _run_synthesis_only(
    session: aiohttp.ClientSession,
    *, task: str, digest: dict, prompt_text: str,
    host: str, model: str,
    num_ctx: int, timeout: int,
) -> tuple[str, float]:
    """Run only the synthesizer step with a given prompt template.

    Used so A/B doesn't have to re-run map+reduce on the same input.
    """
    prompt = (
        prompt_text
        .replace("{{task}}", task)
        .replace("{{constraints}}", "(none)")
        .replace("{{digest}}", json.dumps(digest, ensure_ascii=False, indent=2))
    )
    t0 = time.monotonic()
    res = await W.call_ollama(
        session, prompt, host=host, model=model,
        num_ctx=num_ctx, timeout=timeout, temperature=0.6,
    )
    return (res.text if res.ok else ""), time.monotonic() - t0


async def compare_synth(run_id: str, challenger: str) -> dict:
    """Replay synthesis through the active synthesizer prompt AND a challenger.

    `challenger` is the basename of the prompt file under odt/prompts/
    (without .md), e.g. 'synthesizer_v2'.

    Returns a verdict dict and appends to lessons/_evolution.jsonl.
    """
    C = cfg.CFG
    run_dir = cfg.ROOT / "runs" / run_id
    digest_path = run_dir / "05_reduce" / "root.json"
    task_path = run_dir / "00_task.txt"
    if not digest_path.exists() or not task_path.exists():
        raise FileNotFoundError(f"run {run_id} missing required artifacts")
    digest = json.loads(digest_path.read_text())
    task = task_path.read_text().strip()

    active_path = PROMPTS_DIR / "synthesizer_v1.md"
    challenger_path = PROMPTS_DIR / f"{challenger}.md"
    if not challenger_path.exists():
        raise FileNotFoundError(f"challenger {challenger_path} missing")

    active_tmpl = active_path.read_text()
    challenger_tmpl = challenger_path.read_text()

    async with aiohttp.ClientSession() as session:
        ans_a, wall_a = await _run_synthesis_only(
            session, task=task, digest=digest, prompt_text=active_tmpl,
            host=C.ollama_host, model=C.model,
            num_ctx=C.synth_num_ctx, timeout=C.synth_timeout_s,
        )
        ans_b, wall_b = await _run_synthesis_only(
            session, task=task, digest=digest, prompt_text=challenger_tmpl,
            host=C.ollama_host, model=C.model,
            num_ctx=C.synth_num_ctx, timeout=C.synth_timeout_s,
        )
        verdict_a = await J.judge_answer(
            session, task=task, digest=digest, answer=ans_a,
            host=C.ollama_host, model=C.model,
            num_ctx=C.judge_num_ctx, timeout=C.judge_timeout_s,
        )
        verdict_b = await J.judge_answer(
            session, task=task, digest=digest, answer=ans_b,
            host=C.ollama_host, model=C.model,
            num_ctx=C.judge_num_ctx, timeout=C.judge_timeout_s,
        )

    a = TrialResult("synthesizer_v1", verdict_a["total"], verdict_a["verdict"], wall_a, len(ans_a))
    b = TrialResult(challenger, verdict_b["total"], verdict_b["verdict"], wall_b, len(ans_b))
    winner = "challenger" if b.judge_total > a.judge_total else "active" if a.judge_total > b.judge_total else "tie"

    record = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "run_id": run_id,
        "active": {"prompt": a.prompt_version, "total": a.judge_total, "verdict": a.verdict,
                   "wall_s": round(a.wall_time_s, 1), "chars": a.answer_chars,
                   "critique": verdict_a.get("top_critique", "")},
        "challenger": {"prompt": b.prompt_version, "total": b.judge_total, "verdict": b.verdict,
                       "wall_s": round(b.wall_time_s, 1), "chars": b.answer_chars,
                       "critique": verdict_b.get("top_critique", "")},
        "winner": winner,
    }
    EVOLUTION_LOG.parent.mkdir(parents=True, exist_ok=True)
    with EVOLUTION_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # Save both answers for inspection
    out = run_dir / "_evolution" / challenger
    out.mkdir(parents=True, exist_ok=True)
    (out / "active_answer.md").write_text(ans_a, encoding="utf-8")
    (out / "challenger_answer.md").write_text(ans_b, encoding="utf-8")
    (out / "verdict.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def promote(challenger: str, *, replace: str = "synthesizer_v1") -> Path:
    """Mark a challenger prompt as the new active version.

    We don't overwrite v1; we rename and bump. This preserves history.
    """
    src = PROMPTS_DIR / f"{challenger}.md"
    if not src.exists():
        raise FileNotFoundError(src)
    # Move the current active to _retired/
    retired = PROMPTS_DIR / "_retired"
    retired.mkdir(exist_ok=True)
    cur = PROMPTS_DIR / f"{replace}.md"
    if cur.exists():
        shutil.move(str(cur), str(retired / f"{replace}_{int(time.time())}.md"))
    shutil.copy(str(src), str(cur))
    return cur


def _cli():
    import argparse
    ap = argparse.ArgumentParser(prog="odt-evolve")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compare", help="A/B a challenger prompt against the active one")
    c.add_argument("run_id")
    c.add_argument("challenger", help="prompt basename, e.g. synthesizer_v2")
    p = sub.add_parser("promote", help="promote a challenger to active")
    p.add_argument("challenger")
    p.add_argument("--replace", default="synthesizer_v1")
    args = ap.parse_args()

    if args.cmd == "compare":
        rec = asyncio.run(compare_synth(args.run_id, args.challenger))
        print(json.dumps(rec, indent=2))
    elif args.cmd == "promote":
        path = promote(args.challenger, replace=args.replace)
        print(f"promoted: {path}")


if __name__ == "__main__":
    _cli()
