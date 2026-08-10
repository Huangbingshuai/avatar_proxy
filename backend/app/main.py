from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings, get_settings
from .database import Database
from .errors import install_error_handlers
from .routers import admin, assets
from .volcengine import VolcengineClient


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database = Database(resolved.database_path)
        database.initialize()
        app.state.settings = resolved
        app.state.database = database
        app.state.volcengine = VolcengineClient(resolved, database)
        yield

    app = FastAPI(
        title="Avatar Proxy API",
        version="1.0.0",
        description="火山方舟私域虚拟人像素材资产库的项目级 API Key 网关。",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Admin-Token"],
        expose_headers=["X-Upstream-Service"],
    )
    install_error_handlers(app)
    app.include_router(admin.router)
    app.include_router(assets.router)

    @app.get("/health", tags=["系统"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "avatar-proxy-backend"}

    return app


app = create_app()
