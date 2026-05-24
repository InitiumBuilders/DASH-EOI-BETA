# Scaling to 1M, 3M, 4M Tokens

*A practical engineering note · v1.2 · 2026-05-24*

This document answers: **can DASH-EOI really handle inputs of 3-4 million tokens on a single local 8B model?**

Short answer: **Yes, architecturally. The constraint is wall-time, not context.**

---

## The capacity math

Tree-reduce gives compound coverage. With chunk size 6K and fanout 4:

| Depth | Chunks | Input capacity | Reduce calls |
|---:|---:|---:|---:|
| 1 | 4 | 24K | 1 |
| 2 | 16 | 96K | 5 |
| 3 | 64 | 384K | 21 |
| 4 | 256 | 1.5M | 85 |
| 5 | 1,024 | **6.1M** | 341 |
| 6 | 4,096 | **24.6M** | 1365 |

**At depth 5 we already exceed 3-4M.** The architecture supports 6M with margin.

## The wall-time math

Wall time ≈ (map_calls / concurrency × per_map) + (reduce_calls × per_reduce)

Empirical from v1.2 runs on qwen3:8b at concurrency=2:
- per_map ≈ 25-30s
- per_reduce ≈ 25-35s

Projected for various input sizes:

| Input | Chunks | Map wall | Reduce wall | **Total (cold)** | **Total (warm cache)** |
|---:|---:|---:|---:|---:|---:|
| 50K | 9 | 2.5 min | 1 min | **~4 min** | ~30s |
| 200K | 35 | 9 min | 4 min | **~14 min** | ~3 min |
| 1M | 165 | 42 min | 17 min | **~1 hr** | ~10 min |
| 3M | 500 | 2 hr | 50 min | **~3 hr** | ~30 min |
| 4M | 660 | 2.75 hr | 65 min | **~4 hr** | ~40 min |

**3-4M is overnight territory on this rig.** Practical, not theoretical.

## What makes 3M-4M practical (vs theoretically possible)

### v1.2 levers already in place:

1. **Content-hash cache** — re-runs over similar corpora cost a fraction. Boss iterates on the *task*, not the input. Each iteration after the first runs at cache speed.
2. **Streaming reduce** — concurrent merges at each reduce level. Cuts the reduce wall-time roughly in half.
3. **Collapse safety net** — never overflow context, no matter how deep the tree goes.
4. **Resume support** — if Ollama OOMs at chunk 478, pick up at 479.
5. **Deep-tree warning** — system tells you upfront when wall-time will be hours.
6. **Single GPU saturation** — concurrency=2 is the sweet spot. Higher means cache thrashing.

### v1.3 levers to bring 4M from "overnight" to "lunch":

1. **Multi-model routing** — small chunks via `qwen3:1.7b` (5× faster), big ones via `qwen3:8b`.
2. **Cache warming** — pre-cache common chunks (e.g., the first 50K of a long doc you query repeatedly).
3. **Tighter map prompts** — every 5% reduction in prompt overhead is 5% off wall time.
4. **Async reduce streaming** — start merging the moment 4 chunks finish, don't wait for all.

### v2.0 levers to bring 4M to **minutes**:

1. **Cluster the workers** — add a second machine, double concurrency.
2. **Quantized model swap** — `qwen3:8b-int4` is ~30% faster than fp16 with marginal quality loss.
3. **Direct vLLM** — drop Ollama, use vLLM with continuous batching. 3-5× throughput.
4. **Embedding pre-filter** — for retrieval-style tasks, embed chunks and only summarize the top-K relevant. Skip 80% of the input entirely.

---

## How to actually run a 1M+ job today (v1.2)

```bash
# Step 1: split your input into a single file if not already
cat doc1.md doc2.md doc3.md > /tmp/big_input.md
wc -c /tmp/big_input.md   # check size

# Step 2: configure for the long run
export ODT_MAP_CONCURRENCY=2
export ODT_MAP_TIMEOUT_S=240        # bigger timeout for warm-up cold starts
export ODT_REDUCE_TIMEOUT_S=240
export ODT_MAP_CACHE_ENABLED=1
export ODT_REDUCE_STREAMING=1
export ODT_TOKENIZER=tiktoken       # accurate token counting
export ODT_MAX_CHUNKS=1000          # raise the safety cap if needed

# Step 3: kick it off
python -m odt.pipeline "@/tmp/big_input.md" \
  --task "your specific question about the full corpus" \
  --concurrency 2

# Step 4: monitor progress on another terminal
watch -n 30 'ls runs/<latest>/04_map/ | wc -l'

# Step 5: if it dies mid-run, resume:
python -m odt.pipeline --resume <run-id>
```

---

## The honest ceiling

**Realistic ceiling on this single-GPU rig:** ~4M tokens per run, with ~4 hours wall time on a cold cache.

**Why not higher?** Two reasons:
1. **Practical:** an 8-hour run that can fail in hour 7 is operationally fragile. Resume helps but doesn't eliminate the risk.
2. **Useful:** at 4M+ tokens, the *task* itself starts being the constraint. The right framing usually involves retrieval or pre-segmentation, not pure map-reduce.

**Want higher than 4M? v2.0 territory:**
- Add a second machine (concurrency goes up linearly)
- Switch to vLLM with continuous batching (3-5× per-machine throughput)
- Add embedding-based pre-filtering (often cuts input by 80%)

---

\\Hold Fast//
