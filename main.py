import logging
from typing import Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import PROVIDERS, is_ready, is_visible
from orchestrator import debate, roundtable
from providers import ProviderError, ask

log = logging.getLogger("ai_hub")
app = FastAPI(title="AI Hub")


class ChatRequest(BaseModel):
    provider: str
    messages: List[Dict[str, str]]


class MultiRequest(BaseModel):
    question: str
    providers: List[str]
    mode: str = "roundtable"


@app.get("/api/providers")
def list_providers():
    return {
        "providers": [
            {
                "name": k,
                "model": v["model"],
                "ready": is_ready(k),
                "limited": v["limited"],
            }
            for k, v in PROVIDERS.items()
            if is_visible(k)
        ]
    }


@app.post("/api/chat")
async def chat(req: ChatRequest):
    try:
        return {"provider": req.provider, "answer": await ask(req.provider, req.messages)}
    except ProviderError as e:
        raise HTTPException(400, str(e))
    except Exception:
        log.exception("chat hiba (%s)", req.provider)
        raise HTTPException(502, f"A(z) {req.provider} hívása sikertelen.")


@app.post("/api/multi")
async def multi(req: MultiRequest):
    if req.mode not in ("roundtable", "debate"):
        raise HTTPException(400, f"Ismeretlen mód: {req.mode}")
    unknown = [p for p in req.providers if p not in PROVIDERS or not is_visible(p)]
    if unknown:
        raise HTTPException(400, f"Ismeretlen: {unknown}")
    not_ready = [p for p in req.providers if not is_ready(p)]
    if not_ready:
        raise HTTPException(400, f"Nincs API kulcs: {not_ready}")
    try:
        if req.mode == "debate":
            return await debate(req.question, req.providers)
        return await roundtable(req.question, req.providers)
    except ProviderError as e:
        raise HTTPException(400, str(e))
    except Exception:
        log.exception("multi hiba")
        raise HTTPException(502, "A több-modelles hívás sikertelen.")


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def root():
    return FileResponse("static/index.html")
