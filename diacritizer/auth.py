"""Service-to-service authentication: a shared key in a header, compared in constant time.

Two keys are accepted at once, current and optional previous, so the ASP.NET API can rotate without downtime:
set the new key as current, move the old one to previous, deploy both sides, then clear previous.
"""
from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, Request

HEADER = "X-Service-Key"


class ServiceKeyAuth:
    def __init__(self, current: str, previous: str = ""):
        if not current:
            raise ValueError("SERVICE_KEY must be set")
        self.current = current
        self.previous = previous or ""

    def verify(self, presented: str | None) -> bool:
        if not presented:
            return False
        ok = hmac.compare_digest(presented.encode(), self.current.encode())
        if self.previous:
            # evaluate both comparisons regardless of the first result, so timing does not reveal which matched
            ok_prev = hmac.compare_digest(presented.encode(), self.previous.encode())
            ok = ok or ok_prev
        return ok


def require_service_key(request: Request, x_service_key: str | None = Header(default=None, alias=HEADER)) -> None:
    auth: ServiceKeyAuth = request.app.state.auth
    if not auth.verify(x_service_key):
        raise HTTPException(status_code=401, detail="missing or invalid service key")
