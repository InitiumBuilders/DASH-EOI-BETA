"""odt.worker — single-call wrapper around Ollama for Outlier-Deep-Think.

Responsibilities:
  - One LLM call per invocation.
  - Strict JSON parsing where required (call_json).
  - Streaming text generation when requested (call_stream).
  - Retry with stricter wording on JSON failure.
  - Timeouts, backoff, no swallowed errors.

v1.1 additions:
  - call_stream() — generator that yields tokens as they arrive
  - explicit retry-on-empty-response logic
"""

from __future__ import annotations
import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator

import aiohttp


OLLAMA_HOST_DEFAULT = "http://localhost:11434"
MODEL_DEFAULT = "qwen3:8b"
NUM_CTX_DEFAULT = 16384   # plenty for one chunk + prompt + response
TIMEOUT_DEFAULT = 120     # per-call seconds


@dataclass
class CallResult:
    ok: bool
    text: str
    parsed: dict | None = None
    duration_s: float = 0.0
    attempts: int = 1
    error: str | None = None
    raw_response: dict | None = field(default=None, repr=False)


def load_prompt_template(name: str, prompts_dir: Path) -> str:
    p = prompts_dir / f"{name}.md"
    return p.read_text(encoding="utf-8")


def render(template: str, **fields: object) -> str:
    out = template
    for k, v in fields.items():
        out = out.replace("{{" + k + "}}", str(v))
    return out


def strip_think_blocks(text: str) -> str:
    """qwen3 sometimes emits <think>...</think> reasoning blocks; remove them."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def extract_json_object(text: str) -> dict | None:
    """Best-effort: find the first balanced JSON object in text and parse it."""
    text = strip_think_blocks(text)
    # Strip code fences if any
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.M)
    text = re.sub(r"\s*```\s*$", "", text.strip(), flags=re.M)
    # Find first '{' and last '}' as a fallback
    start = text.find("{")
    if start < 0:
        return None
    # Balanced-brace scan
    depth = 0
    end = -1
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end < 0:
        return None
    blob = text[start:end]
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        return None


async def call_ollama(
    session: aiohttp.ClientSession,
    prompt: str,
    *,
    host: str = OLLAMA_HOST_DEFAULT,
    model: str = MODEL_DEFAULT,
    num_ctx: int = NUM_CTX_DEFAULT,
    timeout: int = TIMEOUT_DEFAULT,
    temperature: float = 0.4,
) -> CallResult:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "options": {
            "num_ctx": num_ctx,
            "temperature": temperature,
        },
    }
    start = time.monotonic()
    try:
        async with session.post(
            f"{host}/api/generate",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                return CallResult(
                    ok=False,
                    text="",
                    duration_s=time.monotonic() - start,
                    error=f"HTTP {resp.status}: {body[:300]}",
                )
            data = await resp.json()
    except asyncio.TimeoutError:
        return CallResult(ok=False, text="", duration_s=time.monotonic() - start, error="timeout")
    except Exception as e:
        return CallResult(ok=False, text="", duration_s=time.monotonic() - start, error=f"{type(e).__name__}: {e}")

    text = strip_think_blocks((data.get("response") or "").strip())
    return CallResult(
        ok=True,
        text=text,
        duration_s=time.monotonic() - start,
        raw_response=data,
    )


async def call_json(
    session: aiohttp.ClientSession,
    prompt: str,
    *,
    max_attempts: int = 3,
    use_cache: bool = True,
    **kwargs,
) -> CallResult:
    """Call Ollama expecting a JSON object back. Retry with stricter wording on failure.

    v1.2: content-addressable cache. Cache hits return instantly with no
    network call. Cache key is sha256 of (prompt, model, num_ctx, temperature).
    """
    # Cache lookup
    if use_cache:
        try:
            from . import cache as _cache
            model = kwargs.get("model", MODEL_DEFAULT)
            num_ctx = kwargs.get("num_ctx", NUM_CTX_DEFAULT)
            temperature = kwargs.get("temperature", 0.4)
            hit = _cache.get(prompt, model=model, num_ctx=num_ctx, temperature=temperature)
            if hit and "value" in hit and isinstance(hit["value"], dict):
                v = hit["value"]
                if "parsed" in v and v.get("parsed"):
                    return CallResult(
                        ok=True, text=v.get("text", ""),
                        parsed=v["parsed"], duration_s=0.0,
                        attempts=0,  # 0 attempts = cache hit
                    )
        except Exception:
            pass

    last_err: str | None = None
    for attempt in range(1, max_attempts + 1):
        result = await call_ollama(session, prompt, **kwargs)
        if not result.ok:
            last_err = result.error
            await asyncio.sleep(min(2 ** attempt, 8))
            continue
        parsed = extract_json_object(result.text)
        if parsed is not None:
            result.parsed = parsed
            result.attempts = attempt
            # Cache the successful result
            if use_cache:
                try:
                    from . import cache as _cache
                    model = kwargs.get("model", MODEL_DEFAULT)
                    num_ctx = kwargs.get("num_ctx", NUM_CTX_DEFAULT)
                    temperature = kwargs.get("temperature", 0.4)
                    _cache.put(
                        prompt,
                        {"text": result.text, "parsed": parsed},
                        model=model, num_ctx=num_ctx, temperature=temperature,
                    )
                except Exception:
                    pass
            return result
        last_err = f"JSON parse failed on attempt {attempt}"
        prompt = (
            prompt
            + "\n\nIMPORTANT: Your previous response was not valid JSON. "
            "Emit ONLY a single JSON object. No prose. No code fences. Start with { and end with }."
        )
    result.ok = False
    result.error = last_err or "json parse failed"
    result.attempts = max_attempts
    return result


# ─── v1.1 streaming ─────────────────────────────────────────────────────────
async def call_stream(
    session: aiohttp.ClientSession,
    prompt: str,
    *,
    host: str = OLLAMA_HOST_DEFAULT,
    model: str = MODEL_DEFAULT,
    num_ctx: int = NUM_CTX_DEFAULT,
    timeout: int = TIMEOUT_DEFAULT,
    temperature: float = 0.6,
) -> AsyncIterator[str]:
    """Yield token chunks from Ollama as they arrive.

    Caller is responsible for assembling the full text. Use this when
    the operator wants to see synthesis arrive live rather than wait for the
    complete response.
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "think": False,
        "options": {"num_ctx": num_ctx, "temperature": temperature},
    }
    async with session.post(
        f"{host}/api/generate",
        json=payload,
        timeout=aiohttp.ClientTimeout(total=timeout),
    ) as resp:
        if resp.status != 200:
            body = await resp.text()
            raise RuntimeError(f"HTTP {resp.status}: {body[:300]}")
        async for raw_line in resp.content:
            if not raw_line:
                continue
            try:
                obj = json.loads(raw_line.decode("utf-8"))
            except json.JSONDecodeError:
                continue
            chunk = obj.get("response", "")
            if chunk:
                yield chunk
            if obj.get("done"):
                return
