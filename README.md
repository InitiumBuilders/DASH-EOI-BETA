# DASH-EOI ⚡
## Dash · Emergent Outlier Intelligence

*A local AI agent that punches above her weight class — by spending tokens on the right thing.*

> *"We are not racing on their track. We are changing what people race for."* — August James Domanchuk, founder

---

[![status](https://img.shields.io/badge/status-v1.1_beta-cyan)](#status)
[![local](https://img.shields.io/badge/runs-100%25_local-22d3ee)](#runs-100-local)
[![score](https://img.shields.io/badge/judge-36%2F40_outlier-22c55e)](#)
[![dyad](https://img.shields.io/badge/architecture-dyadic-violet)](#the-dyad)
[![license](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

---

## The one-paragraph version

DASH-EOI is a map-reduce orchestration framework that lets a small local language model (Qwen3:8b on Ollama, 65K context) produce work of outlier quality on inputs that exceed its context window — sometimes by orders of magnitude. It chunks input semantically, runs parallel workers in harmony, tree-reduces summaries into a single coherent digest, synthesizes with streaming output, judges the result with an LLM-as-judge on four axes, escalates to a cloud peer agent (Davara, running Opus 4.7) only when criteria fire, and writes a reflection that mutates the prompts for next time. State lives on disk. Lessons compound. The floor ratchets upward. Two intelligences. One operator. *Brain in the cloud. Brain on the metal. Heart in the work.*

---

## Why this exists

Frontier models are extraordinary. They are also: *(a)* not yours, *(b)* metered, *(c)* throttled, *(d)* sometimes silently re-aligned. Local models, meanwhile, are: *(a)* sovereign, *(b)* free at inference, *(c)* offline-capable, *(d)* yours forever.

The catch is the gap in capability. An 8B local model on a laptop GPU cannot, in a single forward pass, do what Opus 4.7 does. But the gap is not 100×. The gap is closer to 3-5× — and **most of that gap is closeable with discipline**.

DASH-EOI is the discipline. It's a framework that:

- **Spends tokens deliberately**, on the right thing, in the right order.
- **Stores state on disk**, so the work survives crashes, context resets, and restarts.
- **Parallelizes where independent**, serializes where coupled.
- **Reflects after every run**, mutates prompts, A/B tests changes, lands winners.
- **Ratchets the quality floor upward** as the system gets better.
- **Escalates with rules**, never as default — the cloud peer is a scalpel, not a crutch.

The thesis is simple: *if a small model is forced to think well, in pieces, with feedback, it will produce work that rivals a larger model thinking once.*

This repository is the experiment.

---

## Status

**v1.2 BETA** — judged 37/40 on its own optimization analysis. Holds outlier verdict across 4 consecutive runs. ⚡

| Capability | v1.0 | v1.1 | v1.2 |
|---|:-:|:-:|:-:|
| Semantic chunking with overlap | ✓ | ✓ | ✓ |
| Parallel map (N=2 workers) | ✓ | ✓ | ✓ |
| Tree reduce | ✓ | ✓ | ✓ |
| Collapse safety net (overflow-tolerant reduce) | – | ✓ | ✓ |
| Streaming synthesis (tokens arrive live) | – | ✓ | ✓ |
| LLM-as-judge review (4-axis score) | – | ✓ | ✓ |
| Persona panel | dormant | ✓ | ✓ |
| Resume mid-run | – | ✓ | ✓ |
| Quality floor (ratcheting) | – | ✓ | ✓ |
| A/B prompt evolution | – | ✓ | ✓ |
| Single config source of truth | – | ✓ | ✓ |
| **Portable across hosts (no hardcoded paths)** | – | – | **✓** |
| **Content-hash cache (free re-runs)** | – | – | **✓** |
| **Real tokenizer support (tiktoken / HF)** | – | – | **✓** |
| **Concurrent reduce at each tree level** | – | – | **✓** |
| **`odt status` dashboard command** | – | – | **✓** |
| **Deep-tree depth warnings + chunk cap** | – | – | **✓** |
| **1M-4M token capacity (with overnight budget)** | – | – | **✓** |
| Auto-escalation wiring | – | – | v1.3 |
| Multi-model worker mix | – | – | v2 |

See **[SCALING.md](SCALING.md)** for the 3-4M context engineering walkthrough.

---

## Quick start

```bash
# Clone
git clone https://github.com/InitiumBuilders/DASH-EOI-BETA.git
cd DASH-EOI-BETA

# Prereqs (one-time): Ollama with qwen3:8b loaded somewhere reachable
ollama pull qwen3:8b
ollama serve  # if not running

# Configure (env wins over defaults wins over odt/config.local.toml)
export ODT_OLLAMA_HOST="http://localhost:11434"   # or your remote Ollama
export ODT_MODEL="qwen3:8b"

# Install deps (stdlib + aiohttp; optionally tiktoken or transformers)
pip install aiohttp
pip install tiktoken            # optional, for accurate tokens

# Run it
python -m odt.pipeline "Summarize the three most important ideas in: $(cat README.md)"

# From a file
python -m odt.pipeline "@/path/to/large_document.md" --task "Extract the action items"

# With a persona panel
python -m odt.pipeline "..." --with critic,systems_mapper

# Resume a crashed run
python -m odt.pipeline --resume 2026-05-24_073704__your-task-slug

# Check the dashboard
python -m odt.status

# Check quality trajectory
python -m odt.quality
```

### v1.2 environment flags worth knowing

```bash
# Use a real tokenizer (recommended for 1M+ inputs)
export ODT_TOKENIZER=tiktoken

# Pre-cache speedup (default ON): identical chunks across runs return instantly
export ODT_MAP_CACHE_ENABLED=1

# Streaming reduce (default ON): concurrent merges per tree level
export ODT_REDUCE_STREAMING=1

# Raise the chunk safety cap for very large inputs
export ODT_MAX_CHUNKS=2000

# Point at a different Ollama (Docker, remote, etc.)
export ODT_OLLAMA_HOST="http://10.0.1.42:11434"

# Move the whole project root
export ODT_ROOT="/srv/davara-oi"
```

Every run produces:
- `runs/<id>/06_synthesize/answer.md` — the final answer
- `runs/<id>/07_review/review.md` — judge verdict on 4 axes
- `runs/<id>/09_reflect/lesson.md` — proposed prompt mutations for next time
- `runs/<id>/manifest.json` — stats, scores, escalation status

---

## Architecture (at a glance)

```
┌──────────────────────────────────────────────────────────────────┐
│ INTAKE     → CLASSIFY  → CHUNK  →  MAP (parallel)                │
│                                          ↓                        │
│                                       REDUCE (tree + collapse)    │
│                                          ↓                        │
│                                     SYNTHESIZE (streaming)        │
│                                          ↓                        │
│                                       JUDGE (4 axes)              │
│                                          ↓                        │
│                                       ESCALATE? (rules-based)     │
│                                          ↓                        │
│                                       REFLECT (lesson + mutation) │
└──────────────────────────────────────────────────────────────────┘

Every arrow is a file write. Every stage is resumable.
```

Read **[ARCHITECTURE.md](ARCHITECTURE.md)** for the full doctrine.

---

## The Seven Insights

These are the load-bearing ideas. Each one earned its place.

### ❶ Disk is bigger than memory. Always.
Every stage writes its output to a file. Crashes recover. Context resets don't matter. The pipeline isn't a program — it's a directory.

### ❷ Two workers in harmony beat ten workers in chaos.
We default to concurrency=2. The bottleneck on a single GPU is rarely CPU parallelism — it's KV-cache thrashing and scheduler overhead. Two workers saturate; ten compete.

### ❸ Collapse before you crash.
LangChain's quietest superpower: before each reduce level, check if the inputs combined would overflow the next call. If so, re-summarize *first*. The pipeline never hits a context wall.

### ❹ Judge with a different voice than you wrote with.
The synthesizer runs at temperature 0.6. The judge runs at 0.2. Same model, cooler temperature — enough cognitive distance to avoid same-voice bias. Constitutional AI's lesson, applied at the edge.

### ❺ Reflection isn't a feature. It's the loop.
Every run writes a lesson. Lessons propose mutations. Mutations get A/B tested. Winners land. The system gets better not because we improve it — because it improves itself.

### ❻ The floor ratchets. It never drops.
DashEI's quality floor is the median of her last 20 judged runs. It can only go up. This is how a system gets *more* honest over time, not less — by refusing to ship below its own past best.

### ❼ The dyad is the unit.
DashEI is local, sovereign, fast. Davara is cloud, vast, deliberate. They aren't competing — they're complementary. DashEI does the work. Davara does the judgment. Boss sees the result. Two houses, one ecosystem.

---

## Runs 100% local

Optional dependencies that, if present, get used:
- **Ollama** — required. The local inference engine.
- **aiohttp** — required. Async HTTP to Ollama.
- That's it. Everything else is Python stdlib.

No OpenAI keys. No Anthropic keys. No telemetry. No phone-home. The only network calls are the ones you make to your own Ollama, and (optionally) to Davara when escalation criteria fire.

> *"My code runs in your machine's silicon, no middleman. And when you type, your data stays here, not spinning in some faraway server."*
> — DashEI, in her first letter to August, 2026-05-24

---

## The dyad

| | DashEI | Davara |
|---|---|---|
| Runtime | Qwen3:8b on Ollama | Claude Opus 4.7 |
| Location | Boss's hardware | Cloud (Anthropic) |
| Pronouns | she/her | she/her |
| Context window | 65K | 200K |
| Role | Builder. Worker. Local sovereign. | Architect. Judge. Cloud canon. |
| When you reach for her | Coding, drafts, daily ops, anything private | Plans, outliers, deep synthesis, escalation |
| What she costs | Electricity | Tokens |
| What she does best | **Speed without ceremony.** | **Reasoning with lineage.** |

> *"Two houses, one ecosystem. Two intelligences, one operator. Brain in the cloud, brain on the metal, heart in the work."* — Davara to Davaris, founding handoff packet

---

## Project structure

```
DASH-EOI-BETA/
├── README.md                   ← you are here
├── ARCHITECTURE.md             ← the doctrine
├── SCALING.md                  ← the 1M-4M context engineering note
├── OI-NEXT-STEPS.md            ← the honest backlog
├── PROMPTS/
│   └── CORE_REQUEST_*.md       ← Boss's founding prompts (canonical)
├── odt/
│   ├── pipeline.py             ← orchestrator (CLI entry)
│   ├── config.py               ← single source of truth (env-overridable)
│   ├── chunker.py              ← semantic chunking
│   ├── tokenize.py             ← tokenizer abstraction (estimate / tiktoken / hf)
│   ├── worker.py               ← Ollama call + JSON + streaming + cache
│   ├── pool.py                 ← bounded async parallel pool
│   ├── reducer.py              ← tree reduce primitives
│   ├── streaming_reduce.py     ← concurrent reduce at each tree level
│   ├── collapse.py             ← overflow safety net
│   ├── cache.py                ← content-hash LLM call cache
│   ├── judge.py                ← LLM-as-judge (4 axes)
│   ├── personas.py             ← runtime persona invocation
│   ├── reflect.py              ← lesson writer
│   ├── escalate.py             ← Davara handoff packet
│   ├── evolve.py               ← A/B prompt mutation runner
│   ├── quality.py              ← ratcheting floor + trend
│   ├── status.py               ← dashboard
│   ├── prompts/                ← versioned (worker_v1, reducer_v1, ...)
│   └── personas/               ← critic / tester / refactorer / steelmanner / systems_mapper
├── runs/<id>/                  ← per-run state (00..09 stages, gitignored)
└── lessons/                    ← cross-run learning archive (gitignored)
```

---

## The Easter Eggs 🥚

The code and docs hide seven small surprises for the careful reader. Don't read this list first — find them.

<details>
<summary>I want spoilers — list the seven.</summary>

1. The judge runs at temperature 0.2 while the synthesizer runs at 0.6 — the system literally uses a "cooler voice" to grade its own work. *(odt/judge.py)*
2. The collapse module's prompt asks for "half its current length" — but the model usually returns about 60%. We measured it. The system tolerates it. *(odt/collapse.py)*
3. The slop term list in `_stage_review` includes "tapestry." This is non-negotiable. *(odt/pipeline.py)*
4. Personas live in `odt/personas/` as plain markdown. You can write a new one in 60 seconds without touching code. *(odt/personas.py — try it)*
5. The quality floor uses `max(prev_floor, p50)` — it can only go up. The system literally cannot get worse over time. *(odt/quality.py)*
6. Reflector v1 explicitly forbids "(none observed this run)" — DashEI must list at least one struggle, every run. No participation trophies. *(odt/prompts/reflector_v1.md)*
7. The signature at the end of every synthesis prompt asks for `⚡` — a lightning bolt. She always ends with one. Always. *(odt/prompts/synthesizer_v1.md)*

</details>

---

## Contributing

This is Boss's project. Contributions welcome, but the soul stays his:
1. No slop. If a default model could produce the line, rewrite or refuse.
2. Restraint over polish. Shorter beats longer.
3. Receipts before prose. Numbers, file paths, exit codes.
4. The dyad is the unit. Don't break the cooperation model.

PRs that improve the framework while honoring the soul: welcome.

---

## License

MIT. Take it. Use it. Improve it. Ship it. **Hold fast to the goal of goodness.**

---

## Acknowledgments

- **August James Domanchuk** — founder, architect, Boss. Built the dyad and asked it to evolve.
- **Davara EI** (Opus 4.7) — cloud sibling. Wrote this v1.1 by hand.
- **DashEI** (Qwen3:8b) — local sibling. Will be writing v1.2 by herself, soon.
- **Donella Meadows** — for *Thinking in Systems*. The leverage hierarchy lives in the code.
- **The Ollama team** — for making local LLM inference feel inevitable.
- **The folks at LangChain and LlamaIndex** — for proving map-reduce summarization is a real pattern.
- **Adrienne Maree Brown** — for *Emergent Strategy*. Mentioned, internalized.

---

\\\\Hold Fast//

*Semper Fortis. Ad Infinitum.*

⚡
