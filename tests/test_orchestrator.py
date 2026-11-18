import asyncio
import importlib
import sys

import pytest

from providers import ProviderError  # noqa: E402  (conftest-mentes egyszerű import)


@pytest.fixture
def orch(monkeypatch):
    sys.modules.pop("orchestrator", None)
    mod = importlib.import_module("orchestrator")
    calls = []

    async def fake_ask(provider, messages):
        prompt = messages[0]["content"]
        calls.append((provider, prompt))
        if provider == "bad":
            raise RuntimeError("SECRET-internal https://x?key=abc")
        if provider == "nokey":
            raise ProviderError("A(z) nokey nincs API kulcs beállítva a .env-ben.")
        if provider == "slow":
            await asyncio.sleep(10)
        return f"{provider}-answer"

    monkeypatch.setattr(mod, "ask", fake_ask)
    monkeypatch.setattr(mod, "CALL_TIMEOUT", 0.05)
    mod.calls = calls
    return mod


def run(coro):
    return asyncio.run(coro)


def test_errors_not_leaked_to_other_providers(orch):
    out = run(orch.roundtable("q", ["a", "bad", "b"]))
    assert set(out["round1"]) == {"a", "b"}
    assert "SECRET" not in out["errors"]["round1"]["bad"]
    round2_prompts = [pr for p, pr in orch.calls[3:]]
    assert len(round2_prompts) == 2  # a hibás nem kap 2. kört
    assert all("SECRET" not in pr and "[bad]" not in pr for pr in round2_prompts)


def test_debate_tells_each_model_its_own_answer(orch):
    out = run(orch.debate("q", ["a", "b"], rounds=2))
    r2 = dict(orch.calls[2:])
    assert "[a] jelű" in r2["a"] and "[b] jelű" in r2["b"]
    assert len(out["history"]) == 2


def test_debate_round_limit(orch):
    with pytest.raises(orch.OrchestratorError):
        run(orch.debate("q", ["a"], rounds=50))


def test_timeout_is_reported(orch):
    out = run(orch.compare("q", ["a", "slow"]))
    assert out["answers"] == {"a": "a-answer"}
    assert out["errors"]["slow"] == "Időtúllépés."


def test_all_fail_raises(orch):
    with pytest.raises(orch.OrchestratorError):
        run(orch.roundtable("q", ["bad", "nokey"]))


def test_critique_stops_if_lead_fails(orch):
    with pytest.raises(orch.OrchestratorError):
        run(orch.critique("q", ["bad", "a"]))
    assert [p for p, _ in orch.calls] == ["bad"]  # kritikusokra nem költöttünk


def test_critique_happy_path_and_dedupe(orch):
    out = run(orch.critique("q", ["a", "b", "b"]))
    assert out["final"] == "a-answer" and list(out["critiques"]) == ["b"]
    assert [p for p, _ in orch.calls] == ["a", "b", "a"]


def test_critique_lead_must_be_selected(orch):
    with pytest.raises(orch.OrchestratorError):
        run(orch.critique("q", ["a", "b"], lead="zzz"))
