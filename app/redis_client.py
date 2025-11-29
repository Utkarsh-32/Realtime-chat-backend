import redis.asyncio as aioredis
from typing import AsyncIterator
from fastapi import Depends, FastAPI

redis_client: aioredis.Redis | None

async def init_redis(app: FastAPI, *, host: str = "localhost", port: int = 6379, db: int = 0):
    global redis_client

    redis_client = aioredis.Redis(host=host, port=port, db=db)
    app.state.redis = redis_client

async def close_redis(app: FastAPI):
    global redis_client
    if redis_client:
        try:
            await redis_client.close()
            await redis_client.connection_pool.disconnect()
        except Exception:
            pass
        redis_client = None
        app.state.redis = None

async def get_redis() -> AsyncIterator[aioredis.Redis]:
    yield redis_client #type: ignore