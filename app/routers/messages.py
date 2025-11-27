from app.auth import get_current_user
from app.database import get_db
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import User, Messages
from sqlalchemy import select
from pydantic import BaseModel

router = APIRouter(prefix="/messages", tags=["messages"])

class MessageCreate(BaseModel):
    recipient_id: int
    message: str

@router.post("/send")
async def send_message(
    data: MessageCreate,
    author = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
    ):
    if not data.message:
        raise HTTPException(400, "Invalid Message")
    result = await db.execute(select(User).where(User.id==data.recipient_id))
    recipient = result.scalar_one_or_none()
    if not recipient:
        raise HTTPException(400, "Recipient does not exist")
    message_sent = Messages(
        author_id=author.id, 
        recipient_id=data.recipient_id,
        message=data.message,
        )
    db.add(message_sent)
    await db.commit()
    await db.refresh(message_sent)
    return {
        "author_id": author.id, 
        "recipient_id": data.recipient_id, 
        "message": message_sent.message,
        "timestamp": message_sent.timestamp
        }

@router.get("/inbox")
async def inbox(
    user = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db)
    ):
    result = await db.execute(select(Messages).where(Messages.recipient_id==user.id))
    message = result.scalars().all()
    if not message:
        return []
    return message

@router.get("/sent")
async def sent_messages(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Messages).where(Messages.author_id==user.id))
    message = result.scalars().all()
    if not message:
        return []
    return message