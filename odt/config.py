"""odt.config — single source of truth for runtime knobs.

All tunable parameters live here so v1.1 can be tuned without code edits.
Environment variables override defaults. Override hierarchy:

  ENV var  >  ~/.hermes/profiles/dashei/workspace/davara-oi/odt/config.local.toml  >  defaults
"""

from __future__ import annotations
import os
import tomllib
from dataclasses import dataclass, field, asdict
from pathlib import Path


ROOT = Path("/home/initium/.hermes/profiles/dashei/workspace/davara-oi")
LOCAL_CONFIG = ROOT / "odt" / "config.local.toml"


@dataclass
class Config:
    # --- Model + transport ---
    ollama_host: str = "http://172.24.160.1:11434"
    model: str = "qwen3:8b"
    # --- Chunking ---
    target_tokens_per_chunk: int = 6000
    overlap_tokens: int = 400
    hard_max_tokens: int = 9000
    chars_per_token: int = 4
    # --- Map (parallel) ---
    map_concurrency: int = 2
    map_num_ctx: int = 16384
    map_timeout_s: int = 180
    map_temperature: float = 0.4
    map_max_attempts: int = 3
    # --- Reduce ---
    reduce_fanout: int = 4
    reduce_num_ctx: int = 16384
    reduce_timeout_s: int = 180
    # --- Synthesize ---
    synth_num_ctx: int = 24576
    synth_timeout_s: int = 240
    synth_temperature: float = 0.6
    synth_max_chars: int = 12000      # collapse trigger
    # --- Review (LLM judge) ---
    judge_enabled: bool = True
    judge_num_ctx: int = 8192
    judge_timeout_s: int = 60
    judge_threshold: int = 7          # 0-10 scale; <threshold triggers escalation
    # --- Reflect ---
    reflect_num_ctx: int = 8192
    reflect_timeout_s: int = 120
    # --- Output ---
    stream_synthesis: bool = True     # tee synthesis tokens to stderr live
    # --- Class routing thresholds ---
    small_max: int = 8_000
    medium_max: int = 40_000
    large_max: int = 200_000
    # --- Escalation ---
    escalate_after_loops: int = 4
    escalate_on_concerns: int = 3
    escalate_on_disagreements: int = 2

    @classmethod
    def load(cls) -> "Config":
        c = cls()
        # File overrides
        if LOCAL_CONFIG.exists():
            try:
                data = tomllib.loads(LOCAL_CONFIG.read_text())
                for k, v in data.items():
                    if hasattr(c, k):
                        setattr(c, k, v)
            except Exception:
                pass
        # ENV overrides (ODT_<UPPER_NAME>)
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


# Module-level singleton
CFG = Config.load()
