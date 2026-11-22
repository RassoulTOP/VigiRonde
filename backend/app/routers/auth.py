from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select

from app.deps import DB, Admin, CurrentUser, Manager
from app.models import Role, User
from app.schemas import Token, UserCreate, UserOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(tags=["auth & utilisateurs"])


@router.post("/auth/login", response_model=Token)
def login(db: DB, form: Annotated[OAuth2PasswordRequestForm, Depends()]):
    user = db.scalar(select(User).where(func.lower(User.email) == form.username.lower()))
    if user is None or not user.is_active or not verify_password(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou mot de passe incorrect")
    token = create_access_token(str(user.id), user.role.value, str(user.company_id))
    return Token(access_token=token, role=user.role, full_name=user.full_name)


@router.get("/auth/me", response_model=UserOut)
def me(user: CurrentUser):
    return user


@router.get("/users", response_model=list[UserOut])
def list_users(db: DB, user: Manager, role: Role | None = None):
    q = select(User).where(User.company_id == user.company_id).order_by(User.full_name)
    if role:
        q = q.where(User.role == role)
    return db.scalars(q).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(db: DB, admin: Admin, body: UserCreate):
    if db.scalar(select(User).where(func.lower(User.email) == body.email.lower())):
        raise HTTPException(409, "Cet e-mail est déjà utilisé")
    u = User(
        company_id=admin.company_id,
        email=body.email.lower(),
        full_name=body.full_name,
        phone=body.phone,
        role=body.role,
        qualifications=body.qualifications,
        password_hash=hash_password(body.password),
    )
    db.add(u)
    db.commit()
    return u
