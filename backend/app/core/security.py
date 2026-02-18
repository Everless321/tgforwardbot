import hashlib
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

FIXED_PASSWORD_HASH = hashlib.sha256(b"zhc010321").hexdigest()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7

security_scheme = HTTPBearer()


def verify_password(plain_password: str) -> bool:
    return hashlib.sha256(plain_password.encode()).hexdigest() == FIXED_PASSWORD_HASH


def create_access_token() -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    payload = {"exp": expire, "sub": "admin"}
    return jwt.encode(payload, settings.auth_secret_key, algorithm=ALGORITHM)


def verify_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.auth_secret_key, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
) -> dict:
    return verify_token(credentials.credentials)
