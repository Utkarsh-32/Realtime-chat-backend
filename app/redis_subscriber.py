import asyncio
import json
from typing import Any

from redis.asyncio.client import Redis

from app.routers.ws import CHAT_CHANNEL, PRESENCE_CHANNEL, READ_CHANNEL, manager


async def _handle_pub_messages(msg: dict[str, Any]):
    typ = msg.get("type")
    if typ == "message":
        recipient = msg.get("recipient_id")
        if recipient and manager.is_online(recipient):
            await manager.send_json_to(recipient, msg)
    elif typ == "presence":
        user_id = msg.get("user_id")
        if user_id:
            await manager._broadcast_except(user_id, msg)
    elif typ == "read_receipt":
        author_id = msg.get("author_id")
        if author_id and manager.is_online(author_id):
            await manager.send_json_to(author_id, msg)


async def _subscriber_loop(redis: Redis, channels: list[str]):
    pubsub = redis.pubsub()
    await pubsub.subscribe(*channels)
    try:
        async for raw in pubsub.listen():
            if raw is None:
                continue
            if raw.get("type") != "message":
                continue
            data = raw.get("data")
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
            await _handle_pub_messages(payload)
    except asyncio.CancelledError:
        try:
            await pubsub.unsubscribe()
            await pubsub.close()
        except Exception:
            pass
        raise
    finally:
        try:
            await pubsub.unsubscribe()
            await pubsub.close()
        except Exception:
            pass


async def start_redis_listener(
    redis: Redis, *, channels: tuple[str, ...] = (CHAT_CHANNEL, PRESENCE_CHANNEL, READ_CHANNEL)
) -> asyncio.Task:
    loop = asyncio.get_running_loop()
    task = loop.create_task(_subscriber_loop(redis, list(channels)))
    return task
