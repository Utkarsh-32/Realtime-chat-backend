from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth_service import get_current_user
from app.database import get_db
from app.models import User
from app.routers.ws import manager

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me")
async def me(user=Depends(get_current_user)):
    return user


@router.get("/presence/{user_id}")
async def presence(user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(400, "User not found")
    last_seen_iso = user.last_seen.isoformat() if user.last_seen else None  # type: ignore
    return {"user_id": user_id, "presence_status": user.presence_status, "last_seen": last_seen_iso}


@router.get("/online")
async def online():
    return {"online": list(manager.active.keys())}
