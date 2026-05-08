import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.jwt_auth import get_current_user, require_superadmin
from app.models.parking_lot import ParkingLot
from app.schemas.lot import LotCreate, LotOut, LotPatch

router = APIRouter()


def _mask_key(key: str) -> str:
    return key[:4] + "..." + key[-4:]


def _serialize(lot: ParkingLot, *, mask_key: bool = True) -> LotOut:
    return LotOut(
        id=lot.id,
        name=lot.name,
        address=lot.address,
        total_spaces=lot.total_spaces,
        available_spaces=lot.available_spaces,
        base_fee=lot.base_fee,
        base_duration_minutes=lot.base_duration_minutes,
        extra_fee_per_unit=lot.extra_fee_per_unit,
        extra_fee_unit_minutes=lot.extra_fee_unit_minutes,
        daily_max_fee=lot.daily_max_fee,
        api_key=_mask_key(lot.api_key) if mask_key else lot.api_key,
        is_active=lot.is_active,
        created_at=lot.created_at,
        updated_at=lot.updated_at,
    )


async def _get_lot_or_404(lot_id: uuid.UUID, db: AsyncSession) -> ParkingLot:
    result = await db.execute(select(ParkingLot).where(ParkingLot.id == lot_id))
    lot = result.scalar_one_or_none()
    if not lot:
        raise HTTPException(status_code=404, detail="lot_not_found")
    return lot


@router.post("/lots", response_model=LotOut)
async def create_lot(
    body: LotCreate,
    user: dict = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> LotOut:
    lot = ParkingLot(
        **body.model_dump(),
        id=uuid.uuid4(),
        available_spaces=body.total_spaces,
        api_key=secrets.token_hex(32),
    )
    db.add(lot)
    await db.flush()
    await db.refresh(lot)
    # 최초 등록 시에만 api_key 원문 반환
    return _serialize(lot, mask_key=False)


@router.get("/lots", response_model=list[LotOut])
async def list_lots(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[LotOut]:
    query = select(ParkingLot)
    if user["role"] == "admin":
        query = query.where(ParkingLot.id == user["lot_id"])
    result = await db.execute(query)
    return [_serialize(lot) for lot in result.scalars().all()]


@router.get("/lots/{lot_id}", response_model=LotOut)
async def get_lot(
    lot_id: uuid.UUID,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LotOut:
    lot = await _get_lot_or_404(lot_id, db)
    if user["role"] == "admin" and str(lot.id) != user["lot_id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    return _serialize(lot)


@router.patch("/lots/{lot_id}", response_model=LotOut)
async def update_lot(
    lot_id: uuid.UUID,
    body: LotPatch,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LotOut:
    lot = await _get_lot_or_404(lot_id, db)
    if user["role"] == "admin" and str(lot.id) != user["lot_id"]:
        raise HTTPException(status_code=403, detail="forbidden")

    patch = body.model_dump(exclude_none=True)

    if "total_spaces" in patch and patch["total_spaces"] < lot.available_spaces:
        raise HTTPException(
            status_code=400,
            detail="total_spaces cannot be less than current available_spaces",
        )

    for field, value in patch.items():
        setattr(lot, field, value)

    await db.flush()
    await db.refresh(lot)
    return _serialize(lot)


@router.delete("/lots/{lot_id}", status_code=204)
async def deactivate_lot(
    lot_id: uuid.UUID,
    user: dict = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> None:
    lot = await _get_lot_or_404(lot_id, db)
    lot.is_active = False
    await db.flush()
