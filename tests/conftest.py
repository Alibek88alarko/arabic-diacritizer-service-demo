import pytest
from fastapi.testclient import TestClient

from diacritizer.api import create_app
from diacritizer.providers import FailingProvider, StubProvider
from diacritizer.settings import Settings
from diacritizer.store import Store

KEY = "k-current"
PREV = "k-previous"


@pytest.fixture
def settings(tmp_path):
    return Settings(db_path=str(tmp_path / "api.db"), log_dir=str(tmp_path / "logs"), provider_timeout_s=0.5,
                    service_key=KEY, service_key_previous=PREV)


@pytest.fixture
def client(settings):
    app = create_app(settings, providers=[FailingProvider(), StubProvider()], store=Store(settings.db_path))
    c = TestClient(app)
    c.headers.update({"X-Service-Key": KEY})
    return c
