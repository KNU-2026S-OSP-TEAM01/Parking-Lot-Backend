from fastapi import FastAPI

from app.routers import auth, lots, plates

app = FastAPI(title="OpenPark - Parking Lot Server")

app.include_router(auth.router,   prefix="/api/v1", tags=["auth"])
app.include_router(lots.router,   prefix="/api/v1", tags=["lots"])
app.include_router(plates.router, prefix="/api/v1", tags=["plates"])
