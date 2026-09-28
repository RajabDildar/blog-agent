from fastapi import FastAPI, Request, HTTPException, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from apps.api.config import get_settings
from apps.api.routers import auth, runs, gallery, articles

settings = get_settings()


def create_app() -> FastAPI:
    """Builds and configures the FastAPI application instance."""
    app = FastAPI(
        title="Blog Agent API",
        version="3.0.0",
        description="FastAPI Backend for Blog Agent Technical Article Generator",
    )

    @app.exception_handler(HTTPException)
    async def custom_http_exception_handler(request: Request, exc: HTTPException):
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(
                status_code=exc.status_code,
                content=exc.detail,
                headers=exc.headers,
            )

        code_map = {
            400: "bad_request",
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            409: "conflict",
            422: "validation_error",
            429: "too_many_requests",
            500: "internal_server_error",
            503: "service_unavailable",
        }
        code = code_map.get(exc.status_code, "error")
        message = str(exc.detail) if exc.detail else "An error occurred"
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": code,
                    "message": message,
                    "run_id": None,
                }
            },
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed",
                    "run_id": None,
                }
            },
        )

    allowed_origins = (
        settings.ALLOWED_ORIGINS
        if isinstance(settings.ALLOWED_ORIGINS, list)
        else [settings.ALLOWED_ORIGINS]
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount application routers
    app.include_router(auth.router)
    app.include_router(runs.router)
    app.include_router(gallery.router)
    app.include_router(articles.router)

    # Mount Inngest background execution endpoint
    import inngest.fast_api
    from apps.api.inngest import inngest_client, inngest_functions

    inngest.fast_api.serve(
        app,
        inngest_client,
        inngest_functions,
        serve_path="/api/inngest",
    )

    @app.get("/healthz", tags=["health"])
    def health_check():
        """Basic health check endpoint."""
        return {"status": "ok", "environment": settings.ENVIRONMENT}

    return app


app = create_app()
