"""Run the API in the foreground (development, or under NSSM on Windows)."""
import uvicorn

from diacritizer.api import create_app
from diacritizer.settings import Settings

settings = Settings.from_env()
app = create_app(settings)

if __name__ == "__main__":
    uvicorn.run(app, host=settings.host, port=settings.port, log_config=None)
