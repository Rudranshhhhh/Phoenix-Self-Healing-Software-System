"""
Phoenix API — Main Application

FastAPI application for the Phoenix orchestrator.
Real incident management, not mocked fixtures.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import init_database, close_database
from .routers import health, incidents

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager: startup and shutdown."""
    # Startup
    logger.info("🔥 Phoenix API starting up")
    if not init_database():
        logger.error("Failed to initialize database — aborting")
        raise RuntimeError("Database initialization failed")
    logger.info("✓ Phoenix API ready")
    yield
    # Shutdown
    logger.info("🔥 Phoenix API shutting down")
    close_database()


app = FastAPI(
    title="Phoenix Orchestrator API",
    description="AI-powered self-healing software system",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, be more specific
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router)
app.include_router(incidents.router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Phoenix Orchestrator API",
        "version": "1.0.0",
        "status": "running",
    }
