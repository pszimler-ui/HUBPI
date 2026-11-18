"""
Egyszerű védelem az AI Hub elé.

- Jelszó (HTTP Basic Auth): ha a .env-ben meg van adva a HUB_PASSWORD, minden
  oldal és API végpont jelszót kér. A böngésző egyszer kérdez, utána megjegyzi.
- Kéréskorlát: IP-címenként legfeljebb HUB_RATE_LIMIT fizetős kérés
  (/api/chat, /api/multi) percenként.
- Próbálkozás-védelem: IP-címenként percenként legfeljebb 10 hibás jelszó.

FIGYELEM: a Basic Auth titkosítatlan HTTP-n olvasható a hálózaton. Interneten
csak HTTPS mögött (pl. Caddy / nginx / Cloudflare Tunnel) használd.
"""

import base64
import logging
import secrets
import threading
import time
from collections import defaultdict, deque

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from config import HUB_PASSWORD, HUB_RATE_LIMIT, HUB_USER

log = logging.getLogger("ai_hub.security")

WINDOW = 60.0  # másodperc
MAX_FAILED_LOGINS = 10
PAID_PATHS = ("/api/chat", "/api/multi")


class SlidingWindow:
    """Kulcsonként (IP) számolja az elmúlt WINDOW másodperc eseményeit."""

    def __init__(self, limit: int, window: float = WINDOW):
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, q: deque, now: float) -> None:
        while q and now - q[0] >= self.window:
            q.popleft()

    def blocked(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits.get(key)
            if q is None:
                return False
            self._prune(q, now)
            if not q:
                del self._hits[key]  # ne nőjön a memória a régi IP-kkel
                return False
            return len(q) >= self.limit

    def hit(self, key: str) -> None:
        with self._lock:
            self._hits[key].append(time.monotonic())

    def retry_after(self, key: str) -> int:
        with self._lock:
            q = self._hits.get(key)
            if not q:
                return 0
            return max(1, int(self.window - (time.monotonic() - q[0])) + 1)


rate_limiter = SlidingWindow(HUB_RATE_LIMIT)
login_limiter = SlidingWindow(MAX_FAILED_LOGINS)


def _client_ip(request: Request) -> str:
    # Szándékosan NEM olvassuk az X-Forwarded-For fejlécet: azt bárki hamisíthatja.
    # Proxy mögött indítsd az uvicornt --proxy-headers --forwarded-allow-ips=<proxy IP>
    # kapcsolókkal, akkor a request.client már a valódi IP lesz.
    return request.client.host if request.client else "unknown"


def _check_password(header: str | None) -> bool:
    if not header or not header.lower().startswith("basic "):
        return False
    try:
        user, _, password = base64.b64decode(header[6:]).decode("utf-8").partition(":")
    except Exception:
        return False
    # időzítés-biztos összehasonlítás; mindkettőt kiértékeljük
    ok_user = secrets.compare_digest(user.encode(), HUB_USER.encode())
    ok_pass = secrets.compare_digest(password.encode(), HUB_PASSWORD.encode())
    return ok_user and ok_pass


def _unauthorized() -> Response:
    return Response(
        "Jelszó szükséges.",
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="AI Hub", charset="UTF-8"'},
        media_type="text/plain; charset=utf-8",
    )


def _too_many(message: str, retry: int) -> Response:
    return JSONResponse(
        {"detail": message}, status_code=429, headers={"Retry-After": str(retry)}
    )


async def guard(request: Request, call_next):
    ip = _client_ip(request)

    if HUB_PASSWORD:
        if login_limiter.blocked(ip):
            return _too_many(
                "Túl sok hibás jelszó. Próbáld újra később.", login_limiter.retry_after(ip)
            )
        if not _check_password(request.headers.get("authorization")):
            if request.headers.get("authorization"):  # csak a tényleges rossz próbát számoljuk
                login_limiter.hit(ip)
                log.warning("Hibás jelszó: %s", ip)
            return _unauthorized()

    if request.method == "POST" and request.url.path in PAID_PATHS:
        if rate_limiter.blocked(ip):
            retry = rate_limiter.retry_after(ip)
            return _too_many(
                f"Túl sok kérés (max. {HUB_RATE_LIMIT}/perc). Próbáld újra {retry} mp múlva.",
                retry,
            )
        rate_limiter.hit(ip)

    return await call_next(request)


def startup_warning() -> None:
    if not HUB_PASSWORD:
        log.warning(
            "HUB_PASSWORD nincs beállítva – az AI Hub jelszó nélkül fut. "
            "Csak helyben (--host 127.0.0.1) indítsd!"
        )
