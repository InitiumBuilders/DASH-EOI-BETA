"""odt.quality — quality standards system.

DashEI tracks her own quality bar over time. Each run's judge verdict
gets logged, and the rolling P50/P90 of her scores becomes the new
floor. She does not allow herself to ship below floor; the floor
ratchets upward as she improves.

This is the "increase your standards over time" mechanism.
"""

from __future__ import annotations
import json
import statistics
import time
from dataclasses import dataclass, asdict
from pathlib import Path

from . import config as cfg


QUALITY_LOG = cfg.ROOT / "lessons" / "_quality.jsonl"
QUALITY_FLOOR = cfg.ROOT / "lessons" / "_quality_floor.json"


@dataclass
class QualityRecord:
    ts: str
    run_id: str
    task: str
    klass: str
    total: int
    faithful: int
    clear: int
    restrained: int
    signal: int
    verdict: str
    chars: int


def append_record(run_id: str, task: str, klass: str, judge: dict, chars: int) -> None:
    if not judge or "total" not in judge:
        return
    rec = QualityRecord(
        ts=time.strftime("%Y-%m-%d %H:%M:%S"),
        run_id=run_id,
        task=task[:160],
        klass=klass,
        total=int(judge.get("total", 0)),
        faithful=int(judge.get("faithful", 0)),
        clear=int(judge.get("clear", 0)),
        restrained=int(judge.get("restrained", 0)),
        signal=int(judge.get("signal", 0)),
        verdict=judge.get("verdict", "?"),
        chars=chars,
    )
    QUALITY_LOG.parent.mkdir(parents=True, exist_ok=True)
    with QUALITY_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")


def load_records() -> list[dict]:
    if not QUALITY_LOG.exists():
        return []
    out = []
    for line in QUALITY_LOG.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def compute_floor(records: list[dict] | None = None, window: int = 20) -> dict:
    """Compute the current quality floor from the last `window` records.

    Floor = P50 of total scores. Stretch = P90. We ratchet up: the floor
    never decreases, even if a recent run scored low.
    """
    records = records or load_records()
    if not records:
        return {"floor": 24, "stretch": 32, "count": 0}  # bootstrap values
    last = records[-window:]
    totals = [r["total"] for r in last]
    p50 = int(statistics.median(totals))
    p90 = int(statistics.quantiles(totals, n=10)[-1]) if len(totals) >= 10 else max(totals)

    prev = {}
    if QUALITY_FLOOR.exists():
        try:
            prev = json.loads(QUALITY_FLOOR.read_text())
        except Exception:
            pass
    prev_floor = prev.get("floor", 24)
    floor = max(prev_floor, p50)        # ratchet
    stretch = max(prev.get("stretch", 32), p90)

    out = {
        "floor": floor,
        "stretch": stretch,
        "count": len(records),
        "window_p50": p50,
        "window_p90": p90,
        "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    QUALITY_FLOOR.parent.mkdir(parents=True, exist_ok=True)
    QUALITY_FLOOR.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def trend(records: list[dict] | None = None) -> dict:
    """Compare recent runs to historical baseline."""
    records = records or load_records()
    if len(records) < 4:
        return {"trend": "insufficient_data", "recent_mean": 0, "historical_mean": 0}
    half = len(records) // 2
    hist_mean = statistics.mean(r["total"] for r in records[:half])
    recent_mean = statistics.mean(r["total"] for r in records[half:])
    delta = recent_mean - hist_mean
    if delta > 2:
        label = "improving"
    elif delta < -2:
        label = "declining"
    else:
        label = "stable"
    return {
        "trend": label,
        "recent_mean": round(recent_mean, 1),
        "historical_mean": round(hist_mean, 1),
        "delta": round(delta, 1),
    }


def report() -> str:
    records = load_records()
    floor = compute_floor(records)
    t = trend(records)
    lines = [
        "# Quality Report",
        "",
        f"- runs scored: **{floor['count']}**",
        f"- current floor: **{floor['floor']}/40** (set from P50 of last {min(20, floor['count'])} runs)",
        f"- stretch target: **{floor['stretch']}/40**",
        f"- trend: **{t['trend']}**  (recent mean {t['recent_mean']} vs historical {t['historical_mean']}, Δ {t.get('delta',0):+})",
        "",
        "## Latest runs",
    ]
    for r in records[-5:]:
        lines.append(f"- {r['ts']} · {r['klass']:<7} · {r['total']:>2}/40 · {r['verdict']:<10} · {r['task'][:60]}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(report())
