from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.auth import get_current_user

router = APIRouter(prefix="/users", tags=["Users"])

@router.get("/me")
async def me(user = Depends(get_current_user)):
    return user