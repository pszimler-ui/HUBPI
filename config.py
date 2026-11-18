import os
from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str | None = None) -> str | None:
    """Üres stringet is hiányzónak vesz (pl. `DEEPSEEK_API_KEY=` a .env-ben)."""
    value = os.getenv(name, "").strip()
    return value or default


PROVIDERS = {
    "openai": {
        "kind": "openai_compatible",
        "api_key": _env("OPENAI_API_KEY"),
        "base_url": "https://api.openai.com/v1",
        "model": _env("OPENAI_MODEL", "gpt-4o-mini"),
        "limited": False,
    },
    "anthropic": {
        "kind": "anthropic",
        "api_key": _env("ANTHROPIC_API_KEY"),
        "model": _env("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
        "limited": False,
    },
    "gemini": {
        "kind": "gemini",
        "api_key": _env("GEMINI_API_KEY"),
        "model": _env("GEMINI_MODEL", "gemini-2.5-flash"),
        "limited": False,
    },
    # GitHub Models: hivatalos, OpenAI-kompatibilis végpont, sima PAT-tal
    # (fine-grained token, "Models: read" jogosultság). A api.githubcopilot.com
    # NEM fogad el közvetlenül PAT-ot.
    "copilot": {
        "kind": "openai_compatible",
        "api_key": _env("GITHUB_TOKEN"),
        "base_url": _env("GITHUB_MODELS_BASE_URL", "https://models.github.ai/inference"),
        "model": _env("GITHUB_MODELS_MODEL", "openai/gpt-4o"),
        "limited": False,
    },
    "perplexity": {
        "kind": "openai_compatible",
        "api_key": _env("PERPLEXITY_API_KEY"),
        "base_url": "https://api.perplexity.ai",
        "model": _env("PERPLEXITY_MODEL", "sonar"),
        "limited": False,
    },
    # DeepSeek – korlátozott hozzáférés: kulcs nélkül nem is listázzuk.
    "deepseek": {
        "kind": "openai_compatible",
        "api_key": _env("DEEPSEEK_API_KEY"),
        "base_url": "https://api.deepseek.com/v1",
        "model": _env("DEEPSEEK_MODEL", "deepseek-chat"),
        "limited": True,
    },
}


def is_ready(name: str) -> bool:
    return bool(PROVIDERS[name]["api_key"])


def is_visible(name: str) -> bool:
    """Limited provider csak akkor létezik a felület/API számára, ha van kulcsa."""
    cfg = PROVIDERS[name]
    return is_ready(name) or not cfg["limited"]


# ---------- AI Hub védelem (security.py) ----------
HUB_USER = _env("HUB_USER", "admin")
HUB_PASSWORD = _env("HUB_PASSWORD")  # üresen: nincs jelszó (csak helyi futtatáshoz!)
HUB_RATE_LIMIT = int(_env("HUB_RATE_LIMIT", "20"))  # fizetős kérés / perc / IP
