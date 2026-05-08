from fastapi import FastAPI

from app.config import settings
from app.routers.admin import auth, logs, lots, users, vehicles

app = FastAPI(title="OpenPark - Parking Lot Server")

app.include_router(auth.router,     prefix="/admin", tags=["auth"])
app.include_router(lots.router,     prefix="/admin", tags=["lots"])
app.include_router(users.router,    prefix="/admin", tags=["users"])
app.include_router(vehicles.router, prefix="/admin", tags=["vehicles"])
app.include_router(logs.router,     prefix="/admin", tags=["logs"])

if settings.mode == "public":
    pass  # TODO: public 라우터 마운트 (Hub Server 연동 시)
