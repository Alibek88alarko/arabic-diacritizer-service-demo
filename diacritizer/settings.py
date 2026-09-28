"""Configuration from environment variables (and a .env file next to the project, if present).

Windows services start with no user environment, so everything a service needs must come from .env.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@dataclass
class Settings:
    host: str = "127.0.0.1"
    port: int = 8080
    db_path: str = str(ROOT / "data" / "diacritizer.db")
    log_dir: str = str(ROOT / "logs")
    provider_timeout_s: float = 8.0
    max_chars: int = 2000
    daily_char_budget: int = 200_000
    providers: list[str] = field(default_factory=lambda: ["stub"])
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv(ROOT / ".env")
        e = os.environ.get
        s = cls(
            host=e("API_HOST", "127.0.0.1"),
            port=int(e("API_PORT", "8080")),
            db_path=e("DB_PATH", str(ROOT / "data" / "diacritizer.db")),
            log_dir=e("LOG_DIR", str(ROOT / "logs")),
            provider_timeout_s=float(e("PROVIDER_TIMEOUT_S", "8")),
            max_chars=int(e("MAX_CHARS", "2000")),
            daily_char_budget=int(e("DAILY_CHAR_BUDGET", "200000")),
            providers=[p.strip() for p in e("PROVIDERS", "stub").split(",") if p.strip()],
            anthropic_api_key=e("ANTHROPIC_API_KEY", ""),
            anthropic_model=e("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
        )
        Path(s.db_path).parent.mkdir(parents=True, exist_ok=True)
        Path(s.log_dir).mkdir(parents=True, exist_ok=True)
        return s
