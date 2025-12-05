from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


async def get_username(user_id: int, db: AsyncSession) -> str | None:
    result = await db.execute(select(User.username).where(User.id == user_id))
    return result.scalar_one_or_none()
