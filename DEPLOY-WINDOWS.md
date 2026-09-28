# Deploying on Windows Server 2019 as a native service (no containers)

Written so that another engineer can repeat it without asking the author. Two wrappers are provided:
**pywin32** (the service is a Python class, `service_windows.py`) and **NSSM** (a tiny supervisor that runs
`main.py`). Either is fine. NSSM is simpler to operate; pywin32 has no third-party binary.

Status of this document: written and reviewed on Linux; the Windows-only steps (marked [W]) are to be
verified on the target host during deployment. The API, validator, store and tests are covered by `pytest`.

## 0. Prerequisites

- Windows Server 2019, an account in the local Administrators group for installation.
- Python 3.11 x64 from python.org, installed "for all users", with "Add to PATH" ticked. [W]
- A dedicated service account, e.g. `svc-diacritizer`, "Log on as a service" right, no admin rights. [W]
- A folder for the service, e.g. `C:\services\diacritizer`. The service account needs Modify on it
  (it writes `data\` and `logs\`).
- Outbound HTTPS to the LLM provider(s) from the server, if a real provider is configured.

## 1. Install

```powershell
cd C:\services\diacritizer
git clone <repo> .                # or copy the files
uv venv --python 3.11 .venv       # uv: https://docs.astral.sh/uv/  (pip alternative: py -3.11 -m venv .venv)
uv pip install -r requirements.txt --python .venv\Scripts\python.exe
.\.venv\Scripts\python .venv\Scripts\pywin32_postinstall.py -install    # [W] once, for the pywin32 wrapper
copy .env.example .env
notepad .env                      # SERVICE_KEY (same value in the ASP.NET API), PROVIDERS, keys, port, absolute paths
.\.venv\Scripts\python -m pytest -q     # must be green before anything is registered
```

## 2a. Register with pywin32

```powershell
.\.venv\Scripts\python service_windows.py install                          # [W]
sc.exe config DiacritizerAPI obj= ".\svc-diacritizer" password= "<pwd>"    # [W] run as the service account
powershell -ExecutionPolicy Bypass -File deploy\configure-recovery.ps1    # auto-start + restart on failure
.\.venv\Scripts\python service_windows.py start
```

## 2b. Register with NSSM (alternative)

```powershell
# put nssm.exe (64-bit) on PATH, then:
powershell -ExecutionPolicy Bypass -File deploy\install-nssm.ps1          # [W]
nssm set DiacritizerAPI ObjectName ".\svc-diacritizer" "<pwd>"           # run as the service account
nssm restart DiacritizerAPI
```

## 3. Verify

```powershell
sc.exe query DiacritizerAPI                       # STATE : 4 RUNNING
.\.venv\Scripts\python deploy\smoke_test.py http://127.0.0.1:8080   # prints PASS ..., exit code 0
```

Then the two checks the service must pass:

1. **Survives reboot.** `shutdown /r /t 0`, log back in, run the smoke test again without touching the service.
2. **Restarts on failure.** Kill the process (`taskkill /F /PID <pid>` from `sc.exe queryex DiacritizerAPI`);
   within ~5 s `sc.exe query` shows RUNNING again and the smoke test passes.

## 4. Logs

- Application: `logs\diacritizer.log` (rotating, 5 x 5 MB). Every request id, provider used, fallbacks, failures.
- Service wrapper: Windows Event Viewer, Application log, source `DiacritizerAPI` (pywin32) or
  `logs\service.err.log` (NSSM).

## 5. Updating

```powershell
sc.exe stop DiacritizerAPI
git pull            # or copy new files
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m pytest -q
sc.exe start DiacritizerAPI
.\.venv\Scripts\python deploy\smoke_test.py
```

## 6. Known failure modes

| Symptom | Cause | Fix |
|---|---|---|
| Service stops immediately, event log says "crashed: FileNotFoundError" | `.env` missing or relative paths resolved from `C:\Windows\System32` | Use absolute `DB_PATH` and `LOG_DIR`, or keep `.env` next to `main.py` (it is loaded from the project root). |
| `Error 1053: the service did not respond in time` (pywin32) | pywin32 DLLs not registered for the service account | Re-run `pywin32_postinstall.py -install` as admin; confirm `pywintypes311.dll` is in `.venv\Lib\site-packages\pywin32_system32`. |
| Port already in use | another app on 8080 | Change `API_PORT` in `.env`, restart the service, update the smoke test URL. |
| 502 on every request | all providers failing (no network, bad key) | Check `logs\diacritizer.log`: each attempt is listed with the reason; keep `stub` last in `PROVIDERS` only for testing, never in production. |
| 429 | daily character budget exhausted | Raise `DAILY_CHAR_BUDGET` or wait for the next UTC day; the counter is in the `usage` table. |

## 7. Reachable only from the ASP.NET API

Two layers. First, the network: the service binds to `127.0.0.1` by default, which is enough when the ASP.NET API
runs on the same host. If it runs elsewhere, set `API_HOST` to the private interface and allow only that caller:

```powershell
netsh advfirewall firewall add rule name="DiacritizerAPI from gateway" dir=in action=allow protocol=TCP localport=8080 remoteip=<gateway-ip>
netsh advfirewall firewall add rule name="DiacritizerAPI block others" dir=in action=block protocol=TCP localport=8080
```

Second, the application: every route except `/health/live` requires the `X-Service-Key` header. Rotation
without downtime: set the new value in `SERVICE_KEY`, move the old one to `SERVICE_KEY_PREVIOUS`, restart the
service, update the ASP.NET API, then clear `SERVICE_KEY_PREVIOUS` and restart again.
