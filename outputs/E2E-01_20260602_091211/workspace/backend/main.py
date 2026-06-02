from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import settings
from backend.database import Base, engine
from backend.routers import user_router, product_router, material_router
from backend.core.exceptions import NotFoundException, ConflictException, UnauthorizedException, ForbiddenException
from backend.core.exception_handlers import (
    not_found_exception_handler,
    conflict_exception_handler,
    unauthorized_exception_handler,
    forbidden_exception_handler,
    http_exception_handler
)

# Import models to ensure they are registered with Base.metadata
from backend.models import user, product, material

def create_tables():
    Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Manufacturing Simulator API",
    version="0.1.0",
    description="API for managing users, products, and materials in a manufacturing simulation.",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Allow frontend origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register custom exception handlers
app.add_exception_handler(NotFoundException, not_found_exception_handler)
app.add_exception_handler(ConflictException, conflict_exception_handler)
app.add_exception_handler(UnauthorizedException, unauthorized_exception_handler)
app.add_exception_handler(ForbiddenException, forbidden_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler) # Catch all FastAPI HTTPExceptions

# Include routers
app.include_router(user_router.router, prefix=settings.API_V1_STR)
app.include_router(product_router.router, prefix=settings.API_V1_STR)
app.include_router(material_router.router, prefix=settings.API_V1_STR)

@app.on_event("startup")
async def startup_event():
    create_tables()
    print("Database tables created/checked.")

@app.get(f"{settings.API_V1_STR}/health", tags=["Health Check"])
async def health_check():
    return {"status": "ok"}