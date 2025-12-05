import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth_service import get_current_user
from app.database import get_db
from app.models import Messages, User

router = APIRouter(prefix="/messages", tags=["messages"])

logger = logging.getLogger(__name__)


class MessageCreate(BaseModel):
    recipient_id: int
    message: str


@router.post("/send")
async def send_message(data: MessageCreate, author=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not data.message:
        logger.warning("Invalid message", exc_info=True)
        raise HTTPException(400, "Invalid Message")
    result = await db.execute(select(User).where(User.id == data.recipient_id))
    recipient = result.scalar_one_or_none()
    if not recipient:
        logger.warning("Recipient id does not exist", exc_info=True)
        raise HTTPException(400, "Recipient does not exist")
    if not author:
        logger.warning("User not authenticated", exc_info=True)
        raise HTTPException(401, "Not authenticated")
    message_sent = Messages(
        author_id=author.id,
        recipient_id=data.recipient_id,
        message=data.message,
    )
    db.add(message_sent)
    await db.commit()
    await db.refresh(message_sent)
    logger.info("Message sent")
    return {
        "author_id": author.id,
        "recipient_id": data.recipient_id,
        "message": message_sent.message,
        "timestamp": message_sent.timestamp,
    }


@router.get("/inbox")
async def inbox(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Messages).where(Messages.recipient_id == user.id))
    message = result.scalars().all()
    if not message:
        return []
    return message


@router.get("/sent")
async def sent_messages(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Messages).where(Messages.author_id == user.id))
    message = result.scalars().all()
    if not message:
        return []
    return message


@router.get("/{recipient_id}")
async def get_direct_messages(recipient_id: int, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    me_id = user.id
    result = await db.execute(
        select(Messages)
        .options(
            selectinload(Messages.author),
            selectinload(Messages.recipient),
        )
        .where(
            or_(
                and_(Messages.author_id == me_id, Messages.recipient_id == recipient_id),
                and_(Messages.author_id == recipient_id, Messages.recipient_id == me_id),
            )
        )
        .order_by(Messages.id.asc())
    )

    msgs = result.scalars().all()
    output = []
    for m in msgs:
        output.append(
            {
                "message_id": m.id,
                "author_id": m.author_id,
                "recipient_id": m.recipient_id,
                "author_name": m.author.username,
                "recipient_name": m.recipient.username,
                "message": m.message,
                "image_url": m.image_url,
                "timestamp": m.timestamp.isoformat(),
                "status": m.status,
            }
        )
    return output
