from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth_service import get_current_user
from app.database import get_db
from app.models import Group, GroupMember, User

router = APIRouter(prefix="/groups", tags=["groups"])


@router.post("/create-group")
async def create_group(name: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not name:
        raise HTTPException(400, "Group name not provided")

    if not user:
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
    return {"Success": "Group Created", "group_id": group.id}


@router.post("/{group_id}/add-member")
async def add_member(group_id: int, user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(400, "Group does not exist")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(400, "User not found")
    group_member = GroupMember(group_id=group.id, user_id=user.id, role="group_member")
    db.add(group_member)
    await db.commit()
    await db.refresh(group_member)
    return {"Success": "User added to the group"}
