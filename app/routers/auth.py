from fastapi import APIRouter, Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import User
from sqlalchemy import select, or_
from pydantic import BaseModel
from app.auth import (get_password_hash, verify_password, create_access_token, 
create_refresh_token, SECRET_KEY, ALGORITHM)
import jwt
from jwt.exceptions import InvalidTokenError, ExpiredSignatureError

router = APIRouter(prefix="/auth", tags=["auth"])

class SignUpRequest(BaseModel):
    username: str
    email: str
    password: str


@router.post("/signup", status_code=201)
async def signup(
    data: SignUpRequest,
    db: AsyncSession = Depends(get_db)
    ):
    result = await db.execute(select(User).where(or_
        (
        User.username==data.username, 
        User.email==data.email
        )))
    exists = result.scalar_one_or_none()
    if exists:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Username or email already exists")
    hashed_password = get_password_hash(data.password)
    new_user = User(username=data.username, email=data.email, password=hashed_password)
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    if new_user.id is not None:
        return {"Success": "User created"}
    return {"Error": "User not created"}


@router.post("/login")
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
    ):
    result = await db.execute(select(User).where(User.username == form.username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invalid username")
    if not verify_password(form.password, user.password): #type: ignore
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid password")
    token = create_access_token({"user_id": user.id}, expires_delta=30)
    refresh = create_refresh_token({"user_id": user.id}, expires_delta=7)
    return {"access_token": token, "refresh_token": refresh ,"token_type": "bearer"}

@router.post("/refresh")
async def refresh(
    token: str = Header(..., alias="Authorization"),
    db: AsyncSession = Depends(get_db)
    ):
    if not token.startswith("Bearer "):
        raise HTTPException(401, "Missing token")
    token = token.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        token_type = payload.get("type")
    except (InvalidTokenError, ExpiredSignatureError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token type")
    if token_type != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    result = await db.execute(select(User).where(User.id==user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Not found")
    access_token = create_access_token({"user_id": user_id}, expires_delta=30)
    refresh_token = create_refresh_token({"user_id": user_id}, expires_delta=7)
    return {"access_token": access_token, "refresh_token": refresh_token ,"token_type": "bearer"}