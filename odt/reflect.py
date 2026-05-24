"""odt.reflect — post-run reflection writer.

Writes a lesson markdown file capturing what worked, what struggled,
proposed prompt mutations, and open questions for Davara.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any

import aiohttp

from . import worker as W


async def write_lesson(
    session: aiohttp.ClientSession,
    *,
    run_dir: Path,
    task_one_liner: str,
    klass: str,
    n_chunks: int,
    wall_time_s: float,
    dashei_calls: int,
    davara_calls: int,
    escalation_triggered: bool,
    reflector_template: str,
    host: str,
    model: str,
    lessons_dir: Path,
    extra_context: str = "",
) -> Path:
    run_id = run_dir.name

    # Build a compact run_data summary for the reflector prompt.
    run_data = {
        "run_id": run_id,
        "task": task_one_liner,
        "class": klass,
        "n_chunks": n_chunks,
        "wall_time_seconds": round(wall_time_s, 1),
        "dashei_calls": dashei_calls,
        "davara_calls": davara_calls,
        "escalation_triggered": escalation_triggered,
    }

    prompt = W.render(
        reflector_template,
        run_id=run_id,
        task_one_liner=task_one_liner,
        klass=klass,
        n_chunks=n_chunks,
        wall_time_seconds=round(wall_time_s, 1),
        dashei_calls=dashei_calls,
        davara_calls=davara_calls,
        escalation_triggered=str(escalation_triggered).lower(),
        worker_v="1",
        reducer_v="1",
        synth_v="1",
        run_data=json.dumps(run_data, ensure_ascii=False, indent=2) + ("\n\n" + extra_context if extra_context else ""),
    )

    result = await W.call_ollama(
        session, prompt, host=host, model=model, num_ctx=8192, timeout=120, temperature=0.5
    )
    lesson_text = result.text if result.ok else _fallback_lesson(run_id, task_one_liner, klass, n_chunks, wall_time_s)

    out_dir = run_dir / "09_reflect"
    out_dir.mkdir(parents=True, exist_ok=True)
    lesson_path = out_dir / "lesson.md"
    lesson_path.write_text(lesson_text, encoding="utf-8")

    # Mirror to the global lessons folder for fast scanning.
    lessons_dir.mkdir(parents=True, exist_ok=True)
    mirror = lessons_dir / f"{run_id}.md"
    mirror.write_text(lesson_text, encoding="utf-8")
    return lesson_path


def _fallback_lesson(run_id, task, klass, n_chunks, wall_time_s) -> str:
    return f"""# Lesson — Run {run_id}

## Task
{task}

## Stats
- Class: {klass}
- Chunks: {n_chunks}
- Wall time: {wall_time_s:.1f}s
- Reflector call failed; this is the fallback template.

## What worked
(reflector unavailable — manual review required)

## What struggled
Reflector LLM call failed — investigate Ollama availability or prompt structure.

## Prompt mutations to try next time
- reflector_v1.md: simplify and shorten if model can't produce on first call.

## Open questions for Davara
- Was the reflector prompt too dense for an 8B context?
"""
