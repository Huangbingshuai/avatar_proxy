import asyncio
from contextlib import asynccontextmanager, suppress
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings, get_settings
from .database import Database
from .errors import install_error_handlers
from .quota import QuotaManager
from .routers import assets, auth, internal, video
from .seedance import SeedanceClient
from .storage import TosStorage
from .volcengine import VolcengineClient


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database = Database(resolved.database_path)
        database.initialize()
        volcengine = VolcengineClient(resolved, database)
        app.state.settings = resolved
        app.state.database = database
        app.state.quota = QuotaManager(database)
        app.state.volcengine = volcengine
        app.state.seedance = SeedanceClient(resolved, database)
        app.state.storage = TosStorage(resolved, database, app.state.quota)
        maintenance = asyncio.create_task(app.state.storage.maintenance_loop())
        try:
            yield
        finally:
            maintenance.cancel()
            with suppress(asyncio.CancelledError):
                await maintenance
            await volcengine.aclose()

    app = FastAPI(
        title="Avatar Proxy API",
        version="1.0.0",
        description="独立部署的虚拟人像素材库与 Seedance 视频生成代理服务。",
        lifespan=lifespan,
        docs_url="/docs" if resolved.enable_api_docs else None,
        redoc_url="/redoc" if resolved.enable_api_docs else None,
        openapi_url="/openapi.json" if resolved.enable_api_docs else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.allowed_origins,
        allow_origin_regex=resolved.cors_origin_regex or None,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Admin-Token", "X-Ark-Api-Key"],
        expose_headers=["X-Upstream-Service", "Retry-After"],
    )
    install_error_handlers(app)
    app.include_router(auth.router)
    app.include_router(internal.router)
    app.include_router(assets.router)
    app.include_router(video.router)

    @app.get("/health", tags=["系统"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "avatar-proxy-api"}

    return app


app = create_app()
