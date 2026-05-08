from fastapi import FastAPI

from app.config import settings
from app.routers.admin import auth

app = FastAPI(title="OpenPark - Parking Lot Server")

app.include_router(auth.router, prefix="/admin", tags=["admin"])

if settings.mode == "public":
    pass  # TODO: public 라우터 마운트 (Hub Server 연동 시)
