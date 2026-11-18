import importlib
import sys
import types

import pytest
from fastapi.testclient import TestClient

KEYS = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
        "GITHUB_TOKEN", "PERPLEXITY_API_KEY", "DEEPSEEK_API_KEY"]


def load_app(monkeypatch, tmp_path, **env):
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **kw: False)
    stub = types.ModuleType("orchestrator")

    async def roundtable(q, ps):
        return {"mode": "roundtable", "providers": ps}

    async def debate(q, ps):
        return {"mode": "debate", "providers": ps}

    stub.roundtable, stub.debate = roundtable, debate
    monkeypatch.setitem(sys.modules, "orchestrator", stub)
    (tmp_path / "static").mkdir()
    monkeypatch.chdir(tmp_path)
    for mod in ("config", "providers", "main"):
        sys.modules.pop(mod, None)
    main = importlib.import_module("main")
    return main, TestClient(main.app)


def names(client):
    return {p["name"]: p for p in client.get("/api/providers").json()["providers"]}


def test_deepseek_hidden_without_key(monkeypatch, tmp_path):
    _, c = load_app(monkeypatch, tmp_path, OPENAI_API_KEY="sk-x")
    ps = names(c)
    assert "deepseek" not in ps
    assert ps["openai"]["ready"] and not ps["perplexity"]["ready"]
    assert c.post("/api/chat", json={"provider": "deepseek", "messages": []}).status_code == 400


def test_empty_key_counts_as_missing(monkeypatch, tmp_path):
    _, c = load_app(monkeypatch, tmp_path, DEEPSEEK_API_KEY="  ")
    assert "deepseek" not in names(c)


def test_deepseek_visible_and_limited_with_key(monkeypatch, tmp_path):
    _, c = load_app(monkeypatch, tmp_path, DEEPSEEK_API_KEY="ds-key")
    ds = names(c)["deepseek"]
    assert ds["ready"] and ds["limited"]


def test_openai_key_not_leaked_to_other_provider(monkeypatch, tmp_path):
    _, c = load_app(monkeypatch, tmp_path, OPENAI_API_KEY="sk-SECRET")
    r = c.post("/api/chat", json={"provider": "perplexity",
                                  "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 400  # nem indul hívás OPENAI kulccsal a perplexity felé


def test_multi_rejects_not_ready_and_bad_mode(monkeypatch, tmp_path):
    _, c = load_app(monkeypatch, tmp_path, OPENAI_API_KEY="sk-x")
    r = c.post("/api/multi", json={"question": "q", "providers": ["openai", "gemini"]})
    assert r.status_code == 400 and "gemini" in r.json()["detail"]
    r = c.post("/api/multi", json={"question": "q", "providers": ["openai"], "mode": "x"})
    assert r.status_code == 400
    r = c.post("/api/multi", json={"question": "q", "providers": ["openai"]})
    assert r.status_code == 200


def test_openai_compatible_uses_own_key_and_base_url(monkeypatch, tmp_path):
    main, c = load_app(monkeypatch, tmp_path, OPENAI_API_KEY="sk-SECRET",
                       DEEPSEEK_API_KEY="ds-key")
    providers = sys.modules["providers"]
    seen = {}

    class FakeClient:
        def __init__(self, api_key, base_url):
            seen.update(api_key=api_key, base_url=base_url)
            self.chat = types.SimpleNamespace(completions=self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def create(self, model, messages):
            seen["model"] = model
            msg = types.SimpleNamespace(content="ok")
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    monkeypatch.setattr(providers, "AsyncOpenAI", FakeClient)
    r = c.post("/api/chat", json={"provider": "deepseek",
                                  "messages": [{"role": "user", "content": "hi"}]})
    assert r.json()["answer"] == "ok"
    assert seen == {"api_key": "ds-key", "base_url": "https://api.deepseek.com/v1",
                    "model": "deepseek-chat"}


def test_upstream_error_is_502_without_details(monkeypatch, tmp_path):
    _, c = load_app(monkeypatch, tmp_path, ANTHROPIC_API_KEY="sk-ant-x")
    providers = sys.modules["providers"]

    async def boom(cfg, messages):
        raise RuntimeError("secret internal detail")

    monkeypatch.setitem(providers._DISPATCH, "anthropic", boom)
    r = c.post("/api/chat", json={"provider": "anthropic", "messages": []})
    assert r.status_code == 502 and "secret" not in r.json()["detail"]
