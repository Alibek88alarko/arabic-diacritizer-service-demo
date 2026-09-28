import pytest
from fastapi.testclient import TestClient

from diacritizer.api import create_app
from diacritizer.providers import FailingProvider, StubProvider
from diacritizer.settings import Settings
from diacritizer.store import Store
from diacritizer.validate import check

TEXT = "كتب الولد الدرس"


@pytest.fixture
def client(tmp_path):
    s = Settings(db_path=str(tmp_path / "api.db"), log_dir=str(tmp_path / "logs"), provider_timeout_s=0.5)
    app = create_app(s, providers=[FailingProvider(), StubProvider()], store=Store(s.db_path))
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["providers"] == ["failing", "stub"]


def test_diacritize_returns_validated_text_and_persists_request(client):
    r = client.post("/diacritize", json={"text": TEXT})
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "stub" and check(TEXT, body["text"]).ok
    stored = client.app.state.store.get_request(body["request_id"])
    assert stored["ok"] == 1 and stored["input_text"] == TEXT and stored["output_text"] == body["text"]
    assert "failing: RuntimeError" in stored["detail"]   # the fallback path is on record


def test_correction_is_captured_and_listed(client):
    rid = client.post("/diacritize", json={"text": TEXT}).json()["request_id"]
    fixed = TEXT.replace("ك", "كَ", 1)    # a human puts one fatha differently
    r = client.post("/corrections", json={"request_id": rid, "corrected_text": fixed, "note": "reviewer A"})
    assert r.status_code == 201
    items = client.get("/corrections").json()["items"]
    assert len(items) == 1
    assert items[0]["request_id"] == rid and items[0]["corrected_text"] == fixed and items[0]["note"] == "reviewer A"
    assert items[0]["input_text"] == TEXT and check(TEXT, items[0]["model_text"]).ok


def test_correction_that_changes_letters_is_refused(client):
    rid = client.post("/diacritize", json={"text": TEXT}).json()["request_id"]
    r = client.post("/corrections", json={"request_id": rid, "corrected_text": TEXT[:-1]})
    assert r.status_code == 422 and "base text" in r.json()["detail"]


def test_correction_for_unknown_request_is_404(client):
    assert client.post("/corrections", json={"request_id": "nope", "corrected_text": TEXT}).status_code == 404


def test_all_providers_down_gives_502_and_is_logged_as_failed_request(tmp_path):
    s = Settings(db_path=str(tmp_path / "x.db"), log_dir=str(tmp_path / "logs"), provider_timeout_s=0.5)
    store = Store(s.db_path)
    c = TestClient(create_app(s, providers=[FailingProvider()], store=store))
    r = c.post("/diacritize", json={"text": TEXT})
    assert r.status_code == 502
    rid = r.json()["detail"]["request_id"]
    assert store.get_request(rid)["ok"] == 0


def test_corrections_survive_restart(tmp_path):
    s = Settings(db_path=str(tmp_path / "p.db"), log_dir=str(tmp_path / "logs"))
    c1 = TestClient(create_app(s, providers=[StubProvider()], store=Store(s.db_path)))
    rid = c1.post("/diacritize", json={"text": TEXT}).json()["request_id"]
    c1.post("/corrections", json={"request_id": rid, "corrected_text": TEXT})
    c2 = TestClient(create_app(s, providers=[StubProvider()], store=Store(s.db_path)))   # "restart"
    assert len(c2.get("/corrections").json()["items"]) == 1
