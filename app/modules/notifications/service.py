"""
TAILOR24 — Notifications Service
Notifications are written to MongoDB and can later be dispatched
via a background worker (SMS/WhatsApp/Push/Email).
Notification delivery deliberately does NOT block transactional workflows.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from bson import ObjectId
from pymongo.database import Database

from app.common.enums import NotificationChannel, NotificationStatus
from app.common.utils import doc_to_dict, to_object_id

logger = logging.getLogger(__name__)


class NotificationsService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def send(
        self,
        recipient_user_id: str,
        notification_type: str,
        channel: str,
        title: str,
        message: str,
        reference: Optional[dict] = None,
    ) -> dict:
        """
        Persist a notification document.
        Actual SMS/WhatsApp/Push delivery should happen via a background worker.
        This method intentionally does not raise on failure so it never blocks
        a transactional workflow.
        """
        try:
            now = datetime.now(timezone.utc)
            doc = {
                "recipientUserId": ObjectId(recipient_user_id),
                "type": notification_type,
                "channel": channel,
                "reference": reference or {},
                "title": title,
                "message": message,
                "status": NotificationStatus.PENDING.value,
                "sentAt": None,
                "createdAt": now,
            }
            result = self.db.notifications.insert_one(doc)
            doc["_id"] = result.inserted_id
            logger.info(
                "Notification queued type=%s channel=%s recipient=%s",
                notification_type, channel, recipient_user_id,
            )
            return doc_to_dict(doc)
        except Exception as exc:
            logger.error("Failed to queue notification: %s", exc)
            return {}

    def mark_sent(self, notification_id: str) -> None:
        self.db.notifications.update_one(
            {"_id": to_object_id(notification_id)},
            {"$set": {"status": NotificationStatus.SENT.value, "sentAt": datetime.now(timezone.utc)}},
        )

    def mark_read(self, notification_id: str, user_id: str) -> None:
        self.db.notifications.update_one(
            {"_id": to_object_id(notification_id), "recipientUserId": ObjectId(user_id)},
            {"$set": {"status": NotificationStatus.READ.value}},
        )

    def list_for_user(
        self,
        user_id: str,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> List[dict]:
        query: dict = {"recipientUserId": ObjectId(user_id)}
        if status:
            query["status"] = status
        docs = list(
            self.db.notifications.find(query)
            .sort("createdAt", -1)
            .skip(skip)
            .limit(limit)
        )
        return [doc_to_dict(d) for d in docs]
