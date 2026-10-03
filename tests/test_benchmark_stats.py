import importlib.util
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / "eval" / "benchmark_latency.py"
spec = importlib.util.spec_from_file_location("benchmark_latency", PATH)
bm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bm)


def test_percentile_nearest_rank():
    vals = list(range(1, 101))
    assert bm.percentile(vals, 50) == 50
    assert bm.percentile(vals, 95) == 95
    assert bm.percentile([7], 95) == 7


def test_summarize_and_run_config_with_a_fake_pipeline():
    calls = []

    def fake_ask(question, user_role, redact):
        calls.append((question, user_role, redact))
        return {"timings_ms": {"retrieve": 10, "redact": 20, "llm": 300, "post": 1, "total": 331}}

    qs = [{"question": f"q{i}", "user_role": "hr"} for i in range(4)]
    rows = bm.run_config(fake_ask, qs, rbac=True, redact=True, warmup=2)
    assert len(rows) == 4 and len(calls) == 6  # warm-up calls are not recorded
    assert calls[0][1] == "hr" and calls[0][2] is True
    s = bm.summarize(rows)
    assert s["llm"] == {"mean": 300.0, "p50": 300.0, "p95": 300.0, "max": 300.0}

    bm.run_config(fake_ask, qs, rbac=False, redact=False, warmup=0)
    assert calls[-1][1] is None  # baseline config sends no role
