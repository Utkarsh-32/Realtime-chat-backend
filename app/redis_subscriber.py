import asyncio
import json
import logging
from typing import Any

from redis.asyncio.client import Redis
from sqlalchemy import select

from app.database import get_db
from app.models import GroupMember
from app.routers.ws import CHAT_CHANNEL, PRESENCE_CHANNEL, READ_CHANNEL, manager

logger = logging.getLogger(__name__)


async def handle_pub_messages(msg: dict[str, Any]):
    typ = msg.get("type")
    if typ == "message":
        recipient = msg.get("recipient_id")
        if recipient and manager.is_online(recipient):
            await manager.send_json_to(recipient, msg)
    elif typ == "presence":
        user_id = msg.get("user_id")
        if user_id:
            await manager.broadcast_except(user_id, msg)
    elif typ == "read_receipt":
        author_id = msg.get("author_id")
        if author_id and manager.is_online(author_id):
            await manager.send_json_to(author_id, msg)


async def subscriber_loop(redis: Redis, channels: list[str]):
    pubsub = redis.pubsub()
    await pubsub.subscribe(*channels)
    await pubsub.psubscribe("group:*")
    try:
        async for raw in pubsub.listen():
            if raw is None:
                continue
            msg_type = raw.get("type")
            data = raw.get("data")
            if msg_type not in ("message", "pmessage"):
                continue
            if msg_type == "pmessage":
                if isinstance(data, (bytes, bytearray)):
                    payload = json.loads(data.decode())
                else:
                    payload = json.loads(data)
                group_id = payload.get("group_id")
                gen = get_db()
                try:
                    db = await gen.__anext__()
                    result = await db.execute(select(GroupMember.user_id).where(GroupMember.group_id == group_id))
                    members = result.scalars().all()
                    if not members:
                        continue
                    for m_id in members:
                        if manager.is_online(m_id):
                            await manager.send_json_to(m_id, payload=payload)
                except Exception:
                    continue
                finally:
                    await gen.aclose()  # type: ignore
                continue
            if msg_type == "message":
                if isinstance(data, (bytes, bytearray)):
                    try:
                        payload = json.loads(data.decode())
                    except Exception:
                        continue
                elif isinstance(data, str):
                    try:
                        payload = json.loads(data)
                    except Exception:
                        continue
                else:
                    continue
                await handle_pub_messages(payload)
    except asyncio.CancelledError:
        try:
            await pubsub.unsubscribe()
            await pubsub.close()
        except Exception as e:
            logger.warning(f"Failed to clean Redis pubsub during shutdown: {e}")
            pass
        raise
    finally:
        try:
            await pubsub.unsubscribe()
            await pubsub.close()
        except Exception as e:
            logger.warning(f"Failed to clean Redis pubsub during shutdown: {e}")
            pass


async def start_redis_listener(
    redis: Redis, *, channels: tuple[str, ...] = (CHAT_CHANNEL, PRESENCE_CHANNEL, READ_CHANNEL)
) -> asyncio.Task:
    loop = asyncio.get_running_loop()
    task = loop.create_task(subscriber_loop(redis, list(channels)))
    return task
