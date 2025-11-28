from fastapi import (APIRouter, WebSocket, WebSocketDisconnect, Depends, 
        HTTPException, status)
from app.auth import get_current_user
from app.database import get_db
from typing import Dict, Any
import jwt
from jwt.exceptions import InvalidTokenError, ExpiredSignatureError
from datetime import datetime, timezone
from app.auth import SECRET_KEY, ALGORITHM
from sqlalchemy import select
from app.models import User, Messages

router = APIRouter(prefix="/ws", tags=["websocket"])

class ConnectionManager:
    def __init__(self):
        self.active: Dict[int, WebSocket] = {}
    
    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active[user_id] = websocket
        payload = {
            "type": "presence",
            "user_id": user_id,
            "presence_status": "online",
        }
        await self._broadcast_except(user_id, payload)
    
    async def disconnect(self, user_id: int, last_seen_iso: str | None = None):
        self.active.pop(user_id, None)
        payload = {
            "type": "presence",
            "user_id": user_id,
            "presence_status": "offline",
            "last_seen": last_seen_iso,
        }
        await self._broadcast_except(user_id, payload)
        
    
    def is_online(self, user_id: int) -> bool:
        return user_id in self.active
    
    async def send_json_to(self, user_id: int, payload: dict):
        ws = self.active[user_id]
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
        result = await db.execute(select(User).where(User.id==user_id))
        user = result.scalar_one_or_none()
        return user, db
    except Exception:
        raise
    finally:
        await gen.aclose() #type: ignore

async def _send_pending_messages(user_id: int):
    gen = get_db()
    try:
        db = await gen.__anext__()
        result = await db.execute(
            select(Messages).where(
                Messages.recipient_id==user_id, Messages.status=='pending'
            ))
        pending = result.scalars().all()
        for msg in pending:
            payload = {
                "type": "message",
                "message_id": msg.id,
                "author_id": msg.author_id,
                "message": msg.message,
                "timestamp": msg.timestamp.isoformat(),
                "status": "delivered",
            }
            if manager.is_online(user_id):
                await manager.send_json_to(user_id, payload)
        await db.commit()
    finally:
        await gen.aclose() #type: ignore

@router.websocket("/chat")
async def websocket_chat(websocket: WebSocket):
    token = websocket.query_params.get("token")
    
    if not token:
        await websocket.accept()
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM]) #type: ignore
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
    
    gen = get_db()
    try:
        db = await gen.__anext__()
        result = await db.execute(select(User).where(User.id==user_id))
        user = result.scalar_one_or_none()
        if user:
            user.presence_status = "online" #type: ignore
            db.add(user)
            await db.commit()
            await db.refresh(user)
    finally:
        await gen.aclose() #type: ignore
    
    await manager.connect(user_id, websocket)

    try:
        await _send_pending_messages(user_id)
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "message":
                recipient_id = int(data.get("recipient_id"))
                text = data.get("message", '').strip()
                if not text:
                    await websocket.send_json({"type":"error", "reason":"empty message"})
                    continue
                gen = get_db()
                try:
                    db = await gen.__anext__()
                    msg = Messages(
                        author_id=user_id,
                        recipient_id=recipient_id,
                        message=text,
                        status="pending"
                    )
                    db.add(msg)
                    await db.flush()
                    message_id = msg.id

                    if manager.is_online(recipient_id):
                        forward_payload = {
                            "type": "message",
                            "message_id": msg.id,
                            "author_id": user_id,
                            "message": text,
                            "timestamp": msg.timestamp.isoformat(),
                            "status": "delivered"
                        }
                        await manager.send_json_to(recipient_id, forward_payload)
                        msg.status = "delivered" #type: ignore
                    
                    await db.commit()
                
                finally:
                    await gen.aclose() #type: ignore

                ack = {"type":"ack", "message_id": message_id, "status": msg.status}
                await websocket.send_json(ack)
            
            elif data.get("type") == "read":
                mid = int(data.get("message_id"))
                gen = get_db()
                try:
                    db = await gen.__anext__()
                    result = await db.execute(select(Messages).where(Messages.id==mid))
                    m = result.scalar_one_or_none()
                    if m and m.recipient_id == user_id and m.status != "read": #type: ignore
                        m.status = "read" #type: ignore
                        await db.commit()
                        if manager.is_online(m.author_id): #type: ignore
                            await manager.send_json_to(m.author_id, { #type: ignore
                                "type": "read_reciept",
                                "message_id": m.id,
                                "user_id": user_id
                            }) 
                finally:
                    await gen.aclose() #type: ignore

            else:
                await websocket.send_json({"type":"error", "reason":"unknown_type"})
    
    except WebSocketDisconnect:
        gen = get_db()
        try:
            db = await gen.__anext__()
            result = await db.execute(select(User).where(User.id==user_id))
            user = result.scalar_one_or_none()
            if user:
                user.presence_status = "offline" #type: ignore
                user.last_seen = datetime.now(timezone.utc) #type: ignore
                db.add(user)
                await db.commit()
                await db.refresh(user)
                last_seen_iso = user.last_seen.isoformat()
            else:
                last_seen_iso = None
        finally:
            await gen.aclose() #type: ignore
        await manager.disconnect(user_id, last_seen_iso)
    
    except Exception:
        await manager.disconnect(user_id)
        try:
            await websocket.close()
        except Exception:
            pass
