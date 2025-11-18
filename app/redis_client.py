import redis.asyncio as aioredis
from typing import AsyncIterator
from fastapi import Depends, FastAPI

redis_client = None

def init_redis(app: FastAPI):
    global redis_client

    redis_client = aioredis.Redis(host="localhost", port=6379, db=0)
    app.state.redis = redis_client

async def get_redis() -> AsyncIterator[aioredis.Redis]:
    yield redis_client #type: ignore