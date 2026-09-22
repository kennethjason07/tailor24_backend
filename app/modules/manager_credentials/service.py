"""Service logic for Hub Manager Credential Management."""
from __future__ import annotations

import secrets
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from bson import ObjectId
from pymongo.database import Database

from app.common.exceptions import ConflictError, NotFoundError, AuthorizationError, BadRequestError
from app.common.utils import doc_to_dict, to_object_id
from app.core.security import hash_password

logger = logging.getLogger(__name__)

FORBIDDEN_ROLES = {"SUPER_ADMIN", "ADMIN_FINANCE", "HUB_MANAGER"}
ALLOWED_ROLES = {"RIDER", "HUB_STAFF", "TAILOR"}


class ManagerCredentialsService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def _generate_token_and_expiry(self, hours: int = 24) -> tuple[str, datetime]:
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=hours)
        return token, expires_at

    def log_audit_event(
        self,
        actor_user: dict,
        target_user_id: str,
        target_role: str,
        action: str,
        metadata: Optional[dict] = None,
    ) -> dict:
        now = datetime.now(timezone.utc)
        doc = {
            "actorUserId": str(actor_user.get("_id", actor_user.get("id", ""))),
            "actorRole": str(actor_user.get("role", "")),
            "targetUserId": str(target_user_id),
            "targetRole": str(target_role),
            "hubId": str(actor_user.get("hubId", "")),
            "action": action,
            "timestamp": now,
            "metadata": metadata or {},
        }
        res = self.db.audit_logs.insert_one(doc)
        doc["_id"] = res.inserted_id
        return doc_to_dict(doc)

    def _validate_manager_hub(self, manager: dict) -> str:
        # Super admin bypass or derive hubId
        hub_id = manager.get("hubId")
        if not hub_id and manager.get("role") != "SUPER_ADMIN":
            raise AuthorizationError("Hub Manager is not assigned to any physical hub.")
        return str(hub_id) if hub_id else ""

    def _verify_target_user_hub(self, manager: dict, target_user: dict) -> None:
        manager_hub = manager.get("hubId")
        if manager.get("role") == "SUPER_ADMIN":
            return
        if not manager_hub or str(target_user.get("hubId", "")) != str(manager_hub):
            raise AuthorizationError("You are not authorized to manage users from another hub.")

    def _check_phone_and_email_exists(self, phone: str, email: Optional[str] = None) -> None:
        if self.db.users.find_one({"phone": phone}):
            raise ConflictError("An account already exists with this mobile number.")
        if email and self.db.users.find_one({"email": email}):
            raise ConflictError("An account already exists with this email address.")

    # ── RIDERS ─────────────────────────────────────────────────────────────

    def create_rider(
        self,
        manager: dict,
        name: str,
        phone: str,
        email: Optional[str] = None,
        password: Optional[str] = None,
        emergency_contact: Optional[str] = None,
        address: Optional[str] = None,
    ) -> dict:
        hub_id = self._validate_manager_hub(manager)
        self._check_phone_and_email_exists(phone, email)

        token, expires_at = self._generate_token_and_expiry(24)
        now = datetime.now(timezone.utc)

        doc = {
            "name": name,
            "phone": phone,
            "email": email,
            "role": "RIDER",
            "hubId": hub_id,
            "isActive": True,
            "emergencyContact": emergency_contact,
            "address": address,
            "createdBy": str(manager.get("_id", manager.get("id"))),
            "createdAt": now,
            "updatedAt": now,
        }

        if password and len(password.strip()) >= 6:
            doc["passwordHash"] = hash_password(password.strip())
            doc["accountStatus"] = "ACTIVE"
        else:
            doc["accountStatus"] = "PENDING_ACTIVATION"
            doc["activationToken"] = token
            doc["activationExpiresAt"] = expires_at

        res = self.db.users.insert_one(doc)
        user_id = str(res.inserted_id)
        doc["_id"] = res.inserted_id

        self.log_audit_event(
            actor_user=manager,
            target_user_id=user_id,
            target_role="RIDER",
            action="USER_CREATED",
            metadata={"name": name, "phone": phone, "hubId": hub_id, "hasDirectPassword": bool(password)},
        )

        resp = doc_to_dict(doc)
        resp["userId"] = user_id
        if doc.get("activationToken"):
            resp["activationLink"] = f"/auth/activate?token={token}"
            resp["activationExpiresAt"] = expires_at.isoformat()
        resp.pop("passwordHash", None)
        return resp

    def list_riders(
        self,
        manager: dict,
        search: Optional[str] = None,
        status: Optional[str] = None,
        account_status: Optional[str] = None,
    ) -> List[dict]:
        hub_id = self._validate_manager_hub(manager)
        query: Dict[str, Any] = {"role": "RIDER"}
        if manager.get("role") != "SUPER_ADMIN":
            query["hubId"] = hub_id

        if search:
            query["$or"] = [
                {"name": {"$regex": search, "$options": "i"}},
                {"phone": {"$regex": search, "$options": "i"}},
            ]
        if account_status:
            query["accountStatus"] = account_status

        users = list(self.db.users.find(query).sort("createdAt", -1))
        results = []
        for u in users:
            d = doc_to_dict(u)
            d["userId"] = d.get("id", str(u["_id"]))
            d.pop("passwordHash", None)
            d.pop("activationToken", None)
            
            # Fetch operational stats if available
            deliveries = list(self.db.deliveries.find({"riderId": d["userId"]}))
            d["activeDeliveries"] = len([deliv for deliv in deliveries if deliv.get("status") in ["ASSIGNED", "OUT_FOR_DELIVERY"]])
            d["deliveriesToday"] = len([deliv for deliv in deliveries if deliv.get("deliveredAt") and str(deliv.get("deliveredAt"))[:10] == str(datetime.now(timezone.utc))[:10]])
            d["availabilityStatus"] = d.get("availabilityStatus", "AVAILABLE" if d.get("isActive") else "INACTIVE")
            
            if status and d["availabilityStatus"].upper() != status.upper():
                continue

            results.append(d)
        return results

    # ── WORKERS ────────────────────────────────────────────────────────────

    def create_worker(
        self,
        manager: dict,
        name: str,
        phone: str,
        email: Optional[str] = None,
        password: Optional[str] = None,
        role: str = "HUB_STAFF",
    ) -> dict:
        if role in FORBIDDEN_ROLES:
            raise AuthorizationError(f"Hub Manager is not permitted to create role {role}.")
        if role != "HUB_STAFF":
            raise BadRequestError("Only HUB_STAFF role is currently supported for operational hub workers.")

        hub_id = self._validate_manager_hub(manager)
        self._check_phone_and_email_exists(phone, email)

        token, expires_at = self._generate_token_and_expiry(24)
        now = datetime.now(timezone.utc)

        doc = {
            "name": name,
            "phone": phone,
            "email": email,
            "role": "HUB_STAFF",
            "hubId": hub_id,
            "isActive": True,
            "createdBy": str(manager.get("_id", manager.get("id"))),
            "createdAt": now,
            "updatedAt": now,
        }

        if password and len(password.strip()) >= 6:
            doc["passwordHash"] = hash_password(password.strip())
            doc["accountStatus"] = "ACTIVE"
        else:
            doc["accountStatus"] = "PENDING_ACTIVATION"
            doc["activationToken"] = token
            doc["activationExpiresAt"] = expires_at

        res = self.db.users.insert_one(doc)
        user_id = str(res.inserted_id)
        doc["_id"] = res.inserted_id

        self.log_audit_event(
            actor_user=manager,
            target_user_id=user_id,
            target_role="HUB_STAFF",
            action="USER_CREATED",
            metadata={"name": name, "phone": phone, "hubId": hub_id, "hasDirectPassword": bool(password)},
        )

        resp = doc_to_dict(doc)
        resp["userId"] = user_id
        if doc.get("activationToken"):
            resp["activationLink"] = f"/auth/activate?token={token}"
            resp["activationExpiresAt"] = expires_at.isoformat()
        resp.pop("passwordHash", None)
        return resp


    def list_workers(
        self,
        manager: dict,
        search: Optional[str] = None,
        account_status: Optional[str] = None,
    ) -> List[dict]:
        hub_id = self._validate_manager_hub(manager)
        query: Dict[str, Any] = {"role": "HUB_STAFF"}
        if manager.get("role") != "SUPER_ADMIN":
            query["hubId"] = hub_id

        if search:
            query["$or"] = [
                {"name": {"$regex": search, "$options": "i"}},
                {"phone": {"$regex": search, "$options": "i"}},
            ]
        if account_status:
            query["accountStatus"] = account_status

        users = list(self.db.users.find(query).sort("createdAt", -1))
        results = []
        for u in users:
            d = doc_to_dict(u)
            d["userId"] = d.get("id", str(u["_id"]))
            d.pop("passwordHash", None)
            d.pop("activationToken", None)
            results.append(d)
        return results

    # ── TAILORS ────────────────────────────────────────────────────────────

    def create_tailor_direct(
        self,
        manager: dict,
        name: str,
        phone: str,
        email: Optional[str] = None,
        password: Optional[str] = None,
        skills: Optional[List[str]] = None,
        gender_specialization: Optional[List[str]] = None,
    ) -> dict:
        hub_id = self._validate_manager_hub(manager)
        self._check_phone_and_email_exists(phone, email)

        token, expires_at = self._generate_token_and_expiry(24)
        now = datetime.now(timezone.utc)

        user_doc = {
            "name": name,
            "phone": phone,
            "email": email,
            "role": "TAILOR",
            "hubId": hub_id,
            "isActive": True,
            "createdBy": str(manager.get("_id", manager.get("id"))),
            "createdAt": now,
            "updatedAt": now,
        }

        if password and len(password.strip()) >= 6:
            user_doc["passwordHash"] = hash_password(password.strip())
            user_doc["accountStatus"] = "ACTIVE"
        else:
            user_doc["accountStatus"] = "PENDING_ACTIVATION"
            user_doc["activationToken"] = token
            user_doc["activationExpiresAt"] = expires_at

        res = self.db.users.insert_one(user_doc)
        user_id = str(res.inserted_id)
        user_doc["_id"] = res.inserted_id

        t_skills = skills or ["Kurtis", "Blouses"]
        t_gender = gender_specialization or ["LADIES"]

        profile_doc = {
            "userId": user_id,
            "hubId": hub_id,
            "name": name,
            "phone": phone,
            "skills": t_skills,
            "genderSpecialization": t_gender,
            "dailyCapacity": 50,
            "availabilityStatus": "AVAILABLE",
            "rating": 5.0,
            "createdAt": now,
            "updatedAt": now,
        }
        self.db.tailor_profiles.update_one(
            {"userId": user_id},
            {"$set": profile_doc},
            upsert=True,
        )

        self.log_audit_event(
            actor_user=manager,
            target_user_id=user_id,
            target_role="TAILOR",
            action="USER_CREATED",
            metadata={"name": name, "phone": phone, "hubId": hub_id, "hasDirectPassword": bool(password)},
        )

        resp = doc_to_dict(user_doc)
        resp["userId"] = user_id
        resp["skills"] = profile_doc["skills"]
        resp["genderSpecialization"] = profile_doc["genderSpecialization"]
        resp["dailyCapacity"] = 50
        resp["availabilityStatus"] = "AVAILABLE"
        if user_doc.get("activationToken"):
            resp["activationLink"] = f"/auth/activate?token={token}"
            resp["activationExpiresAt"] = expires_at.isoformat()
        resp.pop("passwordHash", None)
        return resp

    def create_tailor_account_from_application(

        self,
        manager: dict,
        application_id: str,
        password: Optional[str] = None,
    ) -> dict:
        hub_id = self._validate_manager_hub(manager)
        
        # Check application
        app_doc = self.db.tailor_applications.find_one({"_id": to_object_id(application_id)})
        if not app_doc:
            # Check applications collection fallback
            app_doc = self.db.applications.find_one({"_id": to_object_id(application_id)})
        if not app_doc:
            raise NotFoundError(f"Tailor application {application_id} not found.")

        app_status = str(app_doc.get("status", "")).upper()
        if app_status != "APPROVED":
            raise AuthorizationError("Tailor account can only be created from an APPROVED application.")

        phone = app_doc.get("phone")
        name = app_doc.get("applicantName") or app_doc.get("name") or "Tailor"
        email = app_doc.get("email")

        self._check_phone_and_email_exists(phone, email)

        token, expires_at = self._generate_token_and_expiry(24)
        now = datetime.now(timezone.utc)

        user_doc = {
            "name": name,
            "phone": phone,
            "email": email,
            "role": "TAILOR",
            "hubId": hub_id,
            "isActive": True,
            "createdBy": str(manager.get("_id", manager.get("id"))),
            "createdAt": now,
            "updatedAt": now,
        }

        if password and len(password.strip()) >= 6:
            user_doc["passwordHash"] = hash_password(password.strip())
            user_doc["accountStatus"] = "ACTIVE"
        else:
            user_doc["accountStatus"] = "PENDING_ACTIVATION"
            user_doc["activationToken"] = token
            user_doc["activationExpiresAt"] = expires_at

        res = self.db.users.insert_one(user_doc)
        user_id = str(res.inserted_id)
        user_doc["_id"] = res.inserted_id

        # Profile doc
        skills = app_doc.get("skills", ["Kurtis", "Blouses"])
        gender_spec = app_doc.get("genderSpecialization") or app_doc.get("gender_specialization") or ["LADIES"]
        capacity = app_doc.get("capacity", 50)

        profile_doc = {
            "userId": user_id,
            "hubId": hub_id,
            "name": name,
            "phone": phone,
            "skills": skills if isinstance(skills, list) else [skills],
            "genderSpecialization": gender_spec if isinstance(gender_spec, list) else [gender_spec],
            "dailyCapacity": capacity,
            "availabilityStatus": "AVAILABLE",
            "rating": 5.0,
            "applicationId": application_id,
            "createdAt": now,
            "updatedAt": now,
        }
        self.db.tailor_profiles.update_one(
            {"userId": user_id},
            {"$set": profile_doc},
            upsert=True,
        )

        # Update application doc
        self.db.tailor_applications.update_one(
            {"_id": to_object_id(application_id)},
            {"$set": {"accountCreated": True, "userId": user_id}},
        )

        self.log_audit_event(
            actor_user=manager,
            target_user_id=user_id,
            target_role="TAILOR",
            action="USER_CREATED",
            metadata={"applicationId": application_id, "name": name, "phone": phone, "hubId": hub_id, "hasDirectPassword": bool(password)},
        )

        resp = doc_to_dict(user_doc)
        resp["userId"] = user_id
        resp["skills"] = profile_doc["skills"]
        resp["genderSpecialization"] = profile_doc["genderSpecialization"]
        resp["dailyCapacity"] = capacity
        resp["availabilityStatus"] = "AVAILABLE"
        if user_doc.get("activationToken"):
            resp["activationLink"] = f"/auth/activate?token={token}"
            resp["activationExpiresAt"] = expires_at.isoformat()
        resp.pop("passwordHash", None)
        return resp


    def list_tailors(
        self,
        manager: dict,
        search: Optional[str] = None,
        tab: Optional[str] = None,
    ) -> Dict[str, Any]:
        hub_id = self._validate_manager_hub(manager)

        # 1. Active Tailors
        query: Dict[str, Any] = {"role": "TAILOR"}
        if manager.get("role") != "SUPER_ADMIN":
            query["hubId"] = hub_id

        if search:
            query["$or"] = [
                {"name": {"$regex": search, "$options": "i"}},
                {"phone": {"$regex": search, "$options": "i"}},
            ]

        users = list(self.db.users.find(query).sort("createdAt", -1))
        tailors_list = []

        for u in users:
            d = doc_to_dict(u)
            uid = d.get("id", str(u["_id"]))
            d["userId"] = uid
            d.pop("passwordHash", None)
            d.pop("activationToken", None)

            prof = self.db.tailor_profiles.find_one({"userId": uid})
            if prof:
                d["skills"] = prof.get("skills", [])
                d["genderSpecialization"] = prof.get("genderSpecialization", [])
                d["dailyCapacity"] = prof.get("dailyCapacity", 50)
                d["availabilityStatus"] = prof.get("availabilityStatus", "AVAILABLE")
                d["rating"] = prof.get("rating", 5.0)

            tailors_list.append(d)

        # 2. Tailor Applications
        app_query: Dict[str, Any] = {}
        if manager.get("role") != "SUPER_ADMIN" and hub_id:
            app_query["$or"] = [{"hubId": hub_id}, {"hub_id": hub_id}, {"assignedHub": hub_id}, {"hubId": {"$exists": False}}]

        raw_apps = list(self.db.tailor_applications.find(app_query).sort("submittedAt", -1))
        if not raw_apps:
            raw_apps = list(self.db.applications.find(app_query).sort("createdAt", -1))

        applications_list = []
        for a in raw_apps:
            ad = doc_to_dict(a)
            ad["applicationId"] = ad.get("id", str(a["_id"]))
            ad["applicantName"] = ad.get("applicantName") or ad.get("name") or "Applicant"
            ad["skills"] = ad.get("skills", [])
            ad["genderSpecialization"] = ad.get("genderSpecialization") or ad.get("gender_specialization", ["LADIES"])
            ad["status"] = ad.get("status", "PENDING").upper()
            applications_list.append(ad)

        return {
            "tailors": tailors_list,
            "applications": applications_list,
        }

    # ── USER ACTIONS (RESET, DEACTIVATE, REACTIVATE, GET) ────────────────

    def get_user_detail(self, manager: dict, user_id: str, expected_role: Optional[str] = None) -> dict:
        user = self.db.users.find_one({"_id": to_object_id(user_id)})
        if not user:
            raise NotFoundError(f"User {user_id} not found.")

        self._verify_target_user_hub(manager, user)
        if expected_role and user.get("role") != expected_role:
            raise NotFoundError(f"User {user_id} with role {expected_role} not found.")

        d = doc_to_dict(user)
        d["userId"] = user_id
        d.pop("passwordHash", None)
        d.pop("activationToken", None)

        if user.get("role") == "TAILOR":
            prof = self.db.tailor_profiles.find_one({"userId": user_id})
            if prof:
                d["skills"] = prof.get("skills", [])
                d["genderSpecialization"] = prof.get("genderSpecialization", [])
                d["dailyCapacity"] = prof.get("dailyCapacity", 50)
                d["availabilityStatus"] = prof.get("availabilityStatus", "AVAILABLE")
                d["rating"] = prof.get("rating", 5.0)

        # Fetch audit log timeline
        audit_records = list(self.db.audit_logs.find({"targetUserId": user_id}).sort("timestamp", -1))
        d["auditLogs"] = [doc_to_dict(rec) for rec in audit_records]

        return d

    def reset_access(self, manager: dict, user_id: str) -> dict:
        user = self.db.users.find_one({"_id": to_object_id(user_id)})
        if not user:
            raise NotFoundError(f"User {user_id} not found.")

        self._verify_target_user_hub(manager, user)
        role = user.get("role")
        if role in FORBIDDEN_ROLES:
            raise AuthorizationError(f"Cannot reset access for user with role {role}.")

        token, expires_at = self._generate_token_and_expiry(24)
        now = datetime.now(timezone.utc)

        self.db.users.update_one(
            {"_id": to_object_id(user_id)},
            {
                "$set": {
                    "activationToken": token,
                    "activationExpiresAt": expires_at,
                    "accountStatus": "PENDING_ACTIVATION",
                    "lastCredentialResetAt": now,
                    "updatedAt": now,
                }
            },
        )

        self.log_audit_event(
            actor_user=manager,
            target_user_id=user_id,
            target_role=role,
            action="ACCESS_RESET",
            metadata={"resetAt": now.isoformat()},
        )

        return {
            "userId": user_id,
            "name": user.get("name"),
            "phone": user.get("phone"),
            "role": role,
            "accountStatus": "PENDING_ACTIVATION",
            "activationToken": token,
            "activationExpiresAt": expires_at.isoformat(),
            "activationLink": f"/auth/activate?token={token}",
        }

    def deactivate_user(self, manager: dict, user_id: str) -> dict:
        user = self.db.users.find_one({"_id": to_object_id(user_id)})
        if not user:
            raise NotFoundError(f"User {user_id} not found.")

        self._verify_target_user_hub(manager, user)
        role = user.get("role")
        if role in FORBIDDEN_ROLES:
            raise AuthorizationError(f"Cannot deactivate user with role {role}.")

        now = datetime.now(timezone.utc)
        self.db.users.update_one(
            {"_id": to_object_id(user_id)},
            {"$set": {"isActive": False, "accountStatus": "INACTIVE", "updatedAt": now}},
        )

        self.log_audit_event(
            actor_user=manager,
            target_user_id=user_id,
            target_role=role,
            action="USER_DEACTIVATED",
            metadata={"deactivatedAt": now.isoformat()},
        )

        return {"userId": user_id, "isActive": False, "accountStatus": "INACTIVE"}

    def reactivate_user(self, manager: dict, user_id: str) -> dict:
        user = self.db.users.find_one({"_id": to_object_id(user_id)})
        if not user:
            raise NotFoundError(f"User {user_id} not found.")

        self._verify_target_user_hub(manager, user)
        role = user.get("role")
        if role in FORBIDDEN_ROLES:
            raise AuthorizationError(f"Cannot reactivate user with role {role}.")

        now = datetime.now(timezone.utc)
        # Check if password exists
        has_password = bool(user.get("passwordHash"))
        status = "ACTIVE" if has_password else "PENDING_ACTIVATION"

        self.db.users.update_one(
            {"_id": to_object_id(user_id)},
            {"$set": {"isActive": True, "accountStatus": status, "updatedAt": now}},
        )

        self.log_audit_event(
            actor_user=manager,
            target_user_id=user_id,
            target_role=role,
            action="USER_REACTIVATED",
            metadata={"reactivatedAt": now.isoformat()},
        )

        return {"userId": user_id, "isActive": True, "accountStatus": status}

    # ── PUBLIC ACTIVATION ──────────────────────────────────────────────────

    def activate_account(self, activation_token: str, password: str) -> dict:
        now = datetime.now(timezone.utc)
        user = self.db.users.find_one({"activationToken": activation_token})

        if not user:
            raise NotFoundError("Invalid or expired activation token.")

        exp = user.get("activationExpiresAt")
        if exp:
            if isinstance(exp, str):
                exp = datetime.fromisoformat(exp.replace("Z", "+00:00"))
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp < now:
                raise BadRequestError("Activation token has expired. Please contact your Hub Manager for a new activation link.")

        pwd_hash = hash_password(password)
        user_id = str(user["_id"])

        self.db.users.update_one(
            {"_id": user["_id"]},
            {
                "$set": {
                    "passwordHash": pwd_hash,
                    "accountStatus": "ACTIVE",
                    "isActive": True,
                    "updatedAt": now,
                },
                "$unset": {"activationToken": "", "activationExpiresAt": ""},
            },
        )

        self.log_audit_event(
            actor_user={"_id": user_id, "role": user.get("role"), "hubId": user.get("hubId")},
            target_user_id=user_id,
            target_role=user.get("role", ""),
            action="ACCOUNT_ACTIVATED",
            metadata={"activatedAt": now.isoformat()},
        )

        return {
            "userId": user_id,
            "name": user.get("name"),
            "phone": user.get("phone"),
            "role": user.get("role"),
            "accountStatus": "ACTIVE",
            "message": "Account activated successfully. You may now log in.",
        }
