from openai import AsyncOpenAI
from anthropic import AsyncAnthropic
from google import genai
from google.genai import types as genai_types

from config import PROVIDERS, is_ready, is_visible


class ProviderError(Exception):
    """Felhasználónak megmutatható hiba (4xx)."""


def _require(name: str) -> dict:
    if name not in PROVIDERS or not is_visible(name):
        raise ProviderError(f"Ismeretlen provider: {name}")
    if not is_ready(name):
        cfg = PROVIDERS[name]
        hint = "korlátozott hozzáférésű, " if cfg["limited"] else ""
        raise ProviderError(f"A(z) {name} {hint}nincs API kulcs beállítva a .env-ben.")
    return PROVIDERS[name]


def _split_system(messages: list) -> tuple[str, list]:
    system_parts, rest = [], []
    for m in messages:
        if m["role"] == "system":
            system_parts.append(m["content"])
        else:
            rest.append({"role": m["role"], "content": m["content"]})
    return "\n\n".join(system_parts), rest


async def _openai_compatible(cfg: dict, messages: list) -> str:
    # A kulcsot MINDIG explicit adjuk át: api_key=None esetén az SDK az
    # OPENAI_API_KEY env-et használná, és azt küldené el pl. a DeepSeeknek.
    client = AsyncOpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])
    async with client:
        resp = await client.chat.completions.create(model=cfg["model"], messages=messages)
    return resp.choices[0].message.content or ""


async def _anthropic(cfg: dict, messages: list) -> str:
    system, msgs = _split_system(messages)
    kwargs = {"system": system} if system else {}
    async with AsyncAnthropic(api_key=cfg["api_key"]) as client:
        resp = await client.messages.create(
            model=cfg["model"], max_tokens=2048, messages=msgs, **kwargs
        )
    return "".join(b.text for b in resp.content if b.type == "text")


async def _gemini(cfg: dict, messages: list) -> str:
    system, msgs = _split_system(messages)
    contents = [
        genai_types.Content(
            role="model" if m["role"] == "assistant" else "user",
            parts=[genai_types.Part(text=m["content"])],
        )
        for m in msgs
    ]
    config = genai_types.GenerateContentConfig(system_instruction=system) if system else None
    client = genai.Client(api_key=cfg["api_key"])
    resp = await client.aio.models.generate_content(
        model=cfg["model"], contents=contents, config=config
    )
    return resp.text or ""


_DISPATCH = {
    "openai_compatible": _openai_compatible,
    "anthropic": _anthropic,
    "gemini": _gemini,
}


async def ask(provider: str, messages: list) -> str:
    cfg = _require(provider)
    return await _DISPATCH[cfg["kind"]](cfg, messages)
