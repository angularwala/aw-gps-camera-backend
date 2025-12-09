from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
import os
import logging

logger = logging.getLogger(__name__)

def get_database_url():
    """Get and fix database URL for Railway compatibility"""
    database_url = os.getenv("DATABASE_URL", "")
    
    if not database_url:
        logger.error("DATABASE_URL environment variable is not set!")
        return None
    
    # Railway uses postgres:// but SQLAlchemy needs postgresql://
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
        logger.info("Converted postgres:// to postgresql://")
    
    return database_url

database_url = get_database_url()

# Create engine only if database URL is available
engine = None
SessionLocal = None
Base = declarative_base()

if database_url:
    ssl_mode = os.getenv("DATABASE_SSL_MODE", "prefer")
    connect_args = {}
    if "postgresql" in database_url.lower():
        connect_args = {
            "connect_timeout": 10,
            "options": "-c statement_timeout=30000",
        }
        if ssl_mode == "require":
            connect_args["sslmode"] = "require"

    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=5,
        max_overflow=10,
        poolclass=QueuePool,
        connect_args=connect_args,
        echo=False,
    )
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    logger.info("Database engine created successfully")
else:
    logger.warning("Running without database - some features will not work")

def get_db():
    """Dependency that provides a database session with automatic cleanup"""
    if SessionLocal is None:
        raise Exception("Database not configured. Set DATABASE_URL environment variable.")
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Database error: {e}")
        db.rollback()
        raise
    finally:
        db.close()

def verify_db_connection():
    """Verify database connection is working"""
    if engine is None:
        return False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection verified")
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False
