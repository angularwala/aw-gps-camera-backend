# Yadav Diesel Delivery - Backend API

FastAPI backend for the Yadav Diesel Delivery mobile application.

## Quick Deploy to Railway

### Step-by-Step Deployment

1. **Create GitHub Repository**
   - Create a new repository on GitHub
   - Push this folder to the repository:
   ```bash
   cd yadavdiseldelivery-backend
   git init
   git add .
   git commit -m "Initial commit - Yadav Diesel Delivery Backend"
   git remote add origin https://github.com/YOUR_USERNAME/yadavdiseldelivery-backend.git
   git push -u origin main
   ```

2. **Deploy on Railway**
   - Go to [https://railway.com](https://railway.com)
   - Sign in with GitHub
   - Click "New Project" → "Deploy from GitHub repo"
   - Select your `yadavdiseldelivery-backend` repository
   - Railway will auto-detect Python and start building

3. **Add PostgreSQL Database**
   - In your Railway project, click "New" → "Database" → "Add PostgreSQL"
   - Railway will automatically set `DATABASE_URL` environment variable

4. **Set Environment Variables**
   - Go to your service → "Variables" tab
   - Add these variables:
     - `SESSION_SECRET` = (generate a 32+ character random string)
     - `TWILIO_ACCOUNT_SID` = (optional, for SMS)
     - `TWILIO_AUTH_TOKEN` = (optional, for SMS)
     - `TWILIO_PHONE_NUMBER` = (optional, for SMS)

5. **Generate Public Domain**
   - Go to Settings → Networking
   - Click "Generate Domain"
   - Your API will be available at: `https://your-app.up.railway.app`

6. **Update Android App**
   - Update your Android app's `BASE_URL` to your Railway domain

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | Auto-set when you add PostgreSQL |
| `SESSION_SECRET` | Yes | JWT secret key (min 32 characters) |
| `TWILIO_ACCOUNT_SID` | No | For SMS notifications |
| `TWILIO_AUTH_TOKEN` | No | For SMS notifications |
| `TWILIO_PHONE_NUMBER` | No | For SMS notifications |

## Default Admin Credentials

On first run, an admin user is created:
- **Mobile**: 9999999999
- **Password**: Admin@123

**Important**: Change the admin password immediately after first login!

## API Documentation

Once deployed, visit:
- Swagger UI: `https://your-app.up.railway.app/docs`
- ReDoc: `https://your-app.up.railway.app/redoc`
- Health Check: `https://your-app.up.railway.app/health`

## Features

- JWT Authentication with refresh tokens
- Role-based access control (Admin, Driver, Customer)
- Real-time GPS tracking via WebSocket
- Push notifications (Firebase)
- SMS notifications (Twilio) in 6 languages
- Order management
- Payment tracking
- Receipt generation
- Stock management
- Admin reports

## Tech Stack

- **Framework**: FastAPI (Python 3.11)
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Auth**: JWT with Argon2id password hashing
- **Server**: Gunicorn + Uvicorn workers
