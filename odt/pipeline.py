"""odt.pipeline — Outlier-Deep-Think orchestrator (v1.1).

v1.1 changes vs v1.0:
  + Single source of truth in odt.config (env-overridable)
  + Streaming synthesis (Boss sees tokens live)
  + Resume support (--resume <run-id> picks up at the last incomplete stage)
  + LLM-as-judge review (replaces regex-only checks)
  + Collapse safety net for reduce-level overflow
  + Optional persona panel (--with critic,tester,...)
  + Stage gating that re-uses on-disk artifacts on resume

Pipeline stages (each writes files; any can be skipped on resume if complete):
  00 intake
  01 classify
  02 plan
  03 chunk
  04 map
  05 reduce
  06 synthesize
  07 review (LLM judge + regex)
  08 escalate?
  09 reflect
"""

from __future__ import annotations
import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import aiohttp

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from odt import chunker as C, worker as W, pool as P, reducer as R
    from odt import reflect as RF, escalate as E, collapse as CL
    from odt import judge as J, personas as PERS, config as CFG_MOD
    from odt import quality as Q
    from odt import streaming_reduce as SR, cache as CACHE
else:
    from . import chunker as C, worker as W, pool as P, reducer as R
    from . import reflect as RF, escalate as E, collapse as CL
    from . import judge as J, personas as PERS, config as CFG_MOD
    from . import quality as Q
    from . import streaming_reduce as SR, cache as CACHE


ROOT = CFG_MOD.ROOT
PROMPTS_DIR = ROOT / "odt" / "prompts"
RUNS_DIR = ROOT / "runs"
LESSONS_DIR = ROOT / "lessons"


def slugify(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower())[:60].strip()
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return s or "run"


def new_run_dir(task: str) -> Path:
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    rd = RUNS_DIR / f"{ts}__{slugify(task)}"
    rd.mkdir(parents=True, exist_ok=True)
    return rd


def resolve_input(task_or_path: str) -> tuple[str, str]:
    if task_or_path.startswith("@"):
        p = Path(task_or_path[1:]).expanduser()
        text = p.read_text(encoding="utf-8", errors="replace")
        return f"Analyze {p.name}", text
    return task_or_path[:120], task_or_path


def banner(s: str): print(f"\n\033[1;36m▸ {s}\033[0m", flush=True)
def info(s: str):   print(f"  {s}", flush=True)
def ok(s: str):     print(f"  \033[32m✓\033[0m {s}", flush=True)
def warn(s: str):   print(f"  \033[33m!\033[0m {s}", flush=True)


async def _stage_map(session, chunks, task, worker_tmpl, map_dir, cfg):
    async def map_one(ch: C.Chunk) -> dict:
        out_path = map_dir / f"summary_{ch.index:03d}.json"
        if out_path.exists():
            try:
                return json.loads(out_path.read_text())
            except Exception:
                pass
        prompt = W.render(
            worker_tmpl, task=task,
            chunk_index=ch.index, total_chunks=len(chunks),
            chunk_tokens=ch.token_count, chunk=ch.text,
        )
        res = await W.call_json(
            session, prompt,
            host=cfg.ollama_host, model=cfg.model,
            num_ctx=cfg.map_num_ctx, timeout=cfg.map_timeout_s,
            temperature=cfg.map_temperature, max_attempts=cfg.map_max_attempts,
        )
        summary = res.parsed if (res.ok and res.parsed) else {
            "summary": "", "key_facts": [],
            "concerns": [f"[WORKER_FAIL] {res.error or 'unknown'}"],
            "actions": [], "systems": [], "weight": 1,
        }
        summary.setdefault("chunk_index", ch.index)
        out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return summary

    def _on_progress(done, total, _res): info(f"map {done}/{total} done")
    return await P.run_pool(chunks, map_one, concurrency=cfg.map_concurrency, on_progress=_on_progress)


async def _stage_reduce_with_collapse(session, leaves, task, reducer_tmpl, reduce_dir, cfg):
    """Tree-reduce with collapse safety net at each level."""
    levels = [leaves]
    level_idx = 0
    while len(levels[-1]) > 1:
        current = levels[-1]
        # Collapse if combined size threatens next call's window
        budget = cfg.reduce_num_ctx - 2048   # leave room for prompt + response
        collapsed, did_collapse = await CL.collapse_if_needed(
            session, current, budget_tokens=budget,
            host=cfg.ollama_host, model=cfg.model,
        )
        if did_collapse:
            warn(f"reduce level {level_idx + 1}: collapsed {len(current)} children to fit window")
            current = collapsed

        groups = [current[i : i + cfg.reduce_fanout] for i in range(0, len(current), cfg.reduce_fanout)]
        next_level = []
        for group_idx, group in enumerate(groups):
            merged = await R.reduce_pair_or_group(
                session, group, task, reducer_tmpl,
                host=cfg.ollama_host, model=cfg.model,
            )
            next_level.append(merged)
            level_dir = reduce_dir / f"level_{level_idx + 1}"
            level_dir.mkdir(parents=True, exist_ok=True)
            (level_dir / f"merged_{group_idx:03d}.json").write_text(
                json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            info(f"reduce level {level_idx + 1} · merged {group_idx + 1}/{len(groups)}")
        levels.append(next_level)
        level_idx += 1
        if level_idx > 10:
            break
    root = levels[-1][0]
    (reduce_dir / "root.json").write_text(
        json.dumps(root, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return root, levels


async def _stage_synthesize(session, task, root, synth_tmpl, synth_dir, cfg):
    """Synthesize with optional streaming output."""
    synth_dir.mkdir(parents=True, exist_ok=True)
    out_path = synth_dir / "answer.md"
    if out_path.exists() and out_path.stat().st_size > 100:
        info("synthesis cached, skipping")
        return out_path.read_text(), 0.0

    prompt = W.render(
        synth_tmpl, task=task,
        constraints="(none specified by user)",
        digest=json.dumps(root, ensure_ascii=False, indent=2),
    )
    t0 = time.monotonic()

    if cfg.stream_synthesis:
        info("synthesizing (streaming)…")
        chunks_out: list[str] = []
        try:
            async for tok in W.call_stream(
                session, prompt,
                host=cfg.ollama_host, model=cfg.model,
                num_ctx=cfg.synth_num_ctx, timeout=cfg.synth_timeout_s,
                temperature=cfg.synth_temperature,
            ):
                chunks_out.append(tok)
                sys.stderr.write(tok)
                sys.stderr.flush()
            sys.stderr.write("\n")
        except Exception as e:
            warn(f"stream failed ({e}); falling back to non-streaming")
            res = await W.call_ollama(
                session, prompt,
                host=cfg.ollama_host, model=cfg.model,
                num_ctx=cfg.synth_num_ctx, timeout=cfg.synth_timeout_s,
                temperature=cfg.synth_temperature,
            )
            chunks_out = [res.text]
        text = W.strip_think_blocks("".join(chunks_out).strip())
    else:
        res = await W.call_ollama(
            session, prompt,
            host=cfg.ollama_host, model=cfg.model,
            num_ctx=cfg.synth_num_ctx, timeout=cfg.synth_timeout_s,
            temperature=cfg.synth_temperature,
        )
        text = res.text if res.ok else "(synthesis failed)"

    out_path.write_text(text, encoding="utf-8")
    return text, time.monotonic() - t0


async def _stage_review(session, task, root, answer, review_dir, cfg) -> dict:
    review_dir.mkdir(parents=True, exist_ok=True)
    # Deterministic checks
    flags = []
    SLOP_TERMS = ["delve into", "robust solution", "comprehensive overview",
                  "in conclusion", "tapestry", "navigate", "it is important to note"]
    for term in SLOP_TERMS:
        if term in answer.lower():
            flags.append(f"slop term: '{term}'")
    if len(answer) > cfg.synth_max_chars:
        flags.append(f"length {len(answer)} > {cfg.synth_max_chars} cap")
    if len(answer) < 100:
        flags.append(f"answer suspiciously short ({len(answer)} chars)")

    # LLM judge
    judge_verdict: dict[str, Any] = {}
    if cfg.judge_enabled:
        judge_verdict = await J.judge_answer(
            session, task=task, digest=root, answer=answer,
            host=cfg.ollama_host, model=cfg.model,
            num_ctx=cfg.judge_num_ctx, timeout=cfg.judge_timeout_s,
        )
    review = {
        "flags": flags,
        "length_chars": len(answer),
        "length_words": len(answer.split()),
        "judge": judge_verdict,
    }
    (review_dir / "review.json").write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    md_lines = ["# Review\n", f"- length: {review['length_chars']} chars, {review['length_words']} words"]
    if flags:
        md_lines.append("- flags:")
        md_lines.extend([f"  - {f}" for f in flags])
    if judge_verdict:
        md_lines.append("")
        md_lines.append(f"## Judge verdict: **{judge_verdict.get('verdict','?')}**  ({judge_verdict.get('total','?')}/40)")
        md_lines.append(f"- faithful: {judge_verdict.get('faithful','?')}/10")
        md_lines.append(f"- clear: {judge_verdict.get('clear','?')}/10")
        md_lines.append(f"- restrained: {judge_verdict.get('restrained','?')}/10")
        md_lines.append(f"- signal: {judge_verdict.get('signal','?')}/10")
        md_lines.append(f"- **top critique:** {judge_verdict.get('top_critique','—')}")
        md_lines.append(f"- **top strength:** {judge_verdict.get('top_strength','—')}")
    (review_dir / "review.md").write_text("\n".join(md_lines), encoding="utf-8")
    return review


async def run_pipeline(
    task_or_path: str,
    *,
    task_override: str | None = None,
    force_class: str | None = None,
    concurrency: int | None = None,
    with_personas: list[str] | None = None,
    resume_id: str | None = None,
):
    cfg = CFG_MOD.CFG
    if concurrency is not None:
        cfg.map_concurrency = concurrency

    t_start = time.monotonic()

    # ─── intake / resume resolution ──────────────────────────────────────
    if resume_id:
        run_dir = RUNS_DIR / resume_id
        if not run_dir.exists():
            print(f"ERROR: run id not found: {resume_id}", file=sys.stderr)
            sys.exit(2)
        input_text = (run_dir / "00_input.txt").read_text()
        task_one_liner = (run_dir / "00_task.txt").read_text().strip()
        print(f"\n\033[1m═══ ODT resume: {run_dir.name} ═══\033[0m")
    else:
        task_one_liner_default, input_text = resolve_input(task_or_path)
        task_one_liner = (task_override or task_one_liner_default).strip()
        run_dir = new_run_dir(task_one_liner)
        print(f"\n\033[1m═══ ODT v1.1 run: {run_dir.name} ═══\033[0m")
        (run_dir / "00_input.txt").write_text(input_text, encoding="utf-8")
        (run_dir / "00_task.txt").write_text(task_one_liner, encoding="utf-8")

    info(f"task: {task_one_liner}")
    info(f"runtime: model={cfg.model}  host={cfg.ollama_host}  concurrency={cfg.map_concurrency}")

    # ─── 01 classify ─────────────────────────────────────────────────────
    banner("01 classify")
    total_tokens = C.estimate_tokens(input_text)
    klass = force_class or C.classify_size(total_tokens)
    info(f"input ≈ {total_tokens:,} tokens → class={klass}")
    (run_dir / "01_intake").mkdir(exist_ok=True)
    (run_dir / "01_intake" / "classification.json").write_text(
        json.dumps({"tokens": total_tokens, "class": klass}, indent=2), encoding="utf-8"
    )

    # ─── 03 chunk ────────────────────────────────────────────────────────
    banner("03 chunk")
    chunks = C.chunk_text(
        input_text,
        target_tokens=cfg.target_tokens_per_chunk,
        overlap_tokens=cfg.overlap_tokens,
        hard_max_tokens=cfg.hard_max_tokens,
    )
    if len(chunks) > cfg.max_chunks:
        print(f"ERROR: {len(chunks)} chunks exceeds max_chunks cap ({cfg.max_chunks}). "
              f"Raise ODT_MAX_CHUNKS or split input.", file=sys.stderr)
        sys.exit(3)
    info(f"produced {len(chunks)} chunk(s) of type='{chunks[0].structural_type if chunks else 'n/a'}'")
    # Predict reduce-tree depth to warn early
    import math
    if len(chunks) > 1:
        depth = math.ceil(math.log(len(chunks), cfg.reduce_fanout))
        info(f"predicted reduce-tree depth: {depth} (fanout={cfg.reduce_fanout})")
        if depth >= cfg.deep_tree_warn_levels:
            warn(f"deep tree ({depth} levels) — wall time will scale; consider --concurrency 3+")
    chunk_dir = run_dir / "03_chunk"
    chunk_dir.mkdir(exist_ok=True)
    for ch in chunks:
        p = chunk_dir / f"chunk_{ch.index:03d}.txt"
        if not p.exists():
            p.write_text(ch.text, encoding="utf-8")

    async with aiohttp.ClientSession() as session:
        # ─── 04 map ──────────────────────────────────────────────────────
        banner("04 map")
        worker_tmpl = W.load_prompt_template("worker_v1", PROMPTS_DIR)
        map_dir = run_dir / "04_map"
        map_dir.mkdir(exist_ok=True)
        leaf_summaries = await _stage_map(session, chunks, task_one_liner, worker_tmpl, map_dir, cfg)
        dashei_calls = len(chunks)

        # ─── 05 reduce (with collapse + streaming) ───────────────────────
        banner("05 reduce")
        reducer_tmpl = W.load_prompt_template("reducer_v1", PROMPTS_DIR)
        reduce_dir = run_dir / "05_reduce"
        reduce_dir.mkdir(exist_ok=True)
        if cfg.reduce_streaming:
            def _sr_progress(stage, level, n):
                info(f"reduce level {level}: {stage} ({n})")
            root, levels = await SR.streaming_tree_reduce(
                session, leaf_summaries, task_one_liner, reducer_tmpl,
                host=cfg.ollama_host, model=cfg.model,
                fanout=cfg.reduce_fanout, out_dir=reduce_dir, on_progress=_sr_progress,
            )
        else:
            root, levels = await _stage_reduce_with_collapse(
                session, leaf_summaries, task_one_liner, reducer_tmpl, reduce_dir, cfg,
            )
        dashei_calls += sum(len(L) for L in levels[1:])
        info(f"reduced through {len(levels) - 1} merge level(s) → root.json")

        # ─── 06 synthesize ───────────────────────────────────────────────
        banner("06 synthesize")
        synth_tmpl = W.load_prompt_template("synthesizer_v1", PROMPTS_DIR)
        synth_dir = run_dir / "06_synthesize"
        answer, synth_wall = await _stage_synthesize(session, task_one_liner, root, synth_tmpl, synth_dir, cfg)
        dashei_calls += 1
        info(f"synthesis: {len(answer)} chars in {synth_wall:.1f}s")

        # ─── 06b personas (optional) ─────────────────────────────────────
        if with_personas:
            banner("06b persona panel")
            try:
                panel = await PERS.spawn_panel(
                    session, with_personas, target=answer,
                    host=cfg.ollama_host, model=cfg.model,
                    extra_context=f"TASK: {task_one_liner}\n\nDIGEST_SUMMARY: {root.get('summary','')[:600]}",
                    concurrency=cfg.map_concurrency,
                )
                dashei_calls += len(panel)
                pd = run_dir / "06_synthesize" / "support"
                pd.mkdir(exist_ok=True)
                for r in panel:
                    (pd / f"{r['persona']}.md").write_text(r["text"], encoding="utf-8")
                    ok(f"persona {r['persona']} done in {r['duration_s']:.1f}s")
            except Exception as e:
                warn(f"persona panel failed: {e}")

        # ─── 07 review ───────────────────────────────────────────────────
        banner("07 review")
        review = await _stage_review(session, task_one_liner, root, answer, run_dir / "07_review", cfg)
        if cfg.judge_enabled:
            dashei_calls += 1
        v = review.get("judge", {})
        if v:
            info(f"judge: {v.get('verdict','?')} ({v.get('total','?')}/40)")
            info(f"  top critique: {v.get('top_critique','')}")
        for f in review.get("flags", []):
            warn(f)

        # ─── 08 escalate? ────────────────────────────────────────────────
        banner("08 escalate?")
        should, why = E.should_escalate(
            klass=klass, refinement_loops=0, digest=root, forced=(force_class == "outlier"),
        )
        # Add judge-based escalation
        if v and v.get("total", 40) < cfg.judge_threshold * 4:
            should, why = True, f"judge total {v.get('total')}/40 below threshold"
        if should:
            packet_path = E.write_escalation_packet(
                run_dir,
                task_one_line=task_one_liner,
                specific_question=v.get("top_critique", "Validate root digest and synthesis."),
                what_dashei_tried="Map → tree-reduce with collapse → single-pass synthesis → LLM judge.",
                constraints=[],
            )
            warn(f"escalation packet: {packet_path.relative_to(ROOT)}")
            info(f"  reason: {why}")
        else:
            ok("no escalation triggered")

        # ─── 09 reflect ──────────────────────────────────────────────────
        banner("09 reflect")
        reflector_tmpl = W.load_prompt_template("reflector_v1", PROMPTS_DIR)
        wall = time.monotonic() - t_start
        lesson_path = await RF.write_lesson(
            session,
            run_dir=run_dir,
            task_one_liner=task_one_liner,
            klass=klass,
            n_chunks=len(chunks),
            wall_time_s=wall,
            dashei_calls=dashei_calls + 1,
            davara_calls=0,
            escalation_triggered=should,
            reflector_template=reflector_tmpl,
            host=cfg.ollama_host,
            model=cfg.model,
            lessons_dir=LESSONS_DIR,
            extra_context=f"Judge verdict: {json.dumps(v)}" if v else "",
        )
        ok(f"lesson: {lesson_path.relative_to(ROOT)}")

    # ─── manifest ────────────────────────────────────────────────────────
    manifest = {
        "version": "1.1",
        "run_id": run_dir.name,
        "task": task_one_liner,
        "class": klass,
        "input_tokens_est": total_tokens,
        "chunks": len(chunks),
        "dashei_calls": dashei_calls + 1,
        "wall_time_s": round(time.monotonic() - t_start, 1),
        "model": cfg.model,
        "host": cfg.ollama_host,
        "concurrency": cfg.map_concurrency,
        "judge": review.get("judge", {}),
        "escalated": should,
        "escalation_reason": why,
        "personas_invoked": with_personas or [],
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # Append to quality log + update floor
    if v:
        Q.append_record(run_dir.name, task_one_liner, klass, v, len(answer))
        floor = Q.compute_floor()
        info(f"quality floor now: {floor['floor']}/40  stretch: {floor['stretch']}/40")

    print(f"\n\033[1;32m═══ COMPLETE in {manifest['wall_time_s']}s ═══\033[0m")
    print(f"answer:    {run_dir / '06_synthesize' / 'answer.md'}")
    print(f"manifest:  {run_dir / 'manifest.json'}")
    print(f"lesson:    {run_dir / '09_reflect' / 'lesson.md'}")
    if v:
        print(f"score:     {v.get('total','?')}/40  ({v.get('verdict','?')})")
    return run_dir


def main():
    ap = argparse.ArgumentParser(prog="odt", description="Outlier-Deep-Think pipeline (v1.1)")
    ap.add_argument("task_or_path", nargs="?", help='Task or "@path"')
    ap.add_argument("--task", default=None, help="Override task one-liner when using @path")
    ap.add_argument("--class", dest="force_class", default=None,
                    choices=["small", "medium", "large", "outlier"])
    ap.add_argument("--concurrency", type=int, default=None)
    ap.add_argument("--with", dest="with_personas", default=None,
                    help="Comma-separated personas to invoke (critic,tester,refactorer,steelmanner,systems_mapper)")
    ap.add_argument("--resume", default=None, help="Run id to resume")
    args = ap.parse_args()

    if not args.task_or_path and not args.resume:
        ap.error("provide a task/path or --resume <id>")

    personas = [p.strip() for p in args.with_personas.split(",")] if args.with_personas else None

    asyncio.run(run_pipeline(
        args.task_or_path or "",
        task_override=args.task,
        force_class=args.force_class,
        concurrency=args.concurrency,
        with_personas=personas,
        resume_id=args.resume,
    ))


if __name__ == "__main__":
    main()
