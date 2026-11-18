import logging
from typing import Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from config import PROVIDERS, is_ready, is_visible
import orchestrator
from orchestrator import OrchestratorError
from providers import ProviderError, ask
from security import guard, startup_warning

log = logging.getLogger("ai_hub")
app = FastAPI(title="AI Hub")
app.middleware("http")(guard)
startup_warning()


class ChatRequest(BaseModel):
    provider: str
    messages: List[Dict[str, str]]


class MultiRequest(BaseModel):
    question: str = Field(min_length=1, max_length=20_000)
    providers: List[str] = Field(min_length=1, max_length=10)
    mode: Literal["single", "compare", "roundtable", "debate", "critique"] = "roundtable"
    rounds: int = Field(2, ge=1, le=orchestrator.MAX_ROUNDS)  # csak debate
    lead: Optional[str] = None  # csak critique


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
    unknown = [p for p in req.providers if p not in PROVIDERS or not is_visible(p)]
    if unknown:
        raise HTTPException(400, f"Ismeretlen: {unknown}")
    not_ready = [p for p in req.providers if not is_ready(p)]
    if not_ready:
        raise HTTPException(400, f"Nincs API kulcs: {not_ready}")
    try:
        if req.mode == "single":
            if len(set(req.providers)) != 1:
                raise HTTPException(400, "Egy AI módban pontosan 1 providert válassz.")
            return await orchestrator.single(req.question, req.providers[0])
        if req.mode == "compare":
            return await orchestrator.compare(req.question, req.providers)
        if req.mode == "debate":
            return await orchestrator.debate(req.question, req.providers, req.rounds)
        if req.mode == "critique":
            return await orchestrator.critique(req.question, req.providers, req.lead)
        return await orchestrator.roundtable(req.question, req.providers)
    except (ProviderError, OrchestratorError) as e:
        raise HTTPException(400, str(e))
    except HTTPException:
        raise
    except Exception:
        log.exception("multi hiba")
        raise HTTPException(502, "A több-modelles hívás sikertelen.")


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def root():
    return FileResponse("static/index.html")
