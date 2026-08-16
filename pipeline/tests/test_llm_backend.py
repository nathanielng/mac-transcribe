import pytest

from mac_transcribe import llm_backend


def test_generate_text_dispatches_to_bedrock(monkeypatch):
    calls = {}

    def fake_bedrock(prompt, model, region, profile, max_tokens):
        calls["args"] = (prompt, model, region, profile, max_tokens)
        return "bedrock result"

    monkeypatch.setattr(llm_backend, "_generate_bedrock", fake_bedrock)

    cfg = {
        "outline_backend": "bedrock",
        "bedrock_model": "global.anthropic.claude-sonnet-5",
        "bedrock_region": "us-east-1",
        "bedrock_profile": "default",
    }
    result = llm_backend.generate_text("hello", cfg, max_tokens=100)

    assert result == "bedrock result"
    assert calls["args"] == ("hello", "global.anthropic.claude-sonnet-5", "us-east-1", "default", 100)


def test_generate_text_dispatches_to_mlx_lm(monkeypatch):
    calls = {}

    def fake_mlx(prompt, model, max_tokens):
        calls["args"] = (prompt, model, max_tokens)
        return "mlx result"

    monkeypatch.setattr(llm_backend, "_generate_mlx_lm", fake_mlx)

    cfg = {"outline_backend": "mlx_lm", "mlx_outline_model": "mlx-community/Qwen3.5-4B-MLX-4bit"}
    result = llm_backend.generate_text("hello", cfg, max_tokens=50)

    assert result == "mlx result"
    assert calls["args"] == ("hello", "mlx-community/Qwen3.5-4B-MLX-4bit", 50)


def test_generate_text_defaults_to_bedrock_when_unset(monkeypatch):
    calls = {}
    monkeypatch.setattr(llm_backend, "_generate_bedrock", lambda *a: calls.setdefault("called", True) or "x")

    cfg = {"bedrock_model": "m", "bedrock_region": "r", "bedrock_profile": "p"}
    llm_backend.generate_text("hi", cfg, max_tokens=10)

    assert calls.get("called") is True


def test_generate_text_raises_on_unknown_backend():
    cfg = {"outline_backend": "carrier-pigeon"}

    with pytest.raises(ValueError, match="Unknown outline_backend"):
        llm_backend.generate_text("hi", cfg, max_tokens=10)


def test_load_mlx_model_caches_across_calls(monkeypatch):
    load_calls = []

    class FakeMLXModule:
        @staticmethod
        def load(model):
            load_calls.append(model)
            return (f"model-obj-{model}", f"tokenizer-{model}")

    monkeypatch.setitem(__import__("sys").modules, "mlx_lm", FakeMLXModule)
    llm_backend._model_cache.clear()

    first = llm_backend._load_mlx_model("some-model")
    second = llm_backend._load_mlx_model("some-model")

    assert first == second
    assert load_calls == ["some-model"]  # only loaded once, second call hit the cache
