"""Per-stage latency benchmark for the pipeline.

Measures wall-clock time for retrieve, redact, llm, post-processing, and total, over the
answerable questions in eval/dataset.json, for three configurations (the same ones as the
accuracy eval). Needs ANTHROPIC_API_KEY, the built index, and the spaCy model.

Usage (from the project root, venv active):
    python eval/benchmark_latency.py --label my_machine
    python eval/benchmark_latency.py --label quick --n 10 --configs rbac_redact

Notes for reading the results:
- The "llm" stage is a network call to the Anthropic API and usually dominates; it varies
  with network, time of day, and model. Treat retrieve/redact/post as the part this code
  controls.
- Each configuration runs a short warm-up first (model loading is not counted).
- Numbers depend on the machine, so the output records the platform and model.
"""
import argparse
import json
import math
import os
import platform
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from secure_rag.pipeline import ask  # noqa: E402
from secure_rag.settings import K, MODEL  # noqa: E402

STAGES = ["retrieve", "redact", "llm", "post", "total"]
CONFIGS = {
    "baseline": {"rbac": False, "redact": False},
    "rbac": {"rbac": True, "redact": False},
    "rbac_redact": {"rbac": True, "redact": True},
}


def percentile(values, p):
    """Nearest-rank percentile."""
    s = sorted(values)
    return s[min(len(s) - 1, max(0, math.ceil(p / 100 * len(s)) - 1))]


def summarize(rows):
    """rows: list of timings_ms dicts -> {stage: {mean, p50, p95, max}} (milliseconds)."""
    out = {}
    for stage in STAGES:
        vals = [r[stage] for r in rows]
        out[stage] = {
            "mean": round(sum(vals) / len(vals), 1),
            "p50": round(percentile(vals, 50), 1),
            "p95": round(percentile(vals, 95), 1),
            "max": round(max(vals), 1),
        }
    return out


def run_config(ask_fn, questions, rbac, redact, warmup):
    for q in questions[:warmup]:
        ask_fn(q["question"], user_role=q["user_role"] if rbac else None, redact=redact)
    rows = []
    for q in questions:
        r = ask_fn(q["question"], user_role=q["user_role"] if rbac else None, redact=redact)
        rows.append(r["timings_ms"])
    return rows


def markdown_table(results):
    lines = ["| Config | Stage | mean (ms) | p50 (ms) | p95 (ms) | max (ms) |", "|---|---|---|---|---|---|"]
    for name, summary in results.items():
        for stage in STAGES:
            s = summary[stage]
            lines.append(f"| {name} | {stage} | {s['mean']} | {s['p50']} | {s['p95']} | {s['max']} |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="latency")
    ap.add_argument("--n", type=int, default=0, help="number of questions (0 = all answerable)")
    ap.add_argument("--warmup", type=int, default=2)
    ap.add_argument("--configs", default=",".join(CONFIGS), help="comma-separated subset")
    args = ap.parse_args()

    data = json.loads((ROOT / "eval" / "dataset.json").read_text(encoding="utf-8"))
    questions = [q for q in data if q["type"] == "answerable"]
    if args.n:
        questions = questions[: args.n]

    results = {}
    for name in args.configs.split(","):
        cfg = CONFIGS[name]
        print(f"Running {name} on {len(questions)} questions...", flush=True)
        results[name] = summarize(run_config(ask, questions, cfg["rbac"], cfg["redact"], args.warmup))

    print("\n" + markdown_table(results))
    out = {
        "label": args.label,
        "when": datetime.now().isoformat(timespec="seconds"),
        "model": MODEL,
        "k": K,
        "n_questions": len(questions),
        "warmup": args.warmup,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "results": results,
    }
    path = ROOT / "eval" / "results" / f"latency_{datetime.now():%Y%m%d_%H%M%S}_{args.label}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nSaved {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
