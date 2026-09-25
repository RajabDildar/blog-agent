"""FastAPI application entry point for Blog Agent v3."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.config import get_settings
from apps.api.routers import auth, runs, gallery

settings = get_settings()


def create_app() -> FastAPI:
    """Builds and configures the FastAPI application instance."""
    app = FastAPI(
        title="Blog Agent API",
        version="3.0.0",
        description="FastAPI Backend for Blog Agent Technical Article Generator",
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

    @app.get("/healthz", tags=["health"])
    def health_check():
        """Basic health check endpoint."""
        return {"status": "ok", "environment": settings.ENVIRONMENT}

    return app


app = create_app()
