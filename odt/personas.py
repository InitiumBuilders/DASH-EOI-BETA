"""odt.personas — runtime invocation of specialist support agents.

Personas live as prompt files in odt/personas/*.md. This module loads
them on demand and runs them as additional LLM calls — either alone or
in parallel via the pool.

v1.1 supports five built-in personas:
  critic        — adversarial review
  tester        — produce test case list
  refactorer    — shape-only refactors
  steelmanner   — argue the option not picked
  systems_mapper — Meadows leverage analysis
"""

from __future__ import annotations
import asyncio
from pathlib import Path

import aiohttp

from . import worker as W
from . import pool as P


PERSONAS_DIR = Path(__file__).parent / "personas"
AVAILABLE = ["critic", "tester", "refactorer", "steelmanner", "systems_mapper"]


def load_persona(name: str) -> str:
    p = PERSONAS_DIR / f"{name}.md"
    if not p.exists():
        raise FileNotFoundError(f"persona '{name}' not found at {p}")
    return p.read_text(encoding="utf-8")


async def invoke_persona(
    session: aiohttp.ClientSession,
    name: str,
    target: str,
    *,
    host: str,
    model: str,
    extra_context: str = "",
    num_ctx: int = 12288,
    timeout: int = 120,
) -> dict:
    """Invoke one persona against `target` (a code blob, draft answer, etc.).

    Returns {persona, text, duration_s, ok, error}.
    """
    persona_prompt = load_persona(name)
    full = f"{persona_prompt}\n\nCONTEXT:\n{extra_context}\n\nTARGET:\n{target}"
    res = await W.call_ollama(
        session, full, host=host, model=model,
        num_ctx=num_ctx, timeout=timeout, temperature=0.5,
    )
    return {
        "persona": name,
        "text": res.text,
        "duration_s": res.duration_s,
        "ok": res.ok,
        "error": res.error,
    }


async def spawn_panel(
    session: aiohttp.ClientSession,
    personas: list[str],
    target: str,
    *,
    host: str,
    model: str,
    extra_context: str = "",
    concurrency: int = 2,
) -> list[dict]:
    """Run multiple personas concurrently against the same target.

    The classic 'council of perspectives' pattern. Returns a list of
    persona result dicts, one per requested persona.
    """
    invalid = [p for p in personas if p not in AVAILABLE]
    if invalid:
        raise ValueError(f"unknown personas: {invalid}. available: {AVAILABLE}")

    async def _run(name: str) -> dict:
        return await invoke_persona(
            session, name, target, host=host, model=model, extra_context=extra_context,
        )

    return await P.run_pool(personas, _run, concurrency=concurrency)
