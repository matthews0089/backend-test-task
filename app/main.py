from fastapi import FastAPI

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.web.router import router as web_router


settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(title=settings.app_name)
app.include_router(api_router)
app.include_router(web_router)
