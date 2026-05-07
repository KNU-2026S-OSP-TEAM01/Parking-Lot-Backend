from fastapi import FastAPI
from app.config import settings

app = FastAPI(title="OpenPark - Parking Lot Server")

# 라우터는 각 단계 구현 후 순차적으로 추가


if settings.mode == "public":
    pass  # TODO: public 라우터 마운트 (Hub Server 연동 시)
