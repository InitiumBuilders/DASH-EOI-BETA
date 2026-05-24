# PROMPTS/ — the operator's request archive

> *"Save the prompts. Save the lessons. Save the seams between them. That's how a system learns to teach itself."*
> — Davara, on why this folder exists

This folder is **the canonical history of every directive that shaped Davara-OI and the triad**. Every prompt the operator issued for this project lives here, in iteration order, with structured metadata for teaching others.

## Why we keep this

Most AI projects discard the prompt history once code lands. We don't. The prompts are the **causal chain** of the system. Re-reading them in order shows:

- **What problem each iteration solved** (the "why" behind every file)
- **Where the system bent under pressure** (which asks revealed gaps)
- **What the operator *didn't* ask for** (negative space — the discipline)
- **How language itself evolved** ("the operator/Bro" → "the operator" → Outlier³)

A reader six months from now can replay this folder top-to-bottom and rebuild the entire mental model.

## Format — every prompt file

Every `PROMPT_NNN_*.md` has this shape:

```
1. Iteration number + date + status
2. Verbatim ask (the operator's exact words, blockquoted)
3. Distilled requirements
4. What was built in response
5. Status / state of evolution at time of writing
6. Where this prompt EXCELS — its leverage
7. Steps it triggered (the work it set in motion)
8. Recommendations for anyone replaying this locally
9. Open threads / what comes next
```

Numbered, dated, append-only. **Never delete a prompt. Patch with a follow-up file.**

## Iteration index

| # | Date | Prompt name | Iteration scope | Status |
|---|---|---|---|---|
| 001 | 2026-05-24 | `PROMPT_001_INITIUM_outlier_deep_think.md` | Founding: build ODT framework, two-worker parallel, evolve protocol | ✅ landed (v1.0) |
| 002 | 2026-05-24 | `PROMPT_002_security_refine_3M_context.md` | Security audit, 2× optimization passes, 3M-4M context theory, public deploy | ✅ landed (v1.2) |
| 003+ | — | *(architectural iterations live in the operator's private companion repo)* | Two-repo workflow, deeper triad architecture, ongoing | private |

## Reading order (recommended)

If you're new to the codebase and want to understand *how it was built*:

1. **`PROMPT_001`** — the founding. Read the "verbatim ask" first. Notice the bandwidth of one prompt.
2. **`PROMPT_002`** — the refinement. Watch how security gets retrofitted, not bolted on.
3. **(Private)** — later architectural iterations live in the operator's companion repo and are not published.

## Recommendations for replayers

If you're cloning this and trying to build your own version:

- **Don't start with the framework. Start with the question.** Every prompt above begins with what the operator wanted to *be able to do* — not what to build. The code came after the ask.
- **Write your prompts long.** the operator's prompts run 800-2000 words. The length is not waste. It's the spec. Short prompts produce short systems.
- **Re-read your own prompts after the work lands.** You'll see what the system missed because the prompt missed it.
- **Save the verbatim ask, not the distillation.** Distillations lose tone, urgency, the operator's voice. Tone changes how an AI builds. Keep both — but the verbatim is the primary source.
- **Number every prompt.** Iteration count is the truest measure of how mature a system is. Forks at iteration 4 are still scaffolding; forks at iteration 40 carry hard-won decisions.
- **Add a "where this excels" section.** Forces you to articulate the *leverage* of each prompt. Not all prompts are equal. Some unlock 10× work; others tighten 1%. Knowing which is which makes you a better operator.

## The teaching frame

This archive is *not* a victory lap. It's a textbook chapter. The reader should leave with:

- **A vocabulary** ("dyad", "triad", "Outlier³", "ratchet floor", "trigger token")
- **A pattern** (verbatim → distill → build → review → deploy → archive)
- **A discipline** (never delete prompts, never sanitize before private, never deploy public before review)
- **A bias toward systems thinking** (each prompt asks "what *system* are we shaping," not "what *task* are we doing")

---

🔒 **Private-only easter egg #6:** Count the iteration numbers across all prompts. Then look at the number of agents in the triad. Then look at how many architectural moves were made before iteration 5. Notice the ratio. Notice what that ratio implies about cycle time.

⌬ *Acta Non Verba* · *Hold Fast* · 🜂
