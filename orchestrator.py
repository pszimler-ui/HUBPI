"""
AI Hub – orchestrátor.

Öt együttműködési minta:
  - single:      egy provider válaszol
  - compare:     mindenki függetlenül válaszol, csak összegyűjtjük
  - roundtable:  független válaszok → mindenki értékeli a többiekét
  - debate:      több körös vita, mindenki látja az előző kör összes válaszát
  - critique:    1 fő válaszol, a többiek kritizálják, a fő javít

Hibatűrés: ha egy provider elszáll vagy túllépi az időkorlátot, az "errors"
mezőbe kerül egy rövid, általános üzenettel, és KIMARAD a többieknek küldött
szövegből (a belső hibarészletek így nem jutnak el más szolgáltatókhoz).
"""

import asyncio
import logging

from providers import ProviderError, ask

log = logging.getLogger("ai_hub.orchestrator")

CALL_TIMEOUT = 120  # másodperc / hívás
MAX_ROUNDS = 4


class OrchestratorError(Exception):
    """Felhasználónak megmutatható hiba (pl. minden provider elszállt)."""


# ---------- segédfüggvények ----------------------------------------------

def _user(content: str) -> list[dict]:
    return [{"role": "user", "content": content}]


async def _call(provider: str, prompt: str) -> str:
    return await asyncio.wait_for(ask(provider, _user(prompt)), CALL_TIMEOUT)


def _describe(provider: str, exc: BaseException) -> str:
    if isinstance(exc, ProviderError):
        return str(exc)
    if isinstance(exc, asyncio.TimeoutError):
        return "Időtúllépés."
    log.error("%s hívás hiba", provider, exc_info=exc)
    return "A hívás sikertelen (részletek a szervernaplóban)."


async def _gather(prompts: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """Párhuzamosan hív; providerenként saját prompt. -> (válaszok, hibák)"""
    names = list(prompts)
    results = await asyncio.gather(
        *(_call(p, prompts[p]) for p in names), return_exceptions=True
    )
    answers, errors = {}, {}
    for p, r in zip(names, results):
        if isinstance(r, BaseException):
            if not isinstance(r, Exception):  # CancelledError, KeyboardInterrupt
                raise r
            errors[p] = _describe(p, r)
        else:
            answers[p] = r
    return answers, errors


async def _ask_all(prompt: str, providers: list[str]):
    return await _gather({p: prompt for p in providers})


def _transcript(answers: dict[str, str]) -> str:
    return "\n\n".join(f"[{p}]:\n{a}" for p, a in answers.items())


def _unique(providers: list[str]) -> list[str]:
    return list(dict.fromkeys(providers))  # duplikátum ki, sorrend marad


def _require_any(answers: dict, errors: dict) -> None:
    if not answers:
        raise OrchestratorError(f"Egyik provider sem válaszolt: {errors}")


# ---------- módok ---------------------------------------------------------

async def single(question: str, provider: str) -> dict:
    answers, errors = await _ask_all(question, [provider])
    _require_any(answers, errors)
    return {"mode": "single", "provider": provider, "answer": answers[provider]}


async def compare(question: str, providers: list[str]) -> dict:
    answers, errors = await _ask_all(question, _unique(providers))
    return {"mode": "compare", "answers": answers, "errors": errors}


async def roundtable(question: str, providers: list[str]) -> dict:
    providers = _unique(providers)
    round1, errors1 = await _ask_all(question, providers)
    _require_any(round1, errors1)

    prompts = {
        p: (
            f"Egy kérdésre több AI adott választ. A te korábbi válaszod a [{p}] jelű"
            f"{'' if p in round1 else ' lett volna, de nem érkezett meg'}.\n\n"
            f"KÉRDÉS: {question}\n\n"
            f"VÁLASZOK:\n{_transcript(round1)}\n\n"
            f"Feladatod:\n"
            f"1) Kritikusan értékeld a válaszokat – mi bennük a jó, mi hiányzik, hol tévednek.\n"
            f"2) Ezután add meg a legjobb, összesített választ, felhasználva a jó meglátásokat.\n"
            f"Légy tömör és konkrét."
        )
        for p in round1  # aki az 1. körben elszállt, a 2.-ban nem költünk rá
    }
    round2, errors2 = await _gather(prompts)
    return {
        "mode": "roundtable",
        "round1": round1,
        "round2": round2,
        "errors": {"round1": errors1, "round2": errors2},
    }


async def debate(question: str, providers: list[str], rounds: int = 2) -> dict:
    if not 1 <= rounds <= MAX_ROUNDS:
        raise OrchestratorError(f"A körök száma 1 és {MAX_ROUNDS} között lehet.")
    active = _unique(providers)
    history, previous = [], None
    for r in range(1, rounds + 1):
        if previous is None:
            prompts = {p: question for p in active}
        else:
            prompts = {
                p: (
                    f"EREDETI KÉRDÉS: {question}\n\n"
                    f"ELŐZŐ KÖR VÁLASZAI:\n{_transcript(previous)}\n\n"
                    f"A te előző válaszod a [{p}] jelű. Finomítsd a többiek érvei alapján. "
                    f"Ha valakivel egyetértesz, mondd meg miért; ha nem, cáfold meg konkrétan. "
                    f"Légy tömör – ne ismételd magad feleslegesen."
                )
                for p in active
            }
        answers, errors = await _gather(prompts)
        history.append({"round": r, "answers": answers, "errors": errors})
        if not answers:
            break
        previous = answers
        active = list(answers)  # aki kiesett, nem folytatja
    _require_any(history[0]["answers"], history[0]["errors"])
    return {"mode": "debate", "question": question, "history": history}


async def critique(question: str, providers: list[str], lead: str | None = None) -> dict:
    providers = _unique(providers)
    if not providers:
        raise OrchestratorError("Nincs provider megadva.")
    lead = lead or providers[0]
    if lead not in providers:
        raise OrchestratorError(f"A fő provider ({lead}) nincs a kiválasztottak között.")
    critics = [p for p in providers if p != lead]
    if not critics:
        raise OrchestratorError("Legalább 2 provider kell a kritikához.")

    first_ans, first_err = await _ask_all(question, [lead])
    _require_any(first_ans, first_err)  # ha a fő elszáll, nem fizetünk a kritikusokért
    first = first_ans[lead]

    crit_prompt = (
        f"Az alábbi kérdésre a(z) {lead} modell ezt válaszolta:\n\n"
        f"KÉRDÉS: {question}\n\n"
        f"VÁLASZ:\n{first}\n\n"
        f"Add meg a kritikádat: mi hiányzik, mi pontatlan, mit lehetne jobban. "
        f"Légy konkrét és rövid."
    )
    critiques, crit_errors = await _ask_all(crit_prompt, critics)

    final = first
    final_error = None
    if critiques:
        fix_prompt = (
            f"KÉRDÉS: {question}\n\n"
            f"AZ EREDETI VÁLASZOD:\n{first}\n\n"
            f"KRITIKÁK:\n{_transcript(critiques)}\n\n"
            f"Add meg a javított válaszodat, figyelembe véve a kritikákat."
        )
        fixed, fix_err = await _ask_all(fix_prompt, [lead])
        final = fixed.get(lead, first)
        final_error = fix_err.get(lead)

    return {
        "mode": "critique",
        "lead": lead,
        "initial": first,
        "critiques": critiques,
        "final": final,
        "errors": {"critiques": crit_errors, "final": final_error},
    }
