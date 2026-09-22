from fastapi import FastAPI
from sqlalchemy import text

from app.core.database import engine


# ============================================================
# API ROUTERS
# ============================================================

from app.api.v1.auth import router as auth_router
from app.api.v1.users import router as users_router
from app.api.v1.categories import router as categories_router
from app.api.v1.products import router as products_router
from app.api.v1.bills import router as bills_router
from app.api.v1.kadan import router as kadan_router
from app.api.v1.customers import router as customers_router
from app.api.v1.reports import router as reports_router
from app.api.v1.tenants import router as tenants_router
from app.api.v1.audit_logs import router as audit_logs_router


from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from fastapi.responses import JSONResponse
import uuid
import logging
from sqlalchemy.exc import SQLAlchemyError

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.core.rate_limit import limiter
from app.core.config import settings
from app.core.logging import setup_logging, request_id_var

# Setup structured logging
setup_logging(settings.LOG_LEVEL)

# ============================================================
# APPLICATION
# ============================================================

app = FastAPI(
    title="CRYVEX SHOPFLOW API",
    description="Backend API for CRYVEX SHOPFLOW SaaS",
    version="1.0.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ============================================================
# MIDDLEWARE: REQUEST ID
# ============================================================

class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request_id_var.set(request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

app.add_middleware(RequestIdMiddleware)

# ============================================================
# GLOBAL EXCEPTION HANDLERS
# ============================================================

@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    logging.error(f"Database error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal database error occurred."}
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred."}
    )

# ============================================================
# MIDDLEWARE: CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# MIDDLEWARE: SECURITY HEADERS
# ============================================================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        # Allow Swagger UI to load its assets from jsdelivr, and allow inline styles/scripts for swagger
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com;"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

app.add_middleware(SecurityHeadersMiddleware)


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get(
    "/health",
    tags=["Health"],
)
async def health_check():
    """
    Basic API health check.
    """

    return {
        "status": "ok",
        "service": "shopflow-api",
    }


# ============================================================
# DATABASE HEALTH CHECK
# ============================================================

@app.get(
    "/health/database",
    tags=["Health"],
)
async def database_health_check():
    """
    Check whether the API can connect to PostgreSQL.
    """

    async with engine.connect() as connection:

        result = await connection.execute(
            text("SELECT 1")
        )

        value = result.scalar()

    return {
        "status": "ok",
        "database": "connected",
        "test": value,
    }


# ============================================================
# API ROUTERS
# ============================================================

# Authentication
app.include_router(
    auth_router,
    prefix="/api/v1",
)


# Users / Employees
app.include_router(
    users_router,
    prefix="/api/v1",
)


# Categories
app.include_router(
    categories_router,
    prefix="/api/v1",
)


# Products
app.include_router(
    products_router,
    prefix="/api/v1",
)


# Billing
app.include_router(
    bills_router,
    prefix="/api/v1",
)

#kadan
app.include_router(
    kadan_router,
    prefix="/api/v1",
)

# customers
app.include_router(
    customers_router,
    prefix="/api/v1",
)

# Reports
app.include_router(
    reports_router,
    prefix="/api/v1",
)

# Tenants
app.include_router(
    tenants_router,
    prefix="/api/v1",
)

# Audit Logs
app.include_router(
    audit_logs_router,
    prefix="/api/v1",
)