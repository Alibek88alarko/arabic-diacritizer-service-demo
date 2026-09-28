import pytest

from diacritizer.providers import (FailingProvider, MutatingProvider, Router, RouterError, SlowProvider,
                                   StubProvider)
from diacritizer.store import Store
from diacritizer.validate import check

TEXT = "كتب الولد"


def make(providers, store=None, **kw):
    kw.setdefault("timeout_s", 0.5)
    kw.setdefault("max_chars", 100)
    kw.setdefault("daily_char_budget", 1000)
    return Router(providers, usage_store=store, **kw)


def test_stub_output_passes_validator():
    r = make([StubProvider()]).run(TEXT)
    assert r.provider == "stub" and check(TEXT, r.text).ok


def test_fallback_after_exception():
    r = make([FailingProvider(), StubProvider()]).run(TEXT)
    assert r.provider == "stub"
    assert r.attempts[0].startswith("failing: RuntimeError")


def test_fallback_after_timeout():
    r = make([SlowProvider(2.0), StubProvider()], timeout_s=0.2).run(TEXT)
    assert r.provider == "stub" and "timeout" in r.attempts[0]


def test_fallback_when_validator_rejects_model_output():
    r = make([MutatingProvider(), StubProvider()]).run(TEXT)
    assert r.provider == "stub" and "rejected by validator" in r.attempts[0]


def test_all_providers_fail_is_an_error_not_a_guess():
    with pytest.raises(RouterError) as e:
        make([FailingProvider(), MutatingProvider()]).run(TEXT)
    assert e.value.status == 502 and len(e.value.attempts) == 2


def test_max_chars_cap():
    with pytest.raises(RouterError) as e:
        make([StubProvider()], max_chars=5).run(TEXT)
    assert e.value.status == 413


def test_daily_budget_is_persisted_and_enforced(tmp_path):
    store = Store(str(tmp_path / "u.db"))
    r = make([StubProvider()], store=store, daily_char_budget=len(TEXT) + 1)
    r.run(TEXT)
    assert store.chars_today() == len(TEXT)
    with pytest.raises(RouterError) as e:
        r.run(TEXT)
    assert e.value.status == 429
    # a fresh connection sees the same counter (survives a restart)
    assert Store(str(tmp_path / "u.db")).chars_today() == len(TEXT)
