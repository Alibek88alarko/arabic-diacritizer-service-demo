# Arabic diacritizer API: a demo of the four deliverables

A small, complete HTTP service that adds diacritics to Arabic text through routed LLM providers, with a
validator that has the final word, correction capture persisted in SQLite, a native Windows service wrapper,
a test suite and a deployment document. Built in one afternoon as a stand-in for a real diacritizer whose
code I have not seen, so the provider is pluggable and the shape of the API is my guess, not a spec.

Stack: Python 3.11, FastAPI, SQLite, pywin32 or NSSM for the Windows service.

## Measured result

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest -q
```

Output on the last run (Linux, Python 3.11, no API key, no network):

```
.......................                                                  [100%]
23 passed, 1 warning in 0.72s
```

Then the service itself, started with `python main.py` and checked by the post-deploy script:

```
$ python deploy/smoke_test.py http://127.0.0.1:8765
PASS health ok, providers=['stub'], diacritize via stub in 2 ms, validator ok
```

and a real call:

```
$ curl -X POST http://127.0.0.1:8765/diacritize -H 'Content-Type: application/json' -d '{"text":"كتب الولد الدرس"}'
{"request_id":"29f2155...","text":"كَتَبَ اَلَوَلَدَ اَلَدَرَسَ","provider":"stub","elapsed_ms":1}
```

The stub provider puts a fatha after every letter. That is linguistically wrong on purpose: it proves the
pipeline, not the language. A real provider (`anthropic`) is behind the same interface and switches on with a key.

What the 23 tests check:

| Area | Tests | What is measured |
|---|---|---|
| Validator (`tests/test_validate.py`) | 9 | Output that only adds tashkeel or Quranic marks passes. A changed letter, an appended or removed character, a changed space or full stop is rejected with the position of the first difference. Non-Arabic text passes through unchanged. Empty output is rejected. |
| Router (`tests/test_router.py`) | 7 | Falls back to the next provider after an exception, after a timeout, and after the validator rejects a model's answer. When every provider fails the result is an error, never a guess. Per-request character cap (413). Daily character budget persisted in SQLite and enforced across a restart (429). |
| API (`tests/test_api.py`) | 7 | `/health`; `/diacritize` returns validated text and stores the request with the fallback trail; `/corrections` stores a human correction, lists it with the original input and the model's output, refuses a correction that changes base letters (422), refuses an unknown request id (404); corrections survive a restart; total provider failure is a 502 and is logged as a failed request. |

## Design decisions

- **The validator is the authority.** `diacritizer/validate.py` strips diacritics from input and output and
  requires the skeletons to be identical. Anything a model returns that fails this is discarded and the next
  provider is tried. A human correction has to pass the same check before it is stored.
- **Routing with fallback and cost controls.** `diacritizer/providers.py`: providers are tried in order with
  a timeout each; any exception, timeout or validation failure moves to the next one. A hard cap on characters
  per request and a daily character budget (persisted, so a restart does not reset it) bound the spend.
- **Correction capture is part of the API contract.** `POST /corrections {request_id, corrected_text, note}`
  links the human's version to the stored request, so `GET /corrections?since=...` yields
  (input, model output, corrected output) triples ready for fine-tuning data.
- **Everything is on disk.** Requests, corrections and usage live in one SQLite file (WAL mode). Nothing
  leaves the machine except the text sent to the configured provider.
- **Windows service without containers.** `service_windows.py` is a pywin32 `ServiceFramework` that runs
  uvicorn in a thread and reports to the Service Control Manager; `deploy/configure-recovery.ps1` sets
  auto-start and restart-on-failure through `sc.exe`. `deploy/install-nssm.ps1` is the alternative wrapper.
  `deploy/smoke_test.py` is the check to run after install and after a reboot.

## Honest scope note

The API, validator, store and router are tested here, on Linux. The Windows service wrapper and the
PowerShell scripts are written from the pywin32 and NSSM documentation and have not been executed in this
repository, because there is no Windows host in it. `DEPLOY-WINDOWS.md` marks those steps [W] and lists the
failure modes I would check first on the real server.

## Layout

```
main.py                       run in the foreground (development, or under NSSM)
service_windows.py            pywin32 native service wrapper
diacritizer/validate.py       only-diacritics-added check
diacritizer/providers.py      providers, router with timeout, fallback and cost caps
diacritizer/store.py          SQLite: requests, corrections, daily usage
diacritizer/api.py            FastAPI app: /health, /diacritize, /corrections
diacritizer/settings.py       .env loading (services start with no user environment)
deploy/                       configure-recovery.ps1, install-nssm.ps1, smoke_test.py
tests/                        23 tests
DEPLOY-WINDOWS.md             step-by-step for Windows Server 2019, with known failure modes
```
