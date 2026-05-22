from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.parking_lot import ParkingLot

bearer = HTTPBearer()
ALGORITHM = "HS256"


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(bearer),
) -> dict:
    try:
        return jwt.decode(credentials.credentials, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="invalid_token")


async def get_owned_lot(
    lot_id: str,
    current_user: dict,
    db: AsyncSession,
) -> ParkingLot:
    """lot_id의 주차장이 존재하는지, 현재 사용자가 소유자인지 검증."""
    from uuid import UUID
    result = await db.execute(select(ParkingLot).where(ParkingLot.id == UUID(lot_id)))
    lot = result.scalar_one_or_none()
    if not lot:
        raise HTTPException(status_code=404, detail="lot_not_found")
    if str(lot.owner_user_id) != current_user["sub"]:
        raise HTTPException(status_code=403, detail="forbidden")
    return lot
