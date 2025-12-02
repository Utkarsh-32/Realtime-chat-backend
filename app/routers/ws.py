import json
from datetime import datetime, timezone
from typing import Dict

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from sqlalchemy import select

from app.auth_service import ALGORITHM, SECRET_KEY
from app.database import get_db
from app.models import Messages, User
from app.utils.rate_limit import check_rate_limit

router = APIRouter(prefix="/ws", tags=["websocket"])

CHAT_CHANNEL = "chat_messages"
PRESENCE_CHANNEL = "presence"
READ_CHANNEL = "read_receipt"


class ConnectionManager:
    def __init__(self):
        self.active: Dict[int, WebSocket] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        redis = websocket.app.state.redis
        self.active[user_id] = websocket
        payload = {
            "type": "presence",
            "user_id": user_id,
            "presence_status": "online",
        }
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

    async def _broadcast_except(self, except_user_id: int, payload: dict):
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


async def _fetch_user_from_db(user_id: int):
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


async def _send_pending_messages(user_id: int):
    gen = get_db()
    try:
        db = await gen.__anext__()
        result = await db.execute(
            select(Messages).where(Messages.recipient_id == user_id, Messages.status == "pending")
        )
        pending = result.scalars().all()
        for msg in pending:
            payload = {
                "type": "message",
                "message_id": msg.id,
                "author_id": msg.author_id,
                "recipient_id": msg.recipient_id,
                "message": msg.message,
                "timestamp": msg.timestamp.isoformat(),
                "status": "delivered",
            }
            if manager.is_online(user_id):
                await manager.send_json_to(user_id, payload)
        await db.commit()
    finally:
        await gen.aclose()  # type: ignore


@router.websocket("/chat")
async def websocket_chat(websocket: WebSocket):
    redis = websocket.app.state.redis
    token = websocket.query_params.get("token")

    if not token:
        await websocket.accept()
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])  # type: ignore
        user_id = payload.get("user_id")
        token_type = payload.get("type")
        if not user_id or token_type != "access":
            await websocket.accept()
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    except (InvalidTokenError, ExpiredSignatureError):
        await websocket.accept()
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user, _db = await _fetch_user_from_db(user_id)
    if not user:
        await websocket.accept()
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(user_id, websocket)

    gen = get_db()
    try:
        db = await gen.__anext__()
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user:
            user.presence_status = "online"  # type: ignore
            db.add(user)
            await db.commit()
    finally:
        await gen.aclose()  # type: ignore

    try:
        await _send_pending_messages(user_id)
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "message":
                recipient_id = int(data.get("recipient_id"))
                if not recipient_id:
                    await websocket.send_json({"type": "error", "reason": "recipient id not provided"})
                    continue
                text = data.get("message", "").strip()
                if not text:
                    await websocket.send_json({"type": "error", "reason": "empty message"})
                    continue

                rl_key = f"rl:{user_id}:send_message"
                allowed = await check_rate_limit(redis=redis, key=rl_key, limit=20, window_seconds=60)
                if not allowed:
                    await websocket.send_json({"type": "error", "reason": "rate limit exceeded"})
                    continue

                gen = get_db()
                try:
                    db = await gen.__anext__()
                    msg = Messages(author_id=user_id, recipient_id=recipient_id, message=text, status="pending")

                    db.add(msg)
                    await db.flush()
                    message_id = msg.id

                    is_online = manager.is_online(recipient_id)
                    forward_payload = {
                        "type": "message",
                        "message_id": msg.id,
                        "author_id": user_id,
                        "recipient_id": recipient_id,
                        "message": text,
                        "timestamp": msg.timestamp.isoformat(),
                        "status": "delivered" if is_online else "pending",
                    }
                    await redis.publish(CHAT_CHANNEL, json.dumps(forward_payload))

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
                            await redis.publish(
                                READ_CHANNEL,
                                json.dumps(
                                    {
                                        "type": "read_receipt",
                                        "message_id": m.id,
                                        "reader_id": user_id,
                                        "author_id": author_id,
                                    }
                                ),
                            )
                        except Exception:
                            await manager.disconnect(int(author_id))  # type: ignore
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

        await redis.publish(
            PRESENCE_CHANNEL,
            json.dumps(
                {"type": "presence", "user_id": user_id, "presence_status": "offline", "last_seen_iso": last_seen_iso}
            ),
        )
        await manager.disconnect(user_id)

    except Exception:
        await manager.disconnect(user_id)
        try:
            await websocket.close()
        except Exception:
            pass
