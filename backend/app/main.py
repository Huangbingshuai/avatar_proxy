import asyncio
import secrets
from contextlib import asynccontextmanager, suppress
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .admin_auth import AdminAuthService
from .backup import BackupManager
from .billing import BillingManager
from .config import Settings, get_settings
from .database import Database
from .errors import install_error_handlers
from .maintenance import MaintenanceGate
from .provider_relay import ProviderRelay
from .quota import QuotaManager
from .routers import admin, assets, auth, billing, internal, openai_compat, providers, video
from .seedance import SeedanceClient
from .storage import TosStorage
from .system_monitor import DiskMonitor
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
        app.state.maintenance_gate = MaintenanceGate()
        app.state.admin_auth = AdminAuthService(database, resolved)
        app.state.backup = BackupManager(
            database,
            resolved,
            app.state.maintenance_gate,
            app.state.admin_auth.validate_encrypted_totp_secret,
        )
        app.state.quota = QuotaManager(database)
        app.state.billing = BillingManager(database)
        app.state.provider_relay = ProviderRelay(resolved, database)
        app.state.volcengine = volcengine
        app.state.seedance = SeedanceClient(resolved, database)
        app.state.storage = TosStorage(
            resolved, database, app.state.quota, app.state.maintenance_gate
        )
        app.state.system_monitor = DiskMonitor(
            database, resolved, maintenance_gate=app.state.maintenance_gate
        )
        maintenance = asyncio.create_task(app.state.storage.maintenance_loop())
        backup_maintenance = asyncio.create_task(app.state.backup.maintenance_loop())
        system_monitor_maintenance = asyncio.create_task(app.state.system_monitor.maintenance_loop())
        billing_maintenance = asyncio.create_task(app.state.billing.maintenance_loop())
        try:
            yield
        finally:
            maintenance.cancel()
            backup_maintenance.cancel()
            system_monitor_maintenance.cancel()
            billing_maintenance.cancel()
            with suppress(asyncio.CancelledError):
                await maintenance
            with suppress(asyncio.CancelledError):
                await backup_maintenance
            with suppress(asyncio.CancelledError):
                await system_monitor_maintenance
            with suppress(asyncio.CancelledError):
                await billing_maintenance
            await app.state.system_monitor.aclose()
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
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "X-CSRF-Token",
            "X-Ark-Api-Key",
        ],
        expose_headers=["X-Request-Id", "X-Upstream-Service", "Retry-After"],
    )

    @app.middleware("http")
    async def maintenance_control(request, call_next):
        request.state.request_id = f"req_{secrets.token_hex(16)}"
        gate = getattr(request.app.state, "maintenance_gate", None)
        if gate is None or request.url.path == "/health":
            response = await call_next(request)
            response.headers.setdefault("X-Request-Id", request.state.request_id)
            return response
        if not await gate.begin_request():
            response = JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "code": "system_maintenance",
                        "message": "系统正在恢复数据库，请稍后重试",
                    }
                },
                headers={"Retry-After": "3"},
            )
            response.headers["X-Request-Id"] = request.state.request_id
            return response
        try:
            response = await call_next(request)
            response.headers.setdefault("X-Request-Id", request.state.request_id)
            return response
        finally:
            await gate.finish_request()
    install_error_handlers(app)
    app.include_router(admin.router)
    app.include_router(auth.router)
    app.include_router(internal.router)
    app.include_router(providers.router)
    app.include_router(billing.router)
    app.include_router(assets.router)
    app.include_router(video.router)
    app.include_router(openai_compat.router)

    @app.get("/health", tags=["系统"])
    def health() -> dict[str, str | bool]:
        return {
            "status": "ok",
            "service": "avatar-proxy-api",
            "maintenance": bool(getattr(app.state, "maintenance_gate", None) and app.state.maintenance_gate.active),
        }

    return app


app = create_app()
