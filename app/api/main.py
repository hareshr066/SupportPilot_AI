import logging
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import settings
from app.core.middleware import RequestContextMiddleware
from app.core.errors import (
    APIException,
    api_exception_handler,
    validation_exception_handler,
    http_exception_handler,
    unhandled_exception_handler,
)
from app.api.routes.health import router as health_router
from app.api.routes.tickets import router as tickets_router
from app.api.routes.runs import router as runs_router
from app.api.routes.repositories import router as repositories_router
from app.api.routes.webhooks import router as webhooks_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.evaluations import router as evaluations_router
from app.api.routes.issues import router as issues_router

# Configure Logger
logging.basicConfig(
    level=getattr(logging, settings.api_log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("supportpilot.api")


def create_app() -> FastAPI:
    """
    FastAPI Application Factory for SupportPilot Backend.
    """
    app = FastAPI(
        title="SupportPilot Autonomous Triage & Resolution API",
        description=(
            "Production-grade backend API exposing state-driven LangGraph orchestration, "
            "triage, root-cause correlation, grounded resolution generation, claim verification, "
            "calibrated confidence scoring, deterministic routing, and GitHub webhooks/sync."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json"
    )

    # 1. CORS Middleware Configuration
    origins = [origin.strip() for origin in settings.cors_allowed_origins.split(",") if origin.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    # 2. Request ID & Telemetry Middleware
    app.add_middleware(RequestContextMiddleware)

    # 3. Exception Handlers
    app.add_exception_handler(APIException, api_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # 4. Include Routers
    app.include_router(health_router)
    app.include_router(tickets_router)
    app.include_router(runs_router)
    app.include_router(repositories_router)
    app.include_router(webhooks_router)
    app.include_router(dashboard_router)
    app.include_router(evaluations_router)
    app.include_router(issues_router)

    logger.info("FastAPI Application initialized successfully.")
    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "app.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_debug
    )
