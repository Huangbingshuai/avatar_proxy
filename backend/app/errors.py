from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int,
        code: str,
        *,
        details: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details or {}
        self.headers = headers or {}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, error: RequestValidationError):
        if not request.url.path.startswith("/v1/"):
            return await request_validation_exception_handler(request, error)
        first = error.errors()[0] if error.errors() else {}
        location = first.get("loc") if isinstance(first, dict) else None
        param = ".".join(str(item) for item in location[1:]) if isinstance(location, tuple) else None
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "message": str(first.get("msg") or "请求参数无效"),
                    "type": "invalid_request_error",
                    "param": param,
                    "code": "invalid_request_parameter",
                },
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, error: ApiError) -> JSONResponse:
        if request.url.path.startswith("/v1/"):
            request_id = getattr(request.state, "request_id", None)
            content = {
                "error": {
                    "message": error.message,
                    "type": "invalid_request_error" if error.status_code < 500 else "upstream_error",
                    "param": error.details.get("param"),
                    "code": error.code,
                },
                "request_id": request_id,
            }
            return JSONResponse(
                status_code=error.status_code,
                content=content,
                headers=error.headers,
            )
        return JSONResponse(
            status_code=error.status_code,
            content={"error": {"code": error.code, "message": error.message, **error.details}},
            headers=error.headers,
        )
