from database import engine, Base, SessionLocal
from models.user import User, UserRole
from services.auth_service import AuthService
from sqlalchemy import text
import os

def run_migrations(db):
    """Run database migrations for new columns"""
    try:
        # Add is_active column to customers table if it doesn't exist
        db.execute(text("""
            DO $$ 
            BEGIN 
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name='customers' AND column_name='is_active'
                ) THEN 
                    ALTER TABLE customers ADD COLUMN is_active BOOLEAN DEFAULT TRUE NOT NULL;
                END IF;
            END $$;
        """))
        db.commit()
        print("Migrations completed successfully!")
    except Exception as e:
        print(f"Migration warning: {e}")
        db.rollback()

def init_database():
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully!")
    
    db = SessionLocal()
    try:
        # Run migrations first
        run_migrations(db)
        
        existing_admin = db.query(User).filter(User.role == UserRole.ADMIN).first()
        if not existing_admin:
            admin = AuthService.create_user(
                db=db,
                name="Admin",
                mobile="9999999999",
                password="admin123",
                role=UserRole.ADMIN
            )
            if admin:
                print(f"Admin user created: {admin.mobile}")
            else:
                print("Admin user already exists")
        else:
            print("Admin user already exists")
    finally:
        db.close()

if __name__ == "__main__":
    init_database()
