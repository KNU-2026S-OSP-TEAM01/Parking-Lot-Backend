from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth, lots, plates

app = FastAPI(title="OpenPark - Parking Lot Server")

if settings.frontend_url:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth.router,   prefix="/api/v1", tags=["auth"])
app.include_router(lots.router,   prefix="/api/v1", tags=["lots"])
app.include_router(plates.router, prefix="/api/v1", tags=["plates"])
