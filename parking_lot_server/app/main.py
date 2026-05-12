from fastapi import FastAPI

from app.config import settings
from app.routers import plates
from app.routers.admin import auth, logs, lots, users, vehicles

app = FastAPI(title="OpenPark - Parking Lot Server")

app.include_router(plates.router,       prefix="/api/v1", tags=["plates"])
app.include_router(auth.public_router,  prefix="/auth",   tags=["auth"])
app.include_router(auth.router,         prefix="/admin",  tags=["auth"])
app.include_router(lots.router,     prefix="/admin", tags=["lots"])
app.include_router(users.router,    prefix="/admin", tags=["users"])
app.include_router(vehicles.router, prefix="/admin", tags=["vehicles"])
app.include_router(logs.router,     prefix="/admin", tags=["logs"])

if settings.mode == "public":
    from app.routers.public import status
    app.include_router(status.router, prefix="/public", tags=["public"])
