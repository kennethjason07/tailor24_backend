"""Notifications router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.common.responses import ok
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.modules.notifications.service import NotificationsService

router = APIRouter()


def get_svc():
    return NotificationsService(get_db())


@router.get("", summary="My notifications")
def my_notifications(
    status: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    svc: NotificationsService = Depends(get_svc),
):
    skip = (page - 1) * page_size
    notifications = svc.list_for_user(
        user_id=str(current_user["_id"]),
        status=status,
        skip=skip,
        limit=page_size,
    )
    return ok(data=notifications)


@router.patch("/{notification_id}/read", summary="Mark notification as read")
def mark_read(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
    svc: NotificationsService = Depends(get_svc),
):
    svc.mark_read(notification_id, str(current_user["_id"]))
    return ok(message="Notification marked as read")
