from fastapi import FastAPI
from app.routers import users, auth, messages, ws
from app.redis_client import get_redis, init_redis, close_redis
from fastapi import Depends
from contextlib import asynccontextmanager
import os
from app.redis_subscriber import start_redis_listener
import asyncio
from app.routers.ws import CHAT_CHANNEL, READ_CHANNEL, PRESENCE_CHANNEL

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_redis(app) #type: ignore
    redis = app.state.redis
    app.state.redis_task = await start_redis_listener(redis, channels=(CHAT_CHANNEL, PRESENCE_CHANNEL, READ_CHANNEL))
    try:
        yield
    finally:
        task = getattr(app.state, "redis_task", None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await close_redis(app) #type: ignore

app = FastAPI(lifespan=lifespan)

app.include_router(users.router)
app.include_router(auth.router)
app.include_router(messages.router)
app.include_router(ws.router)

@app.get("/redis-test")
async def redis_test(redis= Depends(get_redis)):
    await redis.set("greet", "Hello from redis!")
    value = await redis.get("greet")
    return {"stored_value" : value.decode()}

@app.get("/")
def root():
    return {"message": "Chat app backend is running"}