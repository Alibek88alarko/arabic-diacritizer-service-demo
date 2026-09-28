"""Post-deploy check. Run after install and again after a reboot:

    python deploy/smoke_test.py http://127.0.0.1:8080

Reads SERVICE_KEY from the environment or from .env in the project root.
Exit code 0 = liveness and readiness answer, a diacritize call succeeds and the validator accepts the output.
"""
import json
import os
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from diacritizer.settings import Settings  # noqa: E402
from diacritizer.validate import check  # noqa: E402

base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"
settings = Settings.from_env()
sample = "كتب الولد الدرس"  # كتب الولد الدرس


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", "X-Service-Key": settings.service_key})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


try:
    st, live = call("GET", "/health/live")
    assert st == 200 and live["status"] == "ok", (st, live)
    st, ready = call("GET", "/health/ready")
    assert st == 200, (st, ready)
    st, d = call("POST", "/diacritize", {"text": sample})
    assert st == 200, (st, d)
    v = check(sample, d["text"])
    assert v.ok, v
    print(f"PASS live ok, ready ok, providers={ready['providers']}, diacritize via {d['provider']} "
          f"in {d['elapsed_ms']} ms, validator ok")
    sys.exit(0)
except Exception as exc:  # noqa: BLE001
    print(f"FAIL {exc!r}")
    sys.exit(1)
