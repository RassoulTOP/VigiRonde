import uuid
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Role, User
from app.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

DB = Annotated[Session, Depends(get_db)]


def get_current_user(db: DB, token: Annotated[str, Depends(oauth2_scheme)]) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Session invalide ou expirée",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise unauthorized
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: Role):
    def checker(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Droits insuffisants")
        return user

    return checker


Manager = Annotated[User, Depends(require_roles(Role.admin, Role.superviseur))]
Admin = Annotated[User, Depends(require_roles(Role.admin))]
