"""
TAILOR24 Backend — FastAPI Application Entry Point
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.common.exceptions import AppError
from app.core.config import settings
from app.core.database import connect_to_mongo, close_mongo_connection, ping_db
from app.core.logging_config import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    logger.info("TAILOR24 Backend starting up (env=%s) …", settings.APP_ENV)
    connect_to_mongo()
    yield
    logger.info("TAILOR24 Backend shutting down …")
    close_mongo_connection()


app = FastAPI(
    title="TAILOR24 Backend API",
    description=(
        "Digital on-demand tailoring & garment delivery platform. "
        "Connects customers, hubs, and independent BYOD tailors under a 24-hour delivery promise."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global Exception Handlers ─────────────────────────────────────────────────


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error_code": exc.error_code,
            "message": exc.message,
            "detail": exc.detail,
        },
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error_code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred. Please try again later.",
            "detail": None,
        },
    )


# ── Health Endpoint ───────────────────────────────────────────────────────────


@app.get("/health", tags=["health"], summary="Health check")
def health_check():
    """
    Returns service health and MongoDB connectivity status.

    Response:
    - `status`: `"ok"` always (if the server is reachable)
    - `database`: `"connected"` | `"disconnected"`
    """
    db_status = "connected" if ping_db() else "disconnected"
    return {"status": "ok", "database": db_status}


# ── Register Routers ──────────────────────────────────────────────────────────
from app.modules.auth.router import router as auth_router
from app.modules.users.router import router as users_router
from app.modules.customers.router import router as customers_router
from app.modules.addresses.router import router as addresses_router
from app.modules.hubs.router import router as hubs_router
from app.modules.tailors.router import router as tailors_router
from app.modules.tailors.applications_router import router as applications_router
from app.modules.tailors.leave_router import router as leave_router
from app.modules.orders.router import router as orders_router
from app.modules.garments.router import router as garments_router
from app.modules.assignments.router import router as assignments_router
from app.modules.deliveries.router import router as deliveries_router
from app.modules.payouts.router import router as payouts_router
from app.modules.notifications.router import router as notifications_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.measurements.router import router as measurements_router

PREFIX = "/api/v1"

app.include_router(auth_router, prefix=f"{PREFIX}/auth", tags=["Authentication"])
app.include_router(users_router, prefix=f"{PREFIX}/users", tags=["Users"])
app.include_router(customers_router, prefix=f"{PREFIX}/customers", tags=["Customers"])
app.include_router(addresses_router, prefix=f"{PREFIX}/addresses", tags=["Addresses"])
app.include_router(hubs_router, prefix=f"{PREFIX}/hubs", tags=["Hubs"])
app.include_router(tailors_router, prefix=f"{PREFIX}/tailors", tags=["Tailors"])
app.include_router(applications_router, prefix=f"{PREFIX}/tailor-applications", tags=["Tailor Applications"])
app.include_router(leave_router, prefix=f"{PREFIX}/leave", tags=["Leave Requests"])
app.include_router(orders_router, prefix=f"{PREFIX}/orders", tags=["Orders"])
app.include_router(garments_router, prefix=f"{PREFIX}/garments", tags=["Garments"])
app.include_router(assignments_router, prefix=f"{PREFIX}/assignments", tags=["Assignments"])
app.include_router(deliveries_router, prefix=f"{PREFIX}/deliveries", tags=["Deliveries"])
app.include_router(payouts_router, prefix=f"{PREFIX}/payouts", tags=["Payouts"])
app.include_router(notifications_router, prefix=f"{PREFIX}/notifications", tags=["Notifications"])
app.include_router(dashboard_router, prefix=f"{PREFIX}/dashboard", tags=["Dashboard"])
app.include_router(measurements_router, prefix=f"{PREFIX}", tags=["Measurements"])
