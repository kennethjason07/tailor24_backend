"""Users router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.common.responses import ok
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin_finance
from app.modules.users.schemas import UserCreateRequest, UserUpdateRequest
from app.modules.users.service import UsersService

router = APIRouter()


def get_svc() -> UsersService:
    return UsersService(get_db())


@router.post("", summary="Create user (admin only)")
def create_user(
    body: UserCreateRequest,
    _: dict = Depends(require_admin_finance),
    svc: UsersService = Depends(get_svc),
):
    user = svc.create_user(
        name=body.name,
        phone=body.phone,
        password=body.password,
        role=body.role.value,
        email=str(body.email) if body.email else None,
    )
    return ok(data=user, message="User created")


@router.get("", summary="List users (admin only)")
def list_users(
    role: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: dict = Depends(require_admin_finance),
    svc: UsersService = Depends(get_svc),
):
    skip = (page - 1) * page_size
    users = svc.list_users(role=role, skip=skip, limit=page_size)
    return ok(data=users)


@router.get("/{user_id}", summary="Get user by ID")
def get_user(
    user_id: str,
    current_user: dict = Depends(get_current_user),
    svc: UsersService = Depends(get_svc),
):
    # Users can view their own profile; admins can view any
    if str(current_user["_id"]) != user_id and current_user.get("role") != "ADMIN_FINANCE":
        from app.common.exceptions import AuthorizationError
        raise AuthorizationError("You are not authorized to view this user.")
    user = svc.get_user(user_id)
    return ok(data=user)


@router.patch("/{user_id}", summary="Update user")
def update_user(
    user_id: str,
    body: UserUpdateRequest,
    current_user: dict = Depends(get_current_user),
    svc: UsersService = Depends(get_svc),
):
    if str(current_user["_id"]) != user_id and current_user.get("role") != "ADMIN_FINANCE":
        from app.common.exceptions import AuthorizationError
        raise AuthorizationError("You are not authorized to update this user.")
    updates = body.model_dump(exclude_none=True)
    if "email" in updates and updates["email"]:
        updates["email"] = str(updates["email"])
    user = svc.update_user(user_id, updates)
    return ok(data=user, message="User updated")
