from fastapi import FastAPI
from app.routers import users, auth
from app.redis_client import get_redis, init_redis
from fastapi import Depends
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_redis(app)
    yield
    await app.state.redis.aclose()

app = FastAPI(lifespan=lifespan)

app.include_router(users.router)
app.include_router(auth.router)

@app.get("/redis-test")
async def redis_test(redis= Depends(get_redis)):
    await redis.set("greet", "Hello from redis!")
    value = await redis.get("greet")
    return {"stored_value" : value.decode()}

@app.get("/")
def root():
    return {"message": "Chat app backend is running"}
