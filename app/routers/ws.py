import json
import logging
from datetime import datetime, timezone
from typing import Dict

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from sqlalchemy import select

from app.auth_service import ALGORITHM, SECRET_KEY
from app.database import get_db
from app.models import GroupMember, GroupMessage, Messages, User
from app.utils.rate_limit import check_rate_limit
from app.utils.user import get_username

router = APIRouter(prefix="/ws", tags=["websocket"])
logger = logging.getLogger(__name__)

CHAT_CHANNEL = "chat_messages"
PRESENCE_CHANNEL = "presence"
READ_CHANNEL = "read_receipt"


class ConnectionManager:
    def __init__(self):
        self.active: Dict[int, WebSocket] = {}  # type: ignore

    async def connect(self, user_id: int, websocket: WebSocket, username):
        redis = websocket.app.state.redis
        self.active[user_id] = websocket
        payload = {"type": "presence", "user_id": user_id, "presence_status": "online", "username": username}
        await redis.publish(PRESENCE_CHANNEL, json.dumps(payload))

    async def disconnect(self, user_id: int):
        self.active.pop(user_id, None)

    def is_online(self, user_id: int) -> bool:
        return user_id in self.active

    async def send_json_to(self, user_id: int, payload: dict):
        ws = self.active.get(user_id)
        if not ws:
            return
        try:
            await ws.send_json(payload)
        except Exception:
            self.active.pop(user_id, None)

    async def broadcast_except(self, except_user_id: int, payload: dict):
        to_remove = []
        for uid, ws in list(self.active.items()):
            if uid == except_user_id:
                continue
            try:
                await ws.send_json(payload)
            except Exception:
                to_remove.append(uid)

        for uid in to_remove:
            self.active.pop(uid, None)


manager = ConnectionManager()


async def fetch_user_from_db(user_id: int):
    gen = get_db()
    try:
        db = await gen.__anext__()
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        return user, db
    except Exception:
        raise
    finally:
        await gen.aclose()  # type: ignore


async def send_pending_messages(user_id: int):
    gen = get_db()
    try:
        db = await gen.__anext__()
        result = await db.execute(
            select(Messages).where(Messages.recipient_id == user_id, Messages.status == "pending")
        )
        pending = result.scalars().all()

        for msg in pending:
            author_name = await get_username(msg.author_id, db)  # type: ignore
            payload = {
                "type": "message",
                "message_id": msg.id,
                "author_id": msg.author_id,
                "author_name": author_name,
                "recipient_id": msg.recipient_id,
                "message": msg.message,
                "timestamp": msg.timestamp.isoformat(),
                "status": "delivered",
                "image_url": msg.image_url or None,
            }
            if manager.is_online(user_id):
                await manager.send_json_to(user_id, payload)
        await db.commit()
    finally:
        await gen.aclose()  # type: ignore


async def send_unread_group_messages(user_id: int, websocket: WebSocket):
    gen = get_db()
    try:
        db = await gen.__anext__()
        result = await db.execute(
            select(GroupMember.group_id, GroupMember.last_read_message_id).where(GroupMember.user_id == user_id)
        )
        row = result.all()

        for grp_id, last_read in row:
            last_read = last_read or 0
            result = await db.execute(
                select(GroupMessage)
                .where(GroupMessage.group_id == grp_id, GroupMessage.id > last_read)
                .order_by(GroupMessage.id.asc())
            )
            unread_msgs = result.scalars().all()
            if not unread_msgs:
                continue
            for msg in unread_msgs:
                author_name = await get_username(msg.author_id, db)  # type: ignore
                await websocket.send_json(
                    {
                        "type": "group_message",
                        "group_id": grp_id,
                        "message_id": msg.id,
                        "author_id": msg.author_id,
                        "author_name": author_name,
                        "message": msg.message,
                        "timestamp": msg.timestamp.isoformat(),
                        "status": "delivered",
                        "image_url": msg.image_url or None,
                    }
                )
            new_last = unread_msgs[-1].id
            await db.execute(
                GroupMember.__table__.update()
                .where(GroupMember.user_id == user_id, GroupMember.group_id == grp_id)
                .values(last_read_message_id=new_last)
            )
        await db.commit()
    finally:
        await gen.aclose()  # type: ignore


@router.websocket("/chat")
async def websocket_chat(websocket: WebSocket):
    redis = websocket.app.state.redis
    token = websocket.headers.get("sec-websocket-protocol")

    if not token:
        await websocket.accept()
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    token = token.strip()
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])  # type: ignore
        user_id = payload.get("user_id")
        token_type = payload.get("type")
        if not user_id or token_type != "access":
            await websocket.accept()
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        logger.info("WebSocket connection active", extra={"user_id": user_id})
    except (InvalidTokenError, ExpiredSignatureError):
        await websocket.accept()
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        logger.warning("Invalid or Expired token", exc_info=True)
        return
    await websocket.accept(subprotocol=token)
    logger.info(f"websocket connected for user: {user_id}")

    gen = get_db()
    try:
        db = await gen.__anext__()
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user:
            user.presence_status = "online"  # type: ignore
            db.add(user)
            await db.commit()
            logger.info("User online", extra={"user_id": user.id})
        username = await get_username(user_id, db)
        await manager.connect(user_id, websocket, username)
    finally:
        await gen.aclose()  # type: ignore

    try:
        await send_pending_messages(user_id)
        await send_unread_group_messages(user_id, websocket)
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "message":
                recipient_id = int(data.get("recipient_id"))
                if not recipient_id:
                    await websocket.send_json({"type": "error", "reason": "recipient id not provided"})
                    continue
                text = data.get("message", "").strip()
                image_url = data.get("image_url", None)
                if not image_url and not text:
                    await websocket.send_json({"type": "error", "reason": "empty message"})
                    continue

                rl_key = f"rl:{user_id}:send_message"
                allowed = await check_rate_limit(redis=redis, key=rl_key, limit=20, window_seconds=60)
                if not allowed:
                    await websocket.send_json({"type": "error", "reason": "rate limit exceeded"})
                    logger.warning("Rate limit exceeded", extra={"user_id": user_id})
                    continue

                gen = get_db()
                try:
                    db = await gen.__anext__()
                    msg = Messages(
                        author_id=user_id,
                        recipient_id=recipient_id,
                        message=text,
                        status="pending",
                        image_url=image_url,
                    )

                    db.add(msg)
                    await db.flush()
                    message_id = msg.id

                    is_online = manager.is_online(recipient_id)
                    author_name = await get_username(user_id, db)
                    recipient_name = await get_username(recipient_id, db)
                    forward_payload = {
                        "type": "message",
                        "message_id": msg.id,
                        "author_id": user_id,
                        "author_name": author_name,
                        "recipient_id": recipient_id,
                        "recipient_name": recipient_name,
                        "message": text or None,
                        "timestamp": msg.timestamp.isoformat(),
                        "status": "delivered" if is_online else "pending",
                        "image_url": image_url or None,
                    }
                    await redis.publish(CHAT_CHANNEL, json.dumps(forward_payload))
                    logger.info("WS message forwarded", extra={"from": user_id, "to": recipient_id})
                    await db.commit()
                finally:
                    await gen.aclose()  # type: ignore

                ack = {"type": "ack", "message_id": message_id, "status": forward_payload.get("status", "pending")}
                await websocket.send_json(ack)

            elif data.get("type") == "read":
                mid = int(data.get("message_id"))
                if not mid:
                    await websocket.send_json({"type": "error", "reason": "message_id not provided"})
                    continue
                gen = get_db()
                try:
                    db = await gen.__anext__()
                    result = await db.execute(select(Messages).where(Messages.id == mid))
                    m = result.scalar_one_or_none()
                    if m and m.recipient_id == user_id and m.status != "read":  # type: ignore
                        m.status = "read"  # type: ignore
                        db.add(m)
                        await db.commit()
                        author_id = m.author_id
                        try:
                            reader_name = await get_username(user_id, db)  # type: ignore
                            await redis.publish(
                                READ_CHANNEL,
                                json.dumps(
                                    {
                                        "type": "read_receipt",
                                        "message_id": m.id,
                                        "reader_id": user_id,
                                        "author_id": author_id,
                                        "reader_name": reader_name,
                                    }
                                ),
                            )
                        except Exception:
                            await manager.disconnect(int(author_id))  # type: ignore
                finally:
                    await gen.aclose()  # type: ignore

            elif data.get("type") == "group_message":
                group_id = int(data.get("group_id"))
                text = data.get("message")
                image_url = data.get("image_url")
                if not group_id:
                    await websocket.send_json({"type": "error", "reason": "group id not found"})
                    continue
                if not text and not image_url:
                    await websocket.send_json({"type": "error", "reason": "empty message"})
                    continue
                author_id = user_id
                allowed = await check_rate_limit(redis, f"rl:{user_id}:group_message", limit=30, window_seconds=60)
                if not allowed:
                    await websocket.send_json({"type": "error", "reason": "rate limit exceeded"})
                    continue
                gen = get_db()
                try:
                    db = await gen.__anext__()
                    result = await db.execute(
                        select(GroupMember).where(GroupMember.user_id == author_id, GroupMember.group_id == group_id)
                    )
                    member = result.scalar_one_or_none()
                    if not member:
                        await websocket.send_json({"type": "error", "reason": "user is not a member of the group"})
                        continue
                    group_msg = GroupMessage(group_id=group_id, author_id=author_id, message=text, image_url=image_url)
                    db.add(group_msg)
                    await db.commit()
                    await db.refresh(group_msg)
                    group_msg_id = group_msg.id
                    author_name = await get_username(author_id, db)
                    payload = {
                        "type": "group_message",
                        "group_id": group_id,
                        "author_id": author_id,
                        "author_name": author_name,
                        "message_id": group_msg_id,
                        "message": text or None,
                        "timestamp": group_msg.timestamp.isoformat(),
                        "status": "pending",
                        "image_url": image_url or None,
                    }

                    await redis.publish(f"group:{group_id}", json.dumps(payload))
                    logger.info("Group message forwarded", extra={"user_id": user_id, "group_id": group_id})

                    await websocket.send_json({"type": "ack", "message_id": group_msg.id, "status": "pending"})
                except Exception:
                    await manager.disconnect(author_id)
                finally:
                    await gen.aclose()  # type: ignore

            elif data.get("type") == "group_read":
                group_id = int(data.get("group_id"))
                if not group_id:
                    await websocket.send_json({"type": "error", "reason": "group_id not provided"})
                    continue
                last_id = int(data.get("message_id") or 0)

                gen = get_db()
                try:
                    db = await gen.__anext__()
                    result = await db.execute(
                        select(GroupMessage.author_id).where(
                            GroupMessage.group_id == group_id, GroupMessage.id == last_id
                        )
                    )
                    author = result.scalar_one_or_none()
                    if author == user_id:
                        await websocket.send_json(
                            {"type": "error", "reason": "Authors cannot mark their own messages as read."}
                        )
                        continue
                    result = await db.execute(
                        GroupMember.__table__.update()
                        .where((GroupMember.group_id == group_id) & (GroupMember.user_id == user_id))
                        .values(last_read_message_id=last_id)
                    )
                    await db.commit()
                    payload = {"type": "group_read", "group_id": group_id, "user_id": user_id, "message_id": last_id}
                    await redis.publish(f"group:{group_id}", json.dumps(payload))
                finally:
                    await gen.aclose()  # type: ignore

            else:
                await websocket.send_json({"type": "error", "reason": "unknown_type"})

    except WebSocketDisconnect:
        gen = get_db()
        try:
            db = await gen.__anext__()
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if user:
                user.presence_status = "offline"  # type: ignore
                user.last_seen = datetime.now(timezone.utc)  # type: ignore
                db.add(user)
                await db.commit()
                last_seen_iso = user.last_seen.isoformat()
            else:
                last_seen_iso = None
        finally:
            await gen.aclose()  # type: ignore

        username = await get_username(user_id, db)
        await redis.publish(
            PRESENCE_CHANNEL,
            json.dumps(
                {
                    "type": "presence",
                    "user_id": user_id,
                    "username": username,
                    "presence_status": "offline",
                    "last_seen_iso": last_seen_iso,
                }
            ),
        )
        logger.info("User disconnected", extra={"user_id": user_id})
        await manager.disconnect(user_id)

    except Exception:
        logger.error("Websocket error", exc_info=True)
        await manager.disconnect(user_id)
        try:
            await websocket.close()
        except Exception:
            pass
