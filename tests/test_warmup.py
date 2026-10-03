from secure_rag import pipeline


def test_pipeline_warm_up_loads_embedder_and_pii(monkeypatch):
    calls = []

    class FakeEmbedder:
        def encode(self, texts):
            calls.append(("embed", texts))

    monkeypatch.setattr(pipeline.resources, "_cache", {"embedder": FakeEmbedder()})
    monkeypatch.setattr(pipeline, "_warm_pii", lambda: calls.append(("pii",)))
    pipeline.warm_up()
    assert [c[0] for c in calls] == ["embed", "pii"]


def test_pii_warm_up_runs_a_real_analysis():
    from secure_rag.security import pii

    pii.warm_up()
    assert pii._analyzer is not None  # model is now loaded
