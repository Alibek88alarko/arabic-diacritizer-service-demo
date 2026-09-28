"""HTTP API. Three routes the client's pipeline needs: health, diacritize, corrections."""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from . import __version__
from .providers import AnthropicProvider, Router, RouterError, StubProvider
from .settings import Settings
from .store import Store
from .validate import check

log = logging.getLogger("diacritizer")


class DiacritizeIn(BaseModel):
    text: str = Field(..., min_length=1)


class DiacritizeOut(BaseModel):
    request_id: str
    text: str
    provider: str
    elapsed_ms: int


class CorrectionIn(BaseModel):
    request_id: str
    corrected_text: str = Field(..., min_length=1)
    note: str | None = None


def build_providers(s: Settings):
    out = []
    for name in s.providers:
        if name == "stub":
            out.append(StubProvider())
        elif name == "anthropic":
            if not s.anthropic_api_key:
                log.warning("provider 'anthropic' listed but ANTHROPIC_API_KEY is empty; skipping")
                continue
            out.append(AnthropicProvider(s.anthropic_api_key, s.anthropic_model, timeout_s=s.provider_timeout_s))
        else:
            raise ValueError(f"unknown provider '{name}'")
    if not out:
        raise ValueError("no usable providers configured")
    return out


def setup_logging(log_dir: str) -> None:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        Path(log_dir) / "diacritizer.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
        root.addHandler(handler)


def create_app(settings: Settings | None = None, *, providers=None, store: Store | None = None) -> FastAPI:
    s = settings or Settings.from_env()
    setup_logging(s.log_dir)
    store = store or Store(s.db_path)
    router = Router(
        providers or build_providers(s),
        timeout_s=s.provider_timeout_s,
        max_chars=s.max_chars,
        daily_char_budget=s.daily_char_budget,
        usage_store=store,
    )
    app = FastAPI(title="Arabic diacritizer API (demo)", version=__version__)
    app.state.store = store
    app.state.router = router

    @app.get("/health")
    def health():
        return {"status": "ok", "version": __version__, "providers": [p.name for p in router.providers]}

    @app.post("/diacritize", response_model=DiacritizeOut)
    def diacritize(body: DiacritizeIn):
        try:
            res = router.run(body.text)
        except RouterError as exc:
            rid = store.save_request(body.text, None, None, ok=False, detail=str(exc))
            log.warning("request %s failed: %s", rid, exc)
            raise HTTPException(status_code=exc.status, detail={"request_id": rid, "error": str(exc)})
        rid = store.save_request(body.text, res.text, res.provider, ok=True, detail="; ".join(res.attempts))
        log.info("request %s ok via %s in %d ms", rid, res.provider, res.elapsed_ms)
        return DiacritizeOut(request_id=rid, text=res.text, provider=res.provider, elapsed_ms=res.elapsed_ms)

    @app.post("/corrections", status_code=201)
    def add_correction(body: CorrectionIn):
        req = store.get_request(body.request_id)
        if req is None:
            raise HTTPException(status_code=404, detail="unknown request_id")
        verdict = check(req["input_text"], body.corrected_text)
        if not verdict.ok:
            raise HTTPException(status_code=422, detail=f"correction changes the base text: {verdict.reason}")
        cid = store.save_correction(body.request_id, body.corrected_text, body.note)
        log.info("correction %s saved for request %s", cid, body.request_id)
        return {"correction_id": cid}

    @app.get("/corrections")
    def list_corrections(since: str | None = Query(default=None, description="ISO-8601 UTC timestamp"),
                         limit: int = Query(default=100, ge=1, le=1000)):
        return {"items": store.list_corrections(since=since, limit=limit)}

    return app
