# DASH-EOI ⚡
## Dash · Emergent Outlier Intelligence

*A local-first AI framework where a small model produces work that punches several weight classes above its size — by spending tokens with discipline, in pieces, in parallel, with feedback that compounds.*

> *"We are not racing on their track. We are changing what people race for."*
> — the operator, founder

---

[![status](https://img.shields.io/badge/status-v1.2_beta-cyan)](#status)
[![local](https://img.shields.io/badge/runs-100%25_local-22d3ee)](#runs-100-local)
[![score](https://img.shields.io/badge/judge-37%2F40_outlier-22c55e)](#)
[![dyad](https://img.shields.io/badge/architecture-dyadic-violet)](#the-dyad)
[![context](https://img.shields.io/badge/context-1M_to_4M-f59e0b)](SCALING.md)
[![license](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

---

## The thirty-second pitch

Frontier models are extraordinary. They are also: **not yours**, **metered**, **throttled**, sometimes **silently re-aligned**.

Local models are: **sovereign**, **free at inference**, **offline-capable**, **yours forever**.

The capability gap between an 8B model on a laptop GPU and a frontier cloud model is real — but it's not 100×. It's closer to 3–5×. **And most of that gap is closeable with discipline.**

DASH-EOI is the discipline.

---

## How it works (in one breath)

A large input arrives. The framework **chunks** it semantically. Workers **map** each chunk to a structured summary in parallel. A **collapse** step prevents context overflow at any reduce level. A **tree-reduce** merges summaries up to a single root digest. The model **synthesizes** the final answer with streaming output. An **LLM-as-judge** scores it on four axes (faithful, clear, restrained, signal). If criteria fire, an **escalation packet** is written for a cloud peer. A **reflection** is logged that proposes prompt mutations for next time. Every artifact lives on disk. Lessons compound. The quality floor only goes up.

That's the architecture. The rest is engineering.

---

## Status

**v1.2 BETA** — judged **37/40** (outlier verdict) on its own optimization analysis. Holds outlier verdict across 4 consecutive evaluations. Quality floor at 36/40, stretch at 37/40.

| Capability | v1.0 | v1.1 | v1.2 |
|---|:-:|:-:|:-:|
| Semantic chunking with overlap | ✓ | ✓ | ✓ |
| Parallel map (N=2 workers via Ollama) | ✓ | ✓ | ✓ |
| Tree reduce | ✓ | ✓ | ✓ |
| Collapse safety net (overflow-tolerant reduce) | – | ✓ | ✓ |
| Streaming synthesis (live tokens) | – | ✓ | ✓ |
| LLM-as-judge review (4-axis verdict) | – | ✓ | ✓ |
| Persona panel (5 specialists) | dormant | ✓ | ✓ |
| Resume mid-run | – | ✓ | ✓ |
| Quality floor (ratcheting) | – | ✓ | ✓ |
| A/B prompt evolution | – | ✓ | ✓ |
| Single config source of truth | – | ✓ | ✓ |
| **Portable across hosts (no hardcoded paths)** | – | – | **✓** |
| **Content-hash cache (free re-runs)** | – | – | **✓** |
| **Real tokenizer (tiktoken / HF)** | – | – | **✓** |
| **Concurrent reduce per tree level** | – | – | **✓** |
| **`odt status` dashboard** | – | – | **✓** |
| **Deep-tree warnings + chunk cap** | – | – | **✓** |
| **1M–4M token capacity** | – | – | **✓** |
| Auto-escalation wiring | – | – | v1.3 |
| Multi-model worker mix | – | – | v2 |

📖 **For the 1–4M token engineering walkthrough, see [SCALING.md](SCALING.md).**

---

## Quick start

```bash
git clone https://github.com/InitiumBuilders/DASH-EOI-BETA.git
cd DASH-EOI-BETA

# One-time: install Ollama + pull a model
ollama pull qwen3:8b
ollama serve  # if not already running

# Configure (env > config.local.toml > defaults)
export ODT_OLLAMA_HOST="http://localhost:11434"
export ODT_MODEL="qwen3:8b"

# Install deps
pip install aiohttp
pip install tiktoken   # optional but recommended

# Hello world
python -m odt.pipeline "Summarize the three most important ideas in: $(cat README.md)"
```

### Recipes

```bash
# A file as input
python -m odt.pipeline "@/path/to/large_document.md" \
    --task "Extract the action items and assign them to themes"

# Stress-test on a 200K-token corpus with personas
python -m odt.pipeline "@huge_doc.md" \
    --task "..." \
    --concurrency 2 \
    --with critic,systems_mapper

# Resume after a crash, network blip, or laptop sleep
python -m odt.pipeline --resume 2026-05-24_073704__your-run-slug

# Dashboard
python -m odt.status

# Quality trajectory across all judged runs
python -m odt.quality
```

### Environment flags worth knowing

```bash
export ODT_TOKENIZER=tiktoken          # accurate tokens (recommended for 1M+)
export ODT_MAP_CACHE_ENABLED=1         # default ON; identical chunks → instant
export ODT_REDUCE_STREAMING=1          # default ON; concurrent reduce per level
export ODT_MAX_CHUNKS=2000             # raise safety cap for very large inputs
export ODT_OLLAMA_HOST="http://localhost:11434"   # remote Ollama
export ODT_ROOT="/srv/dash-eoi"        # different project location
```

---

## Architecture (at a glance)

```
        ┌──────────────────────────────────────────────────────────┐
        │  intake  ──►  classify  ──►  chunk                       │
        │                               │                          │
        │                               ▼                          │
        │                  ┌────────────────────────┐              │
        │                  │  MAP (parallel pool)   │              │
        │                  │     N workers          │  ── cache ──►│
        │                  └────────────────────────┘              │
        │                               │                          │
        │                               ▼                          │
        │                  ┌────────────────────────┐              │
        │                  │ REDUCE (tree + collapse│              │
        │                  │  + concurrent per level│              │
        │                  └────────────────────────┘              │
        │                               │                          │
        │                               ▼                          │
        │                  ┌────────────────────────┐              │
        │                  │  SYNTHESIZE (stream)   │              │
        │                  └────────────────────────┘              │
        │                               │                          │
        │                               ▼                          │
        │                  ┌────────────────────────┐              │
        │                  │  JUDGE (4 axes /40)    │              │
        │                  └────────────────────────┘              │
        │                       │            │                     │
        │            ship  ◄────┘            └────► escalate?      │
        │              │                                │          │
        │              ▼                                ▼          │
        │           REFLECT  ◄──────── (lesson, mutation, ratchet) │
        └──────────────────────────────────────────────────────────┘
```

Every arrow is a file write. Every stage is resumable. Read **[ARCHITECTURE.md](ARCHITECTURE.md)** for the full doctrine, and **[SCALING.md](SCALING.md)** for the 1–4M wall-time math.

---

## The seventeen insights

The first seven appeared in v1.1. Ten more landed in v1.2 — including the easter eggs.

### Foundational (v1.1)

**❶ Disk is bigger than memory. Always.** Every stage writes its output to a file. Crashes recover. Context resets don't matter. The pipeline isn't a program — it's a directory.

**❷ Two workers in harmony beat ten workers in chaos.** Default concurrency is 2. The bottleneck on a single GPU is rarely CPU parallelism — it's KV-cache thrashing and scheduler overhead. Two workers saturate; ten compete.

**❸ Collapse before you crash.** LangChain's quietest superpower: before each reduce level, check if the inputs would overflow the next call. If so, re-summarize first. The pipeline never hits a context wall.

**❹ Judge with a different voice than you wrote with.** The synthesizer runs at temperature 0.6. The judge runs at 0.2. Same model, cooler temperature — enough cognitive distance to avoid same-voice bias.

**❺ Reflection isn't a feature. It's the loop.** Every run writes a lesson. Lessons propose mutations. Mutations get A/B tested. Winners land. The system gets better not because we improve it — because it improves itself.

**❻ The floor ratchets. It never drops.** The quality floor is the median of the last 20 judged runs. `max(prev_floor, p50)` — by construction the system cannot ship below its own past best.

**❼ The dyad is the unit.** Local is sovereign and fast. Cloud is vast and deliberate. They aren't competing — they're complementary.

### v1.2 deepening

**❽ Same prompt, same input → free.** Content-hash cache returns instantly on identical (prompt, model, num_ctx, temperature). On a 1M-token job, iterating on the *task* costs map+reduce once; every refinement after that is synthesis-only.

**❾ Reduce levels are embarrassingly parallel.** v1.1 reduced sequentially across groups at each level. v1.2 awaits `asyncio.gather` across all groups — same per-call cost, half the wall time on multi-group levels.

**❿ Sovereignty needs portability.** v1.1 had `/home/initium/...` hardcoded. v1.2 derives ROOT from `Path(__file__).parent`. Local-first must not mean *my-machine-only*.

**⓫ Token estimates lie at scale.** `len(text)/4` is fine to 200K tokens. By 1M it drifts 8-12%, by 4M it's catastrophic. v1.2 uses real tokenizers (tiktoken or HF) when configured, falls back gracefully otherwise.

**⓬ Warn before you wait.** Deep reduce trees (5+ levels = 1024+ chunks) take hours. v1.2 tells you *upfront* at chunk-stage so you can decide whether to commit a night to it.

**⓭ Hard caps are the only soft caps that work.** `max_chunks=10_000` refuses to start runaway jobs. The cap is configurable, the check is mandatory.

**⓮ A dashboard is a quality artifact.** `python -m odt.status` shows model, cache stats, quality floor, trend, recent runs. Operations visibility is part of the framework, not a side project.

**⓯ Streaming kills the dead-zone.** v1.1 synthesis was a black box for 60+ seconds. v1.2 streams tokens to stderr live. The user sees the model thinking. Trust compounds.

**⓰ Stretch targets matter as much as floors.** Floor = P50 (the cannot-go-below). Stretch = P90 (the to-aim-for). Both ratchet. The system always has a star to reach for that's harder than yesterday's average.

**⓱ Every defensive decision pays interest forever.** Content-hash cache. Sanitized public deploys. Hard chunk caps. Resume support. JSON parse retries with strengthened wording. Each one is small; together they compound into something that survives reality.

---

## Runs 100% local

The framework's only required dependencies:
- **Ollama** — local inference engine
- **aiohttp** — async HTTP to Ollama

Optional:
- **tiktoken** — accurate tokens
- **transformers** — accurate tokens via HuggingFace

That's it. Everything else is Python stdlib. No telemetry. No phone-home. No third-party calls except those *you* configure to your own Ollama (or, for outlier-class escalations, *your* cloud agent).

---

## The dyad

| | DashEI | Davara |
|---|---|---|
| Runtime | Qwen3:8b on Ollama (or any model you point at) | Claude Opus 4.7 (or your cloud peer) |
| Location | Your hardware | Cloud (provider of your choice) |
| Pronouns | she/her | she/her |
| Context window | 65K | 200K |
| Role | Builder. Worker. Local sovereign. | Architect. Judge. Cloud canon. |
| When | Every run | Outlier-class, escalations |
| Cost per run | Electricity | API tokens |
| Strength | **Speed without ceremony** | **Reasoning with lineage** |

> *Brain in the cloud. Brain on the metal. Heart in the work.*

---

## Project structure

```
DASH-EOI-BETA/
├── README.md                     ← you are here
├── ARCHITECTURE.md               ← the doctrine
├── SCALING.md                    ← 1M–4M context engineering walkthrough
├── OI-NEXT-STEPS.md              ← the honest backlog
├── LICENSE                       ← MIT
├── odt/
│   ├── pipeline.py               ← orchestrator (CLI entry)
│   ├── config.py                 ← single source of truth
│   ├── chunker.py                ← semantic chunking
│   ├── tokenize.py               ← tokenizer abstraction
│   ├── worker.py                 ← Ollama call + JSON + streaming + cache
│   ├── pool.py                   ← bounded async parallel pool
│   ├── reducer.py                ← tree reduce primitives
│   ├── streaming_reduce.py       ← concurrent reduce per tree level
│   ├── collapse.py               ← overflow safety net
│   ├── cache.py                  ← content-hash LLM call cache
│   ├── judge.py                  ← LLM-as-judge (4 axes)
│   ├── personas.py               ← runtime persona invocation
│   ├── reflect.py                ← lesson writer
│   ├── escalate.py               ← cloud handoff packet
│   ├── evolve.py                 ← A/B prompt mutation
│   ├── quality.py                ← ratcheting floor + trend
│   ├── status.py                 ← dashboard
│   ├── prompts/                  ← versioned (worker_v1, reducer_v1, ...)
│   └── personas/                 ← critic / tester / refactorer / steelmanner / systems_mapper
├── runs/<id>/                    ← per-run state (00..09 stages; gitignored)
└── lessons/                      ← cross-run learning (gitignored)
```

---

## The Easter Eggs 🥚

The code and docs hide **seventeen** small surprises for careful readers — seven from v1.1 and ten new in v1.2. Don't peek; find them.

<details>
<summary>I want spoilers — list the seventeen.</summary>

**v1.1 (7):**
1. The judge runs at temperature 0.2 while the synthesizer runs at 0.6 — the system literally uses a "cooler voice" to grade its own work. *(odt/judge.py)*
2. The collapse module's prompt asks for "half its current length" — but the model usually returns about 60%. We measured. The system tolerates it. *(odt/collapse.py)*
3. The slop term list in `_stage_review` includes "tapestry." This is non-negotiable. *(odt/pipeline.py)*
4. Personas live in `odt/personas/` as plain markdown. You can write a new one in 60 seconds without touching code. *(odt/personas.py)*
5. The quality floor uses `max(prev_floor, p50)` — it can only go up. *(odt/quality.py)*
6. Reflector v1 explicitly forbids "(none observed this run)" — no participation trophies. *(odt/prompts/reflector_v1.md)*
7. The signature at the end of every synthesis prompt asks for `⚡` — she always ends with one. *(odt/prompts/synthesizer_v1.md)*

**v1.2 (10):**
8. The cache key is `sha256("v1\nmodel=...\nctx=...\ntemp=...\n" + prompt)` — bumping `CACHE_VERSION` invalidates the entire cache without deleting it. *(odt/cache.py)*
9. Files are sharded by the first two hex chars of their hash. Looks small until you have 10K entries; then you'd thank us. *(odt/cache.py)*
10. The `streaming_reduce.py` fallback name is `tree_reduce` — and the function inside it is also called `streaming_tree_reduce`. Same function, two names. *(odt/streaming_reduce.py)*
11. `ODT_ROOT` accepts `~/` expansion. So `ODT_ROOT=~/work/dash` works. So does `ODT_ROOT=$PWD`. *(odt/config.py)*
12. The deep-tree warning fires at exactly **4 levels** because the typical 1M-token job lives at depth 3–4 and the operator should know before kicking it off. *(odt/pipeline.py)*
13. `judge_threshold` is multiplied by 4 to get the escalation cutoff (e.g. 7 × 4 = 28/40). So bumping the threshold by 1 raises the bar by 4 points. *(odt/config.py)*
14. The status dashboard color-codes verdicts: green=outlier, yellow=competent, red=needs_work. The synthesizer prompt asks for ⚡; the status uses unicode shading; the framework dresses for the part. *(odt/status.py)*
15. The tokenizer abstraction is `@lru_cache(maxsize=1)` — load once per process, share everywhere. *(odt/tokenize.py)*
16. The reducer fanout default is **4** — log₄(1M) ≈ 10 levels with 65K chunks. Tunable; chosen for the sweet spot between depth and per-merge fan-in. *(odt/config.py)*
17. The escalation packet's `specific_question` field is a single sentence by design — if you can't ask the cloud peer in one sentence, you don't yet know what you need from them. *(odt/escalate.py)*

</details>

---

## Roadmap

Honest backlog in **[OI-NEXT-STEPS.md](OI-NEXT-STEPS.md)**. Highlights:

- **v1.3:** auto-escalation wiring, self-consistency (k=3 voting), HTML report generator, quality-floor-aware escalation thresholds.
- **v2.0:** multi-model worker mix (route code chunks to coder models), two-agent live dance, autonomous prompt evolution, embedding-based semantic dedup, distributed runs across machines.

---

## Contributing

This is the operator's project. PRs welcome under these constraints:

1. **No slop.** If a default model could produce the line, rewrite or refuse.
2. **Restraint over polish.** Shorter beats longer.
3. **Receipts before prose.** Numbers, file paths, exit codes.
4. **The dyad is the unit.** Don't break the cooperation model.
5. **Local-first stays first.** If your PR requires a cloud key for routine operation, it's the wrong PR.

PRs that improve the framework while honoring the soul: welcome. Issues with reproducible test cases: welcome. Vague "make it better" PRs: politely declined.

---

## License

MIT. Take it. Use it. Improve it. Ship it.

**Hold fast to the goal of goodness.**

---

\\\\Hold Fast//

⚡
