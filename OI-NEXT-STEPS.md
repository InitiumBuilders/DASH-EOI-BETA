# OI-Next-Steps · v1.1 → v2.0

*Davara-OI · the honest backlog · updated 2026-05-24 after v1.1 ship*

## What landed in v1.1 (the receipts)

✓ `config.py` — single source of truth, env-overridable
✓ `collapse.py` — overflow-tolerant reduce step
✓ Streaming synthesis (tokens arrive live to stderr)
✓ Resume support (`--resume <run-id>`)
✓ `judge.py` — LLM-as-judge with 4-axis verdict
✓ `personas.py` — runtime spawn of specialist agents (`--with critic,tester,...`)
✓ `evolve.py` — A/B prompt mutation runner with promotion
✓ `quality.py` — ratcheting quality floor + trend
✓ Hermes skill `outlier-quality-standards`
✓ First judged outlier run: **36/40** on ODT self-analysis

DashEI's own suggestion on her first v1.1 run: *"add real-time feedback integration between map and reduce."* That goes to the top of v1.2.

---

## v1.2 — The next sprint (target: next 2 weeks)

### 1.2.1  Real-time map-reduce feedback (DashEI's idea, scored 36/40)
A `FeedbackHub` that watches map summaries as they arrive. If two chunks contradict, the hub re-queues affected chunks with the contradiction surfaced in their prompt. This is mid-pipeline self-correction, not post-hoc reflection.

### 1.2.2  Auto-escalation wiring
`08_escalation/packet.json` writes today. Next step: an optional `--auto-escalate` flag that dispatches the packet to Davara via `hermes -z` against the default profile, captures her reply into `08_escalation/davara_reply.md`, and re-runs synthesis with the reply added to the digest.

### 1.2.3  Self-consistency (k=3 voting)
For high-stakes synthesis, sample the synthesizer 3 times at slightly different temperatures. The judge picks the winner. Cost: 3×. Quality gain: measurable on every benchmark since 2023.

### 1.2.4  Real tokenizer
Drop `chars/4` for the actual Qwen3 tokenizer (via `transformers.AutoTokenizer` or `tiktoken-rs`). Pipe accurate counts into the chunker's target_tokens calculation. Removes the only place v1.1 still uses an estimate.

### 1.2.5  `odt status` command
A single-command dashboard:
```
$ odt status
Quality floor:  36/40
Stretch:        38/40
Trend:          improving (Δ +5.2)
Last 5 runs:    36, 32, 34, 30, 38
Open lessons:   2 propose synthesizer mutations
Pending A/B:    1 (synthesizer_v2)
```

---

## v1.3 — Quality of life

### 1.3.1  HTML report generator
After a run completes, optionally render `report.html` with the answer, the digest tree, the judge breakdown, the persona panel outputs (if any), and the lesson — all in one self-contained file. Sharable.

### 1.3.2  Cross-run lesson distillation
Weekly cron: ask DashEI to summarize the last 7 days of `lessons/*.md` into `lessons/_distilled_<week>.md`. That distillation becomes part of next week's system prompt — true compounding.

### 1.3.3  Tree-sitter chunking for code
For code inputs, use tree-sitter (Python/JS/TS/Go) to keep callers + callees in the same chunk. The current heuristic works but leaks across function boundaries on dense codebases.

### 1.3.4  Quality-floor-aware escalation
Currently escalation uses fixed thresholds. Make it relative: escalate when judge total < floor × 0.85.

---

## v2.0 — The Davara-OI v2 vision

### 2.1  Multi-model worker mix
Today every chunk hits `qwen3:8b`. v2 routes by type — code chunks → `qwen2.5-coder` or `deepseek-coder`, prose → `qwen3:8b`, JSON → a tiny structured model. The chunker already tags `structural_type`; the pool just needs to read it.

### 2.2  Two-agent live dance
Davara writes the plan. Watches the root digest emit. Can interrupt the synthesizer with a redirect mid-pass. *Real cooperation, not handoff.* This is the moment DASH-EOI becomes a swarm, not a pipeline.

### 2.3  Self-modifying prompts (autonomous loop)
Lessons → A/B runner → winners land into a `_evolution/` branch → a weekly diff surfaces for Boss approval. The system mutates its own DNA; Boss is the regulator.

### 2.4  Beyond Ollama
Swap to vLLM or llama-cpp with continuous batching. Same pipeline, faster floor. Add token-level streaming and per-request priorities.

### 2.5  Distributed runs across machines
When a second machine appears, the pool becomes cluster-aware. Workers register; the dispatcher load-balances by GPU memory available. The dyad becomes a swarm.

### 2.6  Embedding-based semantic dedup
Reducer currently dedupes by string. v2 uses local embeddings (`nomic-embed-text` or `bge-small`) to dedupe by meaning. Stops the "same fact, different wording" problem in tree-reduce.

### 2.7  Retrieval-augmented synthesis
For tasks with verifiable claims (legal, scientific), the synthesizer gets the *raw chunks* as retrievable context, not just the digest. Citations become provable.

---

## Anti-roadmap (deliberately NOT building)

- **Vector DB.** Map-reduce doesn't need retrieval most of the time; adding it now is premature optimization.
- **Web UI.** The CLI + filesystem is the UI. HTML doubles maintenance.
- **Agent-to-agent chat history.** State on disk wins over conversational state every time.
- **Auto-tuning concurrency.** Two workers is the floor. Measure before tuning.
- **A "DashEI on Anthropic" mode.** That breaks the whole thesis.

---

## Open questions for Davara

- Is `[DISAGREEMENT]` propagation correct, or should the reducer try harder to resolve before bailing?
- Should the synthesizer get raw chunks (not just digest) when verbatim quotes matter?
- At what input size does collapse stop being enough? Where's the cliff?
- Can we make the persona panel adaptive — DashEI picks her own personas based on the task?

---

## Tracking metrics (v1.1 baseline)

| Metric | v1.1 baseline | v1.2 target | v2.0 target |
|---|---:|---:|---:|
| Quality floor (P50/40) | 36 | 38 | 40 |
| Median run time, medium class | 120s | 90s | 60s |
| End-to-end, 200K input | (untested) | 12 min | 6 min |
| Escalation rate, large class | (untested) | <20% | <10% |
| Lessons → landed mutations / week | 0 | 1+ | 3+ |

---

\\Hold Fast//
