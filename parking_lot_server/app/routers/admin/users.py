import uuid

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.jwt_auth import get_current_user, require_superadmin
from app.models.user import User
from app.schemas.user import UserCreate, UserOut, UserPatch

router = APIRouter()


async def _get_user_or_404(user_id: uuid.UUID, db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="user_not_found")
    return user


@router.post("/users", response_model=UserOut)
async def create_user(
    body: UserCreate,
    user: dict = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    result = await db.execute(select(User).where(User.username == body.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="username_already_exists")

    new_user = User(
        id=uuid.uuid4(),
        username=body.username,
        email=body.email,
        password_hash=bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode(),
        role="admin",
        parking_lot_id=body.parking_lot_id,
    )
    db.add(new_user)
    await db.flush()
    await db.refresh(new_user)
    return UserOut.model_validate(new_user)


@router.get("/users", response_model=list[UserOut])
async def list_users(
    user: dict = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> list[UserOut]:
    result = await db.execute(select(User))
    return [UserOut.model_validate(u) for u in result.scalars().all()]


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID,
    body: UserPatch,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    # admin은 자신의 계정만 수정 가능
    if current_user["role"] == "admin" and str(user_id) != current_user["sub"]:
        raise HTTPException(status_code=403, detail="forbidden")

    target = await _get_user_or_404(user_id, db)

    if body.email is not None:
        target.email = body.email
    if body.password is not None:
        target.password_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()

    await db.flush()
    await db.refresh(target)
    return UserOut.model_validate(target)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: uuid.UUID,
    user: dict = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> None:
    target = await _get_user_or_404(user_id, db)
    await db.delete(target)
    await db.flush()
