"""Auth router."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.common.responses import ok
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.modules.auth.schemas import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse
from app.modules.auth.service import AuthService
from app.common.utils import doc_to_dict

router = APIRouter()


def get_auth_service() -> AuthService:
    return AuthService(get_db())


@router.post("/register", summary="Register a new customer or tailor")
def register(body: RegisterRequest, svc: AuthService = Depends(get_auth_service)):
    user = svc.register(
        name=body.name,
        phone=body.phone,
        password=body.password,
        role=body.role,
        email=str(body.email) if body.email else None,
    )
    return ok(
        data={"id": str(user["_id"]), "name": user["name"], "role": user["role"]},
        message="Registration successful",
    )


@router.post("/login", response_model=None, summary="Login and receive JWT tokens")
def login(body: LoginRequest, svc: AuthService = Depends(get_auth_service)):
    tokens = svc.login(body.phone, body.password)
    return ok(data=tokens, message="Login successful")


@router.post("/refresh", summary="Refresh access token")
def refresh(body: RefreshRequest, svc: AuthService = Depends(get_auth_service)):
    tokens = svc.refresh(body.refresh_token)
    return ok(data=tokens, message="Token refreshed")


@router.get("/me", summary="Get current authenticated user")
def me(current_user: dict = Depends(get_current_user)):
    user = doc_to_dict(current_user)
    user.pop("passwordHash", None)
    return ok(data=user)
