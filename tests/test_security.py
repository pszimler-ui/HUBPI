import sys

from test_app import load_app


def _fake_ask(monkeypatch):
    async def fake(p, m):
        return "ok"
    monkeypatch.setattr(sys.modules["orchestrator"], "ask", fake)


def test_no_password_means_open(monkeypatch, tmp_path):
    _, c = load_app(monkeypatch, tmp_path)
    assert c.get("/api/providers").status_code == 200


def test_password_required_everywhere(monkeypatch, tmp_path):
    _, c = load_app(monkeypatch, tmp_path, HUB_PASSWORD="titok")
    for path in ("/api/providers", "/docs", "/openapi.json", "/static/x"):
        r = c.get(path)
        assert r.status_code == 401, path
        assert "Basic" in r.headers["www-authenticate"]
    assert c.get("/api/providers", auth=("admin", "rossz")).status_code == 401
    assert c.get("/api/providers", auth=("mas", "titok")).status_code == 401
    assert c.get("/api/providers", auth=("admin", "titok")).status_code == 200


def test_custom_user_and_unicode_password(monkeypatch, tmp_path):
    _, c = load_app(monkeypatch, tmp_path, HUB_USER="pi", HUB_PASSWORD="árvíztűrő")
    import base64
    tok = base64.b64encode("pi:árvíztűrő".encode()).decode()
    assert c.get("/api/providers", headers={"Authorization": "Basic " + tok}).status_code == 200
    assert c.get("/api/providers", headers={"Authorization": "Basic !!!"}).status_code == 401


def test_bruteforce_lockout(monkeypatch, tmp_path):
    _, c = load_app(monkeypatch, tmp_path, HUB_PASSWORD="titok")
    for _ in range(10):
        assert c.get("/api/providers", auth=("admin", "x")).status_code == 401
    r = c.get("/api/providers", auth=("admin", "titok"))  # már a jó jelszó sem megy
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0


def test_rate_limit_on_paid_endpoints_only(monkeypatch, tmp_path):
    _, c = load_app(monkeypatch, tmp_path, OPENAI_API_KEY="k", HUB_RATE_LIMIT="3")
    _fake_ask(monkeypatch)
    body = {"question": "q", "providers": ["openai"], "mode": "single"}
    assert [c.post("/api/multi", json=body).status_code for _ in range(3)] == [200] * 3
    r = c.post("/api/multi", json=body)
    assert r.status_code == 429 and "3/perc" in r.json()["detail"]
    assert c.post("/api/chat", json={"provider": "openai", "messages": []}).status_code == 429
    assert c.get("/api/providers").status_code == 200  # olvasás nem korlátozott


def test_rate_limit_window_expires(monkeypatch, tmp_path):
    _, c = load_app(monkeypatch, tmp_path, OPENAI_API_KEY="k", HUB_RATE_LIMIT="1")
    _fake_ask(monkeypatch)
    sec = sys.modules["security"]
    now = [1000.0]
    monkeypatch.setattr(sec.time, "monotonic", lambda: now[0])
    body = {"question": "q", "providers": ["openai"], "mode": "single"}
    assert c.post("/api/multi", json=body).status_code == 200
    assert c.post("/api/multi", json=body).status_code == 429
    now[0] += 61
    assert c.post("/api/multi", json=body).status_code == 200
