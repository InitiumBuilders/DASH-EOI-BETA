"""odt.config — single source of truth for runtime knobs.

v1.2: ROOT is now derived from this file's location (portable across hosts).
      The OLLAMA host default is 'localhost' — env override expected.

All tunable parameters live here so v1.x can be tuned without code edits.
Override hierarchy (highest wins):
  1. ENV vars (ODT_<UPPER_NAME>)
  2. <project>/odt/config.local.toml  (gitignored)
  3. ODT_ROOT env var pointing to a different project root
  4. defaults below
"""

from __future__ import annotations
import os
import tomllib
from dataclasses import dataclass, field, asdict
from pathlib import Path


# Portable root: defaults to the directory containing this odt/ package.
# Can be overridden with ODT_ROOT for unusual layouts.
def _resolve_root() -> Path:
    env_root = os.environ.get("ODT_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    # odt/config.py → project root is parent of odt/
    return Path(__file__).resolve().parent.parent


ROOT = _resolve_root()
LOCAL_CONFIG = ROOT / "odt" / "config.local.toml"


@dataclass
class Config:
    # --- Model + transport ---
    ollama_host: str = "http://localhost:11434"  # ship-safe default
    model: str = "qwen3:8b"
    # --- Chunking ---
    target_tokens_per_chunk: int = 6000
    overlap_tokens: int = 400
    hard_max_tokens: int = 9000
    chars_per_token: int = 4
    tokenizer: str = "estimate"   # "estimate" | "tiktoken" | "hf"
    hf_tokenizer_model: str = "Qwen/Qwen3-8B"
    # --- Map (parallel) ---
    map_concurrency: int = 2
    map_num_ctx: int = 16384
    map_timeout_s: int = 180
    map_temperature: float = 0.4
    map_max_attempts: int = 3
    map_cache_enabled: bool = True   # v1.2: content-hash cache
    # --- Reduce ---
    reduce_fanout: int = 4
    reduce_num_ctx: int = 16384
    reduce_timeout_s: int = 180
    reduce_streaming: bool = True    # v1.2: start merging before all maps finish
    # --- Synthesize ---
    synth_num_ctx: int = 24576
    synth_timeout_s: int = 240
    synth_temperature: float = 0.6
    synth_max_chars: int = 12000
    # --- Review (LLM judge) ---
    judge_enabled: bool = True
    judge_num_ctx: int = 8192
    judge_timeout_s: int = 60
    judge_threshold: int = 7          # 0-10 scale; <threshold*4 triggers escalation
    # --- Reflect ---
    reflect_num_ctx: int = 8192
    reflect_timeout_s: int = 120
    # --- Output ---
    stream_synthesis: bool = True
    # --- Class routing thresholds ---
    small_max: int = 8_000
    medium_max: int = 40_000
    large_max: int = 200_000
    # --- Escalation ---
    escalate_after_loops: int = 4
    escalate_on_concerns: int = 3
    escalate_on_disagreements: int = 2
    # --- v1.2: deep-tree safeguards ---
    deep_tree_warn_levels: int = 4    # warn if reduce goes deeper than this
    max_chunks: int = 10_000          # hard cap; refuse to start above this

    @classmethod
    def load(cls) -> "Config":
        c = cls()
        if LOCAL_CONFIG.exists():
            try:
                data = tomllib.loads(LOCAL_CONFIG.read_text())
                for k, v in data.items():
                    if hasattr(c, k):
                        setattr(c, k, v)
            except Exception:
                pass
        for f in c.__dataclass_fields__:
            env = os.environ.get(f"ODT_{f.upper()}")
            if env is None:
                continue
            cur = getattr(c, f)
            try:
                if isinstance(cur, bool):
                    setattr(c, f, env.lower() in ("1", "true", "yes", "on"))
                elif isinstance(cur, int):
                    setattr(c, f, int(env))
                elif isinstance(cur, float):
                    setattr(c, f, float(env))
                else:
                    setattr(c, f, env)
            except ValueError:
                pass
        return c

    def to_dict(self) -> dict:
        return asdict(self)


CFG = Config.load()
