"""The authentication path: the gateway's key, rotation with a previous key, and the 401 mapping."""
import pytest

from diacritizer.auth import ServiceKeyAuth
from tests.conftest import KEY, PREV

TEXT = "كتب"


def test_constant_time_compare_accepts_current_and_previous():
    a = ServiceKeyAuth("cur", "old")
    assert a.verify("cur") and a.verify("old")
    assert not a.verify("wrong") and not a.verify("") and not a.verify(None)


def test_previous_key_stops_working_once_cleared():
    a = ServiceKeyAuth("cur")
    assert not a.verify("old")


def test_empty_current_key_is_refused_at_startup():
    with pytest.raises(ValueError):
        ServiceKeyAuth("")


def test_protected_routes_need_the_key(client):
    for method, path, body in (("post", "/diacritize", {"text": TEXT}),
                               ("post", "/corrections", {"request_id": "x", "corrected_text": TEXT}),
                               ("get", "/corrections", None)):
        for bad in ("nope", ""):
            kwargs = {"headers": {"X-Service-Key": bad}}
            if body is not None:
                kwargs["json"] = body
            r = getattr(client, method)(path, **kwargs)
            assert r.status_code == 401, (path, bad, r.status_code)


def test_previous_key_still_accepted_during_rotation(client):
    assert client.post("/diacritize", json={"text": TEXT}, headers={"X-Service-Key": PREV}).status_code == 200
    assert client.post("/diacritize", json={"text": TEXT}, headers={"X-Service-Key": KEY}).status_code == 200
