"""Native Windows service wrapper (pywin32). Runs the API in-process under the Service Control Manager.

    python service_windows.py install      register the service (run from an elevated prompt)
    python service_windows.py start        start it now
    python service_windows.py stop
    python service_windows.py remove

Auto-start on boot and restart on failure are set by deploy/configure-recovery.ps1 (sc.exe), see DEPLOY-WINDOWS.md.
This file only runs on Windows: pywin32 is not importable elsewhere, which is why it is not covered by the Linux tests.
"""
import logging
import sys
import threading

import servicemanager
import win32event
import win32service
import win32serviceutil

import uvicorn

from diacritizer.api import create_app
from diacritizer.settings import Settings

log = logging.getLogger("diacritizer.service")


class DiacritizerService(win32serviceutil.ServiceFramework):
    _svc_name_ = "DiacritizerAPI"
    _svc_display_name_ = "Arabic Diacritizer API"
    _svc_description_ = "HTTP API that adds diacritics to Arabic text via routed LLM providers with strict validation."

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.server: uvicorn.Server | None = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        if self.server is not None:
            self.server.should_exit = True
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self):
        servicemanager.LogInfoMsg(f"{self._svc_name_}: starting")
        try:
            settings = Settings.from_env()
            config = uvicorn.Config(create_app(settings), host=settings.host, port=settings.port, log_config=None)
            self.server = uvicorn.Server(config)
            worker = threading.Thread(target=self.server.run, name="uvicorn", daemon=True)
            worker.start()
            self.ReportServiceStatus(win32service.SERVICE_RUNNING)
            win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)
            worker.join(timeout=15)
            servicemanager.LogInfoMsg(f"{self._svc_name_}: stopped")
        except Exception as exc:  # noqa: BLE001 - a crash here must reach the event log, not vanish
            servicemanager.LogErrorMsg(f"{self._svc_name_}: crashed: {exc!r}")
            log.exception("service crashed")
            # Non-zero exit code so the SCM recovery actions (restart on failure) apply.
            self.ReportServiceStatus(win32service.SERVICE_STOPPED, win32ExitCode=1)
            sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(DiacritizerService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(DiacritizerService)
