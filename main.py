from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from database import engine, Base, SessionLocal, verify_db_connection
from routers import auth, customers, orders, transactions, tracking, receipts, location, notifications, reports
from routers import receipt_settings, stock, notification_settings, price_settings, dashboard, analytics, language_settings, logs, profile
from middleware.security import SecurityMiddleware
from models.user import User, UserRole
from services.auth_service import AuthService
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Yadav Diesel Delivery API",
    description="Backend API for Yadav Diesel Delivery Android App",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler to prevent information leakage"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Please try again later."}
    )

app.add_middleware(SecurityMiddleware)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
    max_age=600,
)

os.makedirs("uploads/receipts", exist_ok=True)
os.makedirs("uploads/profile_photos", exist_ok=True)
os.makedirs("uploads/vehicles", exist_ok=True)
os.makedirs("uploads/logos", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

app.include_router(auth.router)
app.include_router(customers.router)
app.include_router(orders.router)
app.include_router(transactions.router)
app.include_router(tracking.router)
app.include_router(receipts.router)
app.include_router(location.router)
app.include_router(notifications.router)
app.include_router(reports.router)
app.include_router(receipt_settings.router)
app.include_router(stock.router)
app.include_router(notification_settings.router)
app.include_router(price_settings.router)
app.include_router(dashboard.router)
app.include_router(analytics.router)
app.include_router(language_settings.router)
app.include_router(logs.router)
app.include_router(profile.router)

db_initialized = False

@app.on_event("startup")
async def startup_event():
    """Initialize database and create admin user on startup"""
    global db_initialized
    
    if engine is None:
        logger.error("DATABASE_URL not configured - database features disabled")
        return
    
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created/verified")
        
        if SessionLocal:
            db = SessionLocal()
            try:
                existing_admin = db.query(User).filter(User.role == UserRole.ADMIN).first()
                if not existing_admin:
                    admin = AuthService.create_user(
                        db=db,
                        name="Admin",
                        mobile="9999999999",
                        password="Admin@123",
                        role=UserRole.ADMIN
                    )
                    logger.info(f"Admin user created: {admin.mobile}")
                else:
                    logger.info("Admin user already exists")
                db_initialized = True
            except Exception as e:
                logger.error(f"Admin init error: {e}")
            finally:
                db.close()
    except Exception as e:
        logger.error(f"Startup error: {e}")

@app.get("/")
def root():
    return {
        "message": "Yadav Diesel Delivery API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }

@app.get("/health")
def health_check():
    """Health check endpoint - always returns healthy for Railway"""
    db_status = "connected" if verify_db_connection() else "not connected"
    return {
        "status": "healthy",
        "database": db_status
    }
