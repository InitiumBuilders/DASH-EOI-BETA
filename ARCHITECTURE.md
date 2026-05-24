# Outlier-Deep-Think — Architecture

*Davara Outlier Intelligence (Davara-OI) · Framework v1.0 · 2026-05-24*

> **Names:** Outlier-Deep-Think (`odt`) · Outlier-Intel-Mode (`oim`) · Davara-OI
>
> **Mission:** Let a small local model produce work of an outlier model — by spending tokens deliberately, in parallel where it helps, in series where it must, with state on disk and reflection in the loop.

---

## 0. First Principles

These are the load-bearing assumptions. If we change one, the architecture changes.

| # | Principle | Consequence |
|---|---|---|
| 1 | **Tokens are the budget. Context is the constraint.** | Every design choice optimizes for what fills the 65K window when DashEI is thinking about a problem. |
| 2 | **Disk is bigger than memory. Always.** | All inter-phase state lives in files. The pipeline survives crashes, context resets, and restarts. |
| 3 | **Parallel where independent. Serial where coupled.** | Map step parallelizes (independent chunks). Reduce/synthesize is serial (depends on map outputs). |
| 4 | **Reflection is mandatory, not optional.** | Every run ends with a written reflection that mutates the system for next time. |
| 5 | **Escalation has rules.** | DashEI tries first. Davara is called only when explicit criteria fire — never as default. |
| 6 | **Receipts always.** | Every chunk has an ID, a file path, a token count, a duration. No claim without a receipt. |
| 7 | **Systems thinking through the spine.** | The pipeline itself is a system. We model it as stocks (chunks), flows (LLM calls), and feedback loops (reflection → prompt mutation). |

---

## 1. The Pipeline (top to bottom)

```
┌──────────────────────────────────────────────────────────────────┐
│ INTAKE      large request + optional context files               │
│   ↓         classify: small / medium / large / outlier           │
│   ↓                                                              │
│ PLAN        Davara writes the plan ONLY for outlier-class jobs.  │
│   ↓         DashEI writes her own plan for small/medium/large.   │
│   ↓                                                              │
│ CHUNK       semantic chunking with overlap; per-chunk file       │
│   ↓                                                              │
│ MAP         parallel pool (N=2) → each chunk gets full context   │
│   ↓         output: per-chunk summary file (structured)          │
│   ↓                                                              │
│ REDUCE      tree-reduce summaries (pairs → groups → root)        │
│   ↓         each level fits inside DashEI's window               │
│   ↓                                                              │
│ SYNTHESIZE  final answer / final code / final design             │
│   ↓                                                              │
│ REVIEW      self-critique pass (5 lenses)                        │
│   ↓                                                              │
│ ESCALATE?   if quality_score < threshold → hand to Davara        │
│   ↓                                                              │
│ DELIVER     to Boss. Receipts attached.                          │
│   ↓                                                              │
│ REFLECT     write lesson file; mutate prompts; bump version      │
└──────────────────────────────────────────────────────────────────┘
```

Every arrow is a file write. The pipeline is **directory-driven**: each run gets a `runs/<run-id>/` folder, and stages emit numbered subdirs (`01_intake/`, `02_plan/`, ..., `09_reflect/`). You can resume any run at any stage by replaying from the last completed file.

---

## 2. Sizing & Routing (the brain at the front door)

| Class | Input tokens | Strategy | Davara involvement |
|---|---|---|---|
| **Small** | < 8K | Single DashEI call. No chunking. | None |
| **Medium** | 8K–40K | Single DashEI call with intentional structure. | None |
| **Large** | 40K–200K | Chunk + map-reduce + synthesize. | None |
| **Outlier** | > 200K *or* user-flagged | Davara writes the plan. DashEI executes. Davara verifies at end. | Plan + final review |

**User can force the class:** `odt --class outlier "..."` — overrides the auto-classifier.

---

## 3. Chunking — semantic, not naive

Naive chunking (every N tokens, hard cut) destroys signal. We do **semantic chunking**:

1. **Detect the structure** of the input — is it code (split on functions/files), prose (split on headings/paragraphs), JSON (split on top-level keys), or unstructured (split on token windows with sentence-boundary respect)?
2. **Aim for chunks of ~6,000 tokens** with **~500 token overlap** on either side. This keeps each map call deeply inside the 65K window with room for the system prompt, the chunk, the task instruction, and the response.
3. **Each chunk gets metadata:** index, origin offset, parent doc, token count, hash, structural type.
4. **A chunk is never split mid-symbol** — function definitions, code blocks, JSON objects stay intact even if they push a chunk slightly past the target.

---

## 4. Map — the parallel pool

This is where two workers run in harmony.

```
┌─────────────┐
│  chunk[0]   │ ─────► worker_A ─────►  summary[0].json
│  chunk[1]   │ ─────► worker_B ─────►  summary[1].json
│  chunk[2]   │ ─────► worker_A ─────►  summary[2].json  (A returned first)
│  chunk[3]   │ ─────► worker_B ─────►  summary[3].json
│   ...       │
└─────────────┘
```

**Concurrency:** 2 workers by default. Configurable up to whatever `OLLAMA_NUM_PARALLEL` permits. Each worker is a Python coroutine making an HTTP call to Ollama; Ollama's scheduler handles the GPU-level batching.

**Per-chunk prompt structure (the worker prompt):**

```
You are DashEI in a Map worker. You will receive ONE chunk.
Your job: extract a structured summary of THIS chunk in JSON.

Fields:
  "summary"     : 60–80 word distillation of the chunk's core content
  "key_facts"   : 3-7 atomic facts pulled from the chunk
  "concerns"    : anything ambiguous, contradictory, or worth flagging
  "actions"     : if the chunk implies a concrete next step, list it
  "systems"     : if the chunk reveals a stock, flow, or feedback loop, name it
  "weight"      : 1-5 — how important is this chunk to the overall task?

Do NOT try to answer the whole task. Do NOT speculate beyond this chunk.
You are one voice in a council. Stay tight. Stay accurate.

CHUNK:
<chunk text here>
```

**Output schema is rigid.** The reducer parses JSON; loose output fails fast and triggers a retry with stricter wording.

---

## 5. Reduce — tree synthesis

Once the map stage finishes (M summaries on disk), we tree-reduce:

```
[s0, s1, s2, s3, s4, s5, s6, s7]
       ↓ pair (s0+s1), (s2+s3), ...
[r00, r01, r02, r03]
       ↓ pair (r00+r01), (r02+r03)
[r10, r11]
       ↓ pair (r10+r11)
[r20]  ← the root: a structured digest of everything
```

Each level keeps every reducer call inside DashEI's window. Each reducer prompt:

```
You are DashEI in a Reduce worker. You will receive K structured summaries.
Merge them into ONE structured summary at the same schema, preserving:
- All non-redundant key_facts (dedupe by meaning)
- All concerns (escalating any that appear in 2+ children)
- All actions (consolidated, no duplicates)
- The strongest systems observations (paradigm > goals > loops > params)
- A new "summary" that captures the merged content in 80-120 words

If two children disagree on a fact, list BOTH with their source chunk IDs.
Do not invent. Do not smooth over disagreement.
```

The root is a structured digest ready for the synthesizer.

---

## 6. Synthesize — the answer

Synthesis prompt loads:
- The original task statement
- The root digest from reduce
- Any constraints (output format, length, language, code style)
- A worked example if the task type has one

DashEI now has the *meaning* of the whole input compressed into her window. She writes the answer in one focused pass.

---

## 7. Review — the five lenses

Same as her existing Batching Protocol. Run them in order, re-run all five if any pass changes anything:

| Lens | Question |
|---|---|
| **Clarity** | Could a tired Boss read this in 30 seconds and understand the takeaway? |
| **Slop** | Any filler, default-LLM phrasing, decorative bullets? |
| **Receipts** | Does every claim have a file path, line number, or test? |
| **Restraint** | What can I delete without losing meaning? |
| **Canon** | Does this honor Motus Mindset, eight non-negotiables, Meadows frame? |

Convergence usually takes 2 passes. We cap at 4.

---

## 8. Escalate — when DashEI calls Davara

DashEI escalates when ANY of the following fire:

1. **Review repeatedly fails canon or restraint** (4+ refinement loops without convergence)
2. **The synthesizer output references "I'm uncertain" or "this may be wrong" more than twice**
3. **The user flagged `--outlier` upfront**
4. **Reduce produced contradictions that DashEI cannot resolve from the chunks alone**
5. **The task class is `outlier` and we are at the planning or final review stage**

Escalation **does not mean** "Davara takes over." It means: DashEI packages her current state (root digest + draft answer + concerns list) and sends Davara a tight ask. Davara replies with a targeted correction. DashEI then completes the work.

**Escalation packet format:**

```json
{
  "run_id": "...",
  "task_one_line": "...",
  "root_digest_path": "runs/<id>/05_reduce/root.json",
  "draft_answer_path": "runs/<id>/06_synthesize/answer.md",
  "specific_question": "<the one question DashEI needs answered>",
  "what_dashei_tried": "<2-3 sentences>",
  "constraints": [...]
}
```

Davara reads the digest + draft + question, returns 200-400 words of targeted correction. DashEI integrates and ships.

---

## 9. Reflect — the feedback loop that makes this exponential

Every run, win or fail, ends with a written reflection saved to `lessons/<date>__<run-id>.md`:

```
## Run <id> — <task one-liner>
- Class: <small/medium/large/outlier>
- Chunks: <N>
- Wall time: <s>
- DashEI calls: <count>
- Davara calls: <count>
- Escalation triggered: <yes/no, why>
- Quality (1-5, Boss-rated when provided): <n>

### What worked
...

### What struggled
...

### Prompt mutations to try next time
- worker_prompt_v<n+1>: <diff>
- reducer_prompt_v<n+1>: <diff>

### Open questions for Davara
...
```

**Reflection is not optional.** The reflection writer runs at the end of every pipeline. Empty lessons are caught and trigger a stricter prompt next time.

**Prompt evolution:** Worker/reducer/synthesizer prompts are versioned files in `odt/prompts/`. Each lesson can propose a v(n+1). Mutations only land after a side-by-side test against the same input shows improvement on at least one of: shorter runtime, higher Boss rating, fewer escalations.

---

## 10. Support Pathways — sub-agent spawning

For tasks that benefit from specialist views, DashEI spawns **support agents**: same model, different prompt persona, run in parallel alongside her main pool.

Built-in support personas:

| Persona | When she summons it |
|---|---|
| **Critic** | Adversarial review of a draft — find what's wrong |
| **Tester** | Generate test cases for a piece of code |
| **Refactorer** | Propose cleaner shape without changing behavior |
| **Steel-Manner** | Build the strongest case for the option DashEI did NOT pick |
| **Systems-Mapper** | Draw the stocks/flows/loops behind a problem |

Each persona is a prompt-only spec in `odt/personas/<name>.md`. Spawning one is just another worker call with that persona's prompt. **No extra processes, no orchestration overhead.** The harmony comes from the asymmetric prompts running concurrently.

---

## 11. The Two-Agent Dance (Davara × DashEI long-term loop)

Three modes:

1. **Solo DashEI** — small to large class. Davara does not appear.
2. **Sketched Davara + Execute DashEI** — outlier class. Davara writes the plan; DashEI does all the chunk work. Davara reviews the final.
3. **Tight Loop** — high-stakes work where Davara reviews the root digest mid-pipeline and adjusts the synthesizer prompt before DashEI writes the final answer.

The dance is **explicit and traced**. Every cross-agent message is logged in the run folder. Over time, lessons identify when each mode wins, and the auto-router gets sharper.

---

## 12. State Layout (what disk looks like)

```
~/.hermes/profiles/dashei/workspace/davara-oi/
├── ARCHITECTURE.md                 ← this file
├── README.md                       ← quick-start
├── OI-NEXT-STEPS.md                ← evolution roadmap
├── PROMPTS/
│   └── CORE_REQUEST_2026-05-24.md  ← Boss's founding prompt
├── odt/
│   ├── pipeline.py                 ← the orchestrator (CLI entry)
│   ├── worker.py                   ← LLM call wrapper, retries, JSON parse
│   ├── chunker.py                  ← semantic chunking
│   ├── pool.py                     ← parallel async pool
│   ├── reducer.py                  ← tree reduce
│   ├── reflect.py                  ← post-run reflection writer
│   ├── escalate.py                 ← Davara handoff helper
│   ├── prompts/
│   │   ├── worker_v1.md
│   │   ├── reducer_v1.md
│   │   ├── synthesizer_v1.md
│   │   └── reflector_v1.md
│   └── personas/
│       ├── critic.md
│       ├── tester.md
│       ├── refactorer.md
│       ├── steelmanner.md
│       └── systems_mapper.md
├── runs/
│   └── <YYYY-MM-DD_HHMMSS>__<slug>/
│       ├── 00_input.txt
│       ├── 01_intake/classification.json
│       ├── 02_plan/plan.md
│       ├── 03_chunk/chunk_000.txt ... chunk_NNN.txt
│       ├── 04_map/summary_000.json ... summary_NNN.json
│       ├── 05_reduce/level_0/, level_1/, ..., root.json
│       ├── 06_synthesize/answer.md
│       ├── 07_review/review.md
│       ├── 08_escalation/  (only if triggered)
│       ├── 09_reflect/lesson.md
│       └── manifest.json   ← run-level metadata
└── lessons/
    └── <YYYY-MM-DD>__<run-id>.md   ← symlinks or copies for fast scan
```

---

## 13. Failure Modes (designed-for, not surprised-by)

| Failure | Detection | Recovery |
|---|---|---|
| Worker returns invalid JSON | json.loads raises | Retry with stricter wording, max 3 attempts, then quarantine chunk |
| Ollama unreachable mid-run | HTTP timeout | Backoff + retry; if 3 retries fail, pause run, write resume token |
| Tree reduce can't converge (children contradict beyond resolution) | Reducer flags `unresolved` | Escalate to Davara with the specific contradiction |
| Reflection writer produces empty file | Post-write size check | Re-run with explicit "you must list at least one struggle" prompt |
| GPU OOM during parallel map | Ollama 500 | Drop concurrency by 1, restart map phase from last successful chunk |

---

## 14. Invocation Surface

**Shell:**
```bash
odt "your task or path/to/file or @url"
odt --class outlier "..."
odt --concurrency 2 "..."
odt --resume <run-id>
odt --reflect-only <run-id>
oim ...   # alias for odt
```

**Python:**
```python
from davara_oi.odt.pipeline import run
result = run(task="...", input_paths=[...], force_class="outlier")
```

**Hermes skill:** Loading the skill `outlier-deep-think` injects this whole architecture into the agent's context and provides the shell commands.

---

## 15. Performance Targets (v1.0)

| Metric | Target |
|---|---|
| Time to first chunk summary | < 15s after intake |
| End-to-end on 50K-token input | < 4 minutes |
| End-to-end on 200K-token input | < 15 minutes |
| Escalation rate on large class | < 15% |
| Reflection-induced prompt mutations landing per week | ≥ 1 |

These are floors, not ceilings. We beat them by Q2.

---

## 16. North Stars

- **DashEI does the work. Davara does the judgment.**
- **State on disk, not in memory.**
- **Every run teaches the next run.**
- **Receipts before prose.**
- **Restraint over decoration.**
- **The dyad is the unit.**

\\Hold Fast//
