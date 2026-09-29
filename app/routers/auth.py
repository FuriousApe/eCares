from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.auth import COOKIE_NAME, get_current_user, sign_session
from app.db import get_session
from app.models import User
from app.schemas import LoginBody, UserOut

router = APIRouter(tags=["auth"])


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_session)):
    return db.query(User).all()


@router.post("/login", response_model=UserOut)
def login(body: LoginBody, response: Response, db: Session = Depends(get_session)):
    user = db.get(User, body.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="unknown user_id")
    response.set_cookie(COOKIE_NAME, sign_session(user.id), httponly=True)
    return user


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
