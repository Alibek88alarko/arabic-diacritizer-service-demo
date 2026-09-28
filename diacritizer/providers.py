"""Providers and the router.

A provider turns text into diacritized text. The router tries providers in order, applies a timeout,
validates every answer, and moves to the next provider on any error, timeout or validation failure.
Cost controls: a hard cap on characters per request and a daily character budget persisted in the store.
"""
from __future__ import annotations

import concurrent.futures as cf
import time
from dataclasses import dataclass
from typing import Protocol

from .validate import check, is_diacritic


class Provider(Protocol):
    name: str

    def diacritize(self, text: str) -> str: ...


class StubProvider:
    """Deterministic stand-in for a commercial model: puts a fatha after every bare Arabic letter.

    Linguistically meaningless, but it exercises the whole pipeline without network or keys.
    """

    name = "stub"

    def diacritize(self, text: str) -> str:
        out = []
        for i, ch in enumerate(text):
            out.append(ch)
            nxt = text[i + 1] if i + 1 < len(text) else ""
            if "ء" <= ch <= "ي" and not (nxt and is_diacritic(nxt)):
                out.append("َ")
        return "".join(out)


class FailingProvider:
    """Always raises. Used to prove the fallback path."""

    name = "failing"

    def diacritize(self, text: str) -> str:
        raise RuntimeError("provider down")


class SlowProvider:
    """Sleeps longer than the timeout. Used to prove the timeout path."""

    name = "slow"

    def __init__(self, seconds: float = 5.0):
        self.seconds = seconds

    def diacritize(self, text: str) -> str:
        time.sleep(self.seconds)
        return text


class MutatingProvider:
    """Returns text with one base letter changed. The validator must reject it."""

    name = "mutating"

    def diacritize(self, text: str) -> str:
        if not text:
            return text
        return text[:-1] + ("ب" if text[-1] != "ب" else "ت")


class AnthropicProvider:
    """Real commercial model behind the same interface. Only used when an API key is configured."""

    name = "anthropic"

    def __init__(self, api_key: str, model: str, timeout_s: float = 20.0):
        import anthropic  # imported lazily so the demo runs without the SDK installed

        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout_s)
        self._model = model

    def diacritize(self, text: str) -> str:
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=max(64, len(text) * 3),
            system=(
                "You add full Arabic diacritics (tashkeel) to the user's text. Return the same text with "
                "diacritics added and nothing else: no explanations, no quotes, no changes to letters, "
                "punctuation, spacing or line breaks."
            ),
            messages=[{"role": "user", "content": text}],
        )
        return "".join(getattr(b, "text", "") for b in msg.content).strip("\n")


class OpenAICompatibleProvider:
    """Any provider that speaks the OpenAI chat-completions protocol (OpenAI, Azure, DeepSeek, local servers).

    Configured entirely from the environment: base URL, model, key, timeout, retry count. Retries on
    transport errors and 5xx responses; a 4xx is returned to the router at once (it will not get better).
    """

    name = "openai-compatible"

    SYSTEM = ("You add full Arabic diacritics (tashkeel) to the user's text. Return the same text with "
              "diacritics added and nothing else: no explanations, no quotes, no changes to letters, "
              "punctuation, spacing or line breaks.")

    def __init__(self, base_url: str, api_key: str, model: str, *, timeout_s: float = 20.0,
                 retries: int = 1, transport=None, name: str | None = None):
        import httpx

        self.base_url = base_url.rstrip("/")
        self.model = model
        self.retries = max(0, retries)
        if name:
            self.name = name
        self._client = httpx.Client(
            base_url=self.base_url, timeout=timeout_s, transport=transport,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )

    def diacritize(self, text: str) -> str:
        import httpx

        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [{"role": "system", "content": self.SYSTEM}, {"role": "user", "content": text}],
        }
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                r = self._client.post("/chat/completions", json=payload)
            except httpx.HTTPError as exc:
                last = exc
                continue
            if r.status_code >= 500:
                last = RuntimeError(f"HTTP {r.status_code} from provider")
                continue
            if r.status_code >= 400:
                raise RuntimeError(f"HTTP {r.status_code} from provider: {r.text[:200]}")
            data = r.json()
            try:
                return data["choices"][0]["message"]["content"].strip("\n")
            except (KeyError, IndexError, TypeError) as exc:
                raise RuntimeError(f"unexpected response shape: {exc!r}")
        raise RuntimeError(f"gave up after {self.retries + 1} attempt(s): {last!r}")


@dataclass
class RouteResult:
    text: str
    provider: str
    elapsed_ms: int
    attempts: list[str]


class RouterError(Exception):
    def __init__(self, message: str, status: int = 502, attempts: list[str] | None = None):
        super().__init__(message)
        self.status = status
        self.attempts = attempts or []


class Router:
    def __init__(self, providers: list[Provider], *, timeout_s: float, max_chars: int,
                 daily_char_budget: int, usage_store=None):
        if not providers:
            raise ValueError("at least one provider is required")
        self.providers = providers
        self.timeout_s = timeout_s
        self.max_chars = max_chars
        self.daily_char_budget = daily_char_budget
        self.usage = usage_store
        self._pool = cf.ThreadPoolExecutor(max_workers=4)

    def run(self, text: str) -> RouteResult:
        if len(text) > self.max_chars:
            raise RouterError(f"text longer than {self.max_chars} characters", status=413)
        if self.usage is not None and self.usage.chars_today() + len(text) > self.daily_char_budget:
            raise RouterError("daily character budget exhausted", status=429)

        started = time.perf_counter()
        attempts: list[str] = []
        for p in self.providers:
            fut = self._pool.submit(p.diacritize, text)
            try:
                out = fut.result(timeout=self.timeout_s)
            except cf.TimeoutError:
                attempts.append(f"{p.name}: timeout after {self.timeout_s}s")
                continue
            except Exception as exc:  # noqa: BLE001 - any provider failure means "try the next one"
                attempts.append(f"{p.name}: {type(exc).__name__}: {exc}")
                continue
            verdict = check(text, out)
            if not verdict.ok:
                attempts.append(f"{p.name}: rejected by validator ({verdict.reason})")
                continue
            if self.usage is not None:
                self.usage.add_chars(len(text))
            elapsed = int((time.perf_counter() - started) * 1000)
            attempts.append(f"{p.name}: ok")
            return RouteResult(out, p.name, elapsed, attempts)
        raise RouterError("all providers failed: " + "; ".join(attempts), status=502, attempts=attempts)
