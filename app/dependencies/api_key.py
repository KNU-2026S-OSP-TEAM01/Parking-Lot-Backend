from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.parking_lot import ParkingLot

bearer = HTTPBearer()



async def get_parking_lot(
    credentials: HTTPAuthorizationCredentials = Security(bearer),
    db: AsyncSession = Depends(get_db),
) -> ParkingLot:
    result = await db.execute(
        select(ParkingLot).where(
            ParkingLot.api_key == credentials.credentials,
        )
    )
    lot = result.scalar_one_or_none()
    if not lot:
        raise HTTPException(status_code=401, detail="invalid_api_key")
    return lot
