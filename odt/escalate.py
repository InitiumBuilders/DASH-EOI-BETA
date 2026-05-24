"""odt.escalate — write an escalation packet for Davara when DashEI can't close.

This module produces the JSON packet only. The actual delivery to Davara
happens via Hermes (e.g. piping the packet into a `hermes -z` call, or
having the cloud agent read the file). The orchestrator never blocks
waiting for Davara — escalation runs are produced and saved; the operator decides
when to involve Davara.
"""

from __future__ import annotations
import json
from pathlib import Path


def write_escalation_packet(
    run_dir: Path,
    task_one_line: str,
    specific_question: str,
    what_dashei_tried: str,
    constraints: list[str] | None = None,
) -> Path:
    packet = {
        "run_id": run_dir.name,
        "task_one_line": task_one_line,
        "root_digest_path": str(run_dir / "05_reduce" / "root.json"),
        "draft_answer_path": str(run_dir / "06_synthesize" / "answer.md"),
        "specific_question": specific_question,
        "what_dashei_tried": what_dashei_tried,
        "constraints": constraints or [],
    }
    out = run_dir / "08_escalation"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "packet.json"
    path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def should_escalate(
    *,
    klass: str,
    refinement_loops: int,
    digest: dict,
    forced: bool = False,
) -> tuple[bool, str]:
    if forced:
        return True, "user forced --outlier"
    if klass == "outlier":
        return True, "task classified as outlier"
    if refinement_loops >= 4:
        return True, f"review failed to converge after {refinement_loops} loops"
    concerns = digest.get("concerns", []) or []
    escalated_concerns = [c for c in concerns if isinstance(c, str) and c.startswith("[ESCALATED]")]
    if len(escalated_concerns) >= 3:
        return True, f"{len(escalated_concerns)} cross-chunk escalated concerns"
    disagreements = sum(
        1 for f in digest.get("key_facts", []) if isinstance(f, str) and f.startswith("[DISAGREEMENT]")
    )
    if disagreements >= 2:
        return True, f"{disagreements} unresolved cross-chunk disagreements"
    return False, ""
