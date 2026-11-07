from datetime import datetime, timedelta, timezone
from uuid import uuid4
import jwt
from fastapi import Header, HTTPException
from fastapi import Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, RevokedToken
from pwdlib import PasswordHash
from app.settings import settings

password_hash = PasswordHash.recommended()
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = 60


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return password_hash.verify(password, encoded)
    except Exception:
        return False


def create_access_token(subject: str) -> tuple[str, datetime]:
    expires = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_MINUTES)
    token = jwt.encode({"sub": subject, "jti": str(uuid4()), "iat": datetime.now(timezone.utc),
                        "exp": expires}, settings.auth_secret, algorithm=JWT_ALGORITHM)
    return token, expires


def require_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Sign-in required", headers={"WWW-Authenticate": "Bearer"})
    token = authorization[7:]
    try:
        claims = jwt.decode(token, settings.auth_secret, algorithms=[JWT_ALGORITHM], options={"require": ["sub", "exp", "jti"]})
        subject = str(claims["sub"])
        user = db.get(User, subject)
        if not user or not user.is_active or db.get(RevokedToken, str(claims["jti"])):
            raise HTTPException(status_code=401, detail="Session expired or invalid", headers={"WWW-Authenticate": "Bearer"})
        return subject
    except HTTPException:
        raise
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Session expired or invalid", headers={"WWW-Authenticate": "Bearer"}) from exc


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.auth_secret, algorithms=[JWT_ALGORITHM], options={"require": ["sub", "exp", "jti"]})
