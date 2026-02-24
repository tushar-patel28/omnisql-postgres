import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.core.database import init_db
from app.api.routes import router
from app.api.schemas import HealthResponse

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ]
)

log = structlog.get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB and pgvector on startup."""
    log.info("Starting up", env=settings.app_env, inference_mode=settings.inference_mode)
    await init_db()
    log.info("Database initialized, pgvector ready")
    yield
    log.info("Shutting down")


app = FastAPI(
    title="Text-to-SQL API",
    description="PostgreSQL-extended OmniSQL-7B with schema RAG and self-correction",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return HealthResponse(
        status="ok",
        database="postgresql+pgvector",
        inference_mode=settings.inference_mode,
    )
