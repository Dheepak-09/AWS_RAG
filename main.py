import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.logger import setup_logging, get_logger
from app.routes.books import router as books_router
from app.routes.sessions import router as sessions_router
from app.routes.auth import router as auth_router
from app.routes.admin import router as admin_router
from app.models import create_tables

# ---------------------------------------------------------------------------
# Logging first
# ---------------------------------------------------------------------------
setup_logging()
logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Ailaysa RAG API",
    description="Upload books and chat with them. Role based access via HTTP Basic Auth.",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    logger.error(f"Unhandled exception | {request.method} {request.url.path}\n{tb}")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"},
    )

# ---------------------------------------------------------------------------
# Request logging
# ---------------------------------------------------------------------------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"→ {request.method} {request.url.path}")
    response = await call_next(request)
    logger.info(f"← {request.method} {request.url.path} [{response.status_code}]")
    return response

# ---------------------------------------------------------------------------
# Startup / Shutdown
# ---------------------------------------------------------------------------
@app.on_event("startup")
def startup():
    logger.info("=" * 60)
    logger.info("Ailaysa RAG API starting up...")
    create_tables()
    logger.info("API live  → http://127.0.0.1:8000")
    logger.info("Docs      → http://127.0.0.1:8000/docs")
    logger.info("=" * 60)

@app.on_event("shutdown")
def shutdown():
    logger.info("Ailaysa RAG API shutting down...")

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(auth_router,     prefix="/auth",     tags=["Auth"])
app.include_router(books_router,    prefix="/books",    tags=["Books"])
app.include_router(sessions_router, prefix="/sessions", tags=["Sessions"])
app.include_router(admin_router,    prefix="/admin",    tags=["Admin"])

# ---------------------------------------------------------------------------
# Health check — public, no auth needed
# ---------------------------------------------------------------------------
@app.get("/")
def root():
    return {"message": "Ailaysa RAG API is running", "status": "ok"}