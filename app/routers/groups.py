import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel

from app.auth_service import get_current_user
from app.database import get_db
from app.models import Group, GroupMember, User

router = APIRouter(prefix="/groups", tags=["groups"])

logger = logging.getLogger(__name__)

class GroupOut(BaseModel):
    id: int
    name: str

    class Config:
        orm_mode = True


@router.post("/create-group")
async def create_group(name: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not name.strip():
        logger.warning("Group name not provided", exc_info=True)
        raise HTTPException(400, "Group name not provided")

    if not user:
        logger.warning("User does not exist or not authenticated", exc_info=True)
        raise HTTPException(400, "User not found")

    user_id = user.id
    group = Group(name=name, created_by=user_id)
    db.add(group)
    await db.commit()
    await db.refresh(group)
    group_creator = GroupMember(group_id=group.id, user_id=user_id, role="admin")
    db.add(group_creator)
    await db.commit()
    await db.refresh(group_creator)
    logger.info("Group created successfully", extra={"group_id": group.id, "creator": user_id})
    return {"Success": "Group Created", "group_id": group.id}


@router.post("/{group_id}/add-member")
async def add_member(group_id: int, user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        logger.warning("Group does not exist", exc_info=True)
        raise HTTPException(400, "Group does not exist")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        logger.warning("User does not exist or not authenticated", exc_info=True)
        raise HTTPException(400, "User not found")
    group_member = GroupMember(group_id=group.id, user_id=user.id, role="group_member")
    db.add(group_member)
    await db.commit()
    await db.refresh(group_member)
    logger.info("User added to the group", extra={"user_id": user.id, "group_id": group.id})
    return {"Success": "User added to the group"}

@router.get("/all", response_model=list[GroupOut])
async def get_groups(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Group))
    groups = result.scalars().all()
    return groups