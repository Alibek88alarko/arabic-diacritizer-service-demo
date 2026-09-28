"""Post-deploy check. Run after install and again after a reboot:  python deploy/smoke_test.py http://127.0.0.1:8080

Exit code 0 = service answers and the validator accepted the output. Anything else = investigate.
"""
import json
import sys
import urllib.request

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))
from diacritizer.validate import check  # noqa: E402

base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"
sample = "كتب الولد الدرس"  # كتب الولد الدرس


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status, json.loads(r.read().decode())


try:
    st, h = call("GET", "/health")
    assert st == 200 and h["status"] == "ok", h
    st, d = call("POST", "/diacritize", {"text": sample})
    assert st == 200, d
    v = check(sample, d["text"])
    assert v.ok, v
    print(f"PASS health ok, providers={h['providers']}, diacritize via {d['provider']} in {d['elapsed_ms']} ms, validator ok")
    sys.exit(0)
except Exception as exc:  # noqa: BLE001
    print(f"FAIL {exc!r}")
    sys.exit(1)
