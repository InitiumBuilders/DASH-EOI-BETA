"""odt.tokenize — accurate token counting with graceful fallback.

v1.2 supports three modes, set via CFG.tokenizer:
  - "estimate"  : chars // 4  (fastest, no deps; current default)
  - "tiktoken"  : tiktoken.cl100k_base (close enough for most modern models)
  - "hf"        : transformers.AutoTokenizer (most accurate; heavy dep)

The estimate is fine up to ~200K tokens. Above that the 4-char rule
drifts (English ≈ 3.5, code ≈ 4.5, JSON ≈ 5.0). Use a real tokenizer
when you need precision at 1M+ scale.

Set ODT_TOKENIZER=tiktoken or hf to enable.
"""

from __future__ import annotations
from functools import lru_cache
from typing import Optional

from . import config as cfg


@lru_cache(maxsize=1)
def _get_tokenizer():
    mode = cfg.CFG.tokenizer
    if mode == "tiktoken":
        try:
            import tiktoken  # type: ignore
            return ("tiktoken", tiktoken.get_encoding("cl100k_base"))
        except ImportError:
            return ("estimate", None)
    if mode == "hf":
        try:
            from transformers import AutoTokenizer  # type: ignore
            return ("hf", AutoTokenizer.from_pretrained(cfg.CFG.hf_tokenizer_model))
        except (ImportError, OSError):
            return ("estimate", None)
    return ("estimate", None)


def count(text: str) -> int:
    """Count tokens in text using the configured tokenizer.

    Falls back gracefully to chars//4 estimate if the chosen tokenizer
    is unavailable. Never raises.
    """
    if not text:
        return 0
    mode, tok = _get_tokenizer()
    try:
        if mode == "tiktoken":
            return len(tok.encode(text))
        if mode == "hf":
            return len(tok.encode(text, add_special_tokens=False))
    except Exception:
        pass
    return max(1, len(text) // cfg.CFG.chars_per_token)


def info() -> dict:
    mode, tok = _get_tokenizer()
    return {
        "mode": mode,
        "loaded": tok is not None,
        "configured": cfg.CFG.tokenizer,
        "fallback_chars_per_token": cfg.CFG.chars_per_token,
    }
