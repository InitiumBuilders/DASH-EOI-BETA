"""odt.chunker — semantic chunking for Outlier-Deep-Think.

Strategy:
  1. Detect structure: code / json / markdown / prose.
  2. Split along natural boundaries first.
  3. Merge small pieces up toward target_tokens.
  4. Split oversize pieces along secondary boundaries (paragraphs, sentences).
  5. Add overlap between chunks so context doesn't shear at boundaries.

Token estimation: we use 4 chars/token (close enough for English + code).
"""

from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path


CHARS_PER_TOKEN = 4   # approximation; good enough for routing
TARGET_TOKENS = 6000
OVERLAP_TOKENS = 400
HARD_MAX_TOKENS = 9000  # don't let a chunk grow past this even if structure says so


@dataclass
class Chunk:
    index: int
    text: str
    structural_type: str   # "code" | "markdown" | "json" | "prose"
    token_count: int
    origin_offset: int     # char offset in original input


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def detect_type(text: str) -> str:
    head = text[:2000].strip()
    if head.startswith("{") or head.startswith("["):
        # crude JSON sniff
        if head.count("{") + head.count("[") >= 2:
            return "json"
    code_signals = ("def ", "class ", "function ", "import ", "const ", "let ", "package ", "#include", "fn ")
    code_hits = sum(1 for s in code_signals if s in text[:4000])
    if code_hits >= 2:
        return "code"
    if re.search(r"^#{1,6}\s", text, re.M):
        return "markdown"
    return "prose"


def split_prose(text: str) -> list[str]:
    """Paragraphs first, sentences as fallback."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return paras


def split_markdown(text: str) -> list[str]:
    """Split on top-level headings, preserving heading with body."""
    parts = re.split(r"(?m)^(?=#{1,3}\s)", text)
    return [p.strip() for p in parts if p.strip()]


def split_code(text: str) -> list[str]:
    """Split on top-level function/class definitions; fall back to paragraphs."""
    pattern = r"(?m)^(?=(?:def |class |function |fn |func |const |let |export ))"
    parts = re.split(pattern, text)
    if len(parts) <= 1:
        return split_prose(text)
    return [p.strip() for p in parts if p.strip()]


def split_json(text: str) -> list[str]:
    """For JSON, treat top-level keys as natural splits if possible.

    For very large JSON, we fall back to balanced-brace splitting at the top level.
    """
    # cheap split: top-level keys at column 0-ish indentation
    parts = re.split(r"\n(?=  \"[^\"]+\":\s)", text)
    if len(parts) <= 1:
        return [text]
    return parts


def _hard_split(piece: str, max_chars: int) -> list[str]:
    """Last resort: split a single oversized piece at sentence-ish boundaries."""
    if len(piece) <= max_chars:
        return [piece]
    out: list[str] = []
    while len(piece) > max_chars:
        cut = piece.rfind(". ", 0, max_chars)
        if cut < max_chars // 2:
            cut = piece.rfind("\n", 0, max_chars)
        if cut < max_chars // 2:
            cut = max_chars
        out.append(piece[:cut].strip())
        piece = piece[cut:].lstrip()
    if piece:
        out.append(piece)
    return out


def chunk_text(
    text: str,
    target_tokens: int = TARGET_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
    hard_max_tokens: int = HARD_MAX_TOKENS,
) -> list[Chunk]:
    """Return a list of Chunk objects covering the full input with controlled overlap."""
    if not text.strip():
        return []

    stype = detect_type(text)
    splitter = {
        "code": split_code,
        "json": split_json,
        "markdown": split_markdown,
        "prose": split_prose,
    }[stype]

    pieces = splitter(text)
    target_chars = target_tokens * CHARS_PER_TOKEN
    hard_max_chars = hard_max_tokens * CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * CHARS_PER_TOKEN

    # First pass: merge small pieces up to target_chars; split oversized ones.
    merged: list[str] = []
    buf = ""
    for piece in pieces:
        if len(piece) > hard_max_chars:
            if buf:
                merged.append(buf)
                buf = ""
            merged.extend(_hard_split(piece, hard_max_chars))
            continue
        if len(buf) + len(piece) + 2 <= target_chars:
            buf = piece if not buf else f"{buf}\n\n{piece}"
        else:
            if buf:
                merged.append(buf)
            buf = piece
    if buf:
        merged.append(buf)

    # Second pass: add overlap and assemble Chunk objects.
    chunks: list[Chunk] = []
    offset = 0
    for i, body in enumerate(merged):
        prefix = ""
        if i > 0 and merged[i - 1]:
            prev = merged[i - 1]
            prefix = prev[-overlap_chars:] + "\n…\n" if len(prev) > overlap_chars else prev + "\n…\n"
        chunk_text_full = prefix + body
        chunks.append(
            Chunk(
                index=i,
                text=chunk_text_full,
                structural_type=stype,
                token_count=estimate_tokens(chunk_text_full),
                origin_offset=offset,
            )
        )
        offset += len(body)
    return chunks


def chunk_file(path: str | Path, **kwargs) -> list[Chunk]:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    return chunk_text(text, **kwargs)


def classify_size(total_tokens: int) -> str:
    if total_tokens < 8_000:
        return "small"
    if total_tokens < 40_000:
        return "medium"
    if total_tokens < 200_000:
        return "large"
    return "outlier"


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: chunker.py <path>")
        sys.exit(1)
    chunks = chunk_file(sys.argv[1])
    total = sum(c.token_count for c in chunks)
    print(f"input: {total} tokens (est)  →  {len(chunks)} chunks  ({classify_size(total)} class)")
    for c in chunks[:5]:
        print(f"  chunk {c.index}: {c.token_count} tokens  type={c.structural_type}")
    if len(chunks) > 5:
        print(f"  ... and {len(chunks) - 5} more")
