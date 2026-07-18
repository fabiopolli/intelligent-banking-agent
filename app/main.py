from fastapi import FastAPI

from app.api.inbound import router as inbound_router
from app.api.outbound_mcp import router as outbound_router
from app.config import settings


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)
    app.include_router(inbound_router, prefix=settings.api_prefix)
    app.include_router(outbound_router, prefix=settings.api_prefix)
    return app


app = create_app()
