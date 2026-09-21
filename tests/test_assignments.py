"""Tests: smart assignment, capacity, ON_LEAVE guard, scoring."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from bson import ObjectId

from app.common.enums import TailorAvailability
from app.common.exceptions import CapacityExceededError, TailorUnavailableError
from app.modules.assignments.service import AssignmentsService, _compute_score


class TestScoringAlgorithm:
    def test_gender_match_scores(self):
        profile = {
            "genderSpecialization": ["LADIES"],
            "skills": ["KURTA"],
            "dailyCapacity": 10,
            "assignedToday": 0,
            "rating": 5.0,
        }
        score, breakdown = _compute_score(profile, "KURTA", "LADIES")
        assert breakdown["genderMatch"] == 40
        assert breakdown["skillMatch"] == 25
        assert score > 0

    def test_no_gender_match(self):
        profile = {
            "genderSpecialization": ["GENTS"],
            "skills": ["SHIRT"],
            "dailyCapacity": 10,
            "assignedToday": 0,
            "rating": 5.0,
        }
        _, breakdown = _compute_score(profile, "SHIRT", "LADIES")
        assert breakdown["genderMatch"] == 0

    def test_unisex_matches_any_gender(self):
        profile = {
            "genderSpecialization": ["UNISEX"],
            "skills": ["SHIRT"],
            "dailyCapacity": 10,
            "assignedToday": 0,
            "rating": 5.0,
        }
        _, breakdown = _compute_score(profile, "SHIRT", "LADIES")
        assert breakdown["genderMatch"] == 40

    def test_skill_mismatch_zero_score(self):
        profile = {
            "genderSpecialization": ["GENTS"],
            "skills": ["SHIRT"],
            "dailyCapacity": 10,
            "assignedToday": 0,
            "rating": 5.0,
        }
        _, breakdown = _compute_score(profile, "KURTA", "GENTS")
        assert breakdown["skillMatch"] == 0

    def test_capacity_headroom_proportional(self):
        profile = {
            "genderSpecialization": ["GENTS"],
            "skills": ["SHIRT"],
            "dailyCapacity": 10,
            "assignedToday": 5,  # 50% used
            "rating": 5.0,
        }
        _, breakdown = _compute_score(profile, "SHIRT", "GENTS")
        expected = 10 * 0.5  # 50% headroom × weight 10 = 5
        assert abs(breakdown["capacityHeadroom"] - expected) < 0.01

    def test_full_capacity_zero_headroom(self):
        profile = {
            "genderSpecialization": ["GENTS"],
            "skills": ["SHIRT"],
            "dailyCapacity": 10,
            "assignedToday": 10,  # full
            "rating": 5.0,
        }
        _, breakdown = _compute_score(profile, "SHIRT", "GENTS")
        assert breakdown["capacityHeadroom"] == 0

    def test_rating_is_tiebreaker_only(self):
        """Rating contribution is small (fractional) so it never dominates score."""
        profile = {
            "genderSpecialization": [],
            "skills": [],
            "dailyCapacity": 10,
            "assignedToday": 0,
            "rating": 5.0,
        }
        score, breakdown = _compute_score(profile, "SHIRT", "GENTS")
        assert breakdown["ratingTieBreaker"] < 1.0  # never dominates


class TestAssignmentService:
    def _make_svc(self, db_mock):
        svc = AssignmentsService.__new__(AssignmentsService)
        svc.db = db_mock
        return svc

    def test_on_leave_tailor_cannot_be_assigned(self, db):
        """Assigning a tailor who is ON_LEAVE raises TailorUnavailableError."""
        svc = AssignmentsService(db)

        # Create garment
        now = datetime.now(timezone.utc)
        from app.common.utils import money_to_decimal128
        from decimal import Decimal
        hub_id = ObjectId()
        order_id = ObjectId()
        garment_doc = {
            "orderId": order_id,
            "customerId": ObjectId(),
            "hubId": hub_id,
            "qrCode": "GRT-T24-000099999",
            "type": "SHIRT",
            "gender": "GENTS",
            "serviceCharge": money_to_decimal128(Decimal("250")),
            "measurements": {},
            "tailorId": None,
            "currentStage": "CUTTING_COMPLETED",
            "sla": None,
            "intake": None,
            "createdAt": now,
            "updatedAt": now,
            "garmentNumber": "GRM-T24-000099999",
        }
        g_result = db.garments.insert_one(garment_doc)

        # Create ON_LEAVE tailor profile
        tailor_user_id = ObjectId()
        profile_doc = {
            "userId": tailor_user_id,
            "hubId": hub_id,
            "genderSpecialization": ["GENTS"],
            "skills": ["SHIRT"],
            "dailyCapacity": 10,
            "assignedToday": 0,
            "availability": TailorAvailability.ON_LEAVE.value,
            "rating": 4.5,
            "isActive": True,
            "createdAt": now,
            "updatedAt": now,
        }
        p_result = db.tailor_profiles.insert_one(profile_doc)

        manager_user = {"_id": ObjectId(), "role": "HUB_MANAGER", "name": "Mgr"}

        with pytest.raises(TailorUnavailableError):
            svc.assign_tailor(
                garment_id=str(g_result.inserted_id),
                tailor_profile_id=str(p_result.inserted_id),
                assigned_by_user=manager_user,
            )

    def test_capacity_exceeded_raises_error(self, db):
        """Assigning beyond dailyCapacity raises CapacityExceededError."""
        svc = AssignmentsService(db)
        now = datetime.now(timezone.utc)
        from app.common.utils import money_to_decimal128
        from decimal import Decimal

        hub_id = ObjectId()
        garment_doc = {
            "orderId": ObjectId(),
            "customerId": ObjectId(),
            "hubId": hub_id,
            "qrCode": "GRT-T24-000098888",
            "type": "SHIRT",
            "gender": "GENTS",
            "serviceCharge": money_to_decimal128(Decimal("250")),
            "measurements": {},
            "tailorId": None,
            "currentStage": "CUTTING_COMPLETED",
            "sla": None,
            "intake": None,
            "createdAt": now,
            "updatedAt": now,
            "garmentNumber": "GRM-T24-000098888",
        }
        g_result = db.garments.insert_one(garment_doc)

        profile_doc = {
            "userId": ObjectId(),
            "hubId": hub_id,
            "genderSpecialization": ["GENTS"],
            "skills": ["SHIRT"],
            "dailyCapacity": 5,
            "assignedToday": 5,  # at capacity
            "availability": TailorAvailability.AVAILABLE.value,
            "rating": 4.5,
            "isActive": True,
            "createdAt": now,
            "updatedAt": now,
        }
        p_result = db.tailor_profiles.insert_one(profile_doc)

        manager_user = {"_id": ObjectId(), "role": "HUB_MANAGER", "name": "Mgr"}

        with pytest.raises(CapacityExceededError):
            svc.assign_tailor(
                garment_id=str(g_result.inserted_id),
                tailor_profile_id=str(p_result.inserted_id),
                assigned_by_user=manager_user,
                override_capacity=False,
            )

    def test_capacity_override_works(self, db):
        """With override_capacity=True, assignment succeeds even at full capacity."""
        svc = AssignmentsService(db)
        now = datetime.now(timezone.utc)
        from app.common.utils import money_to_decimal128
        from decimal import Decimal

        hub_id = ObjectId()
        garment_doc = {
            "orderId": ObjectId(),
            "customerId": ObjectId(),
            "hubId": hub_id,
            "qrCode": "GRT-T24-000097777",
            "type": "SHIRT",
            "gender": "GENTS",
            "serviceCharge": money_to_decimal128(Decimal("250")),
            "measurements": {},
            "tailorId": None,
            "currentStage": "CUTTING_COMPLETED",
            "sla": None,
            "intake": None,
            "createdAt": now,
            "updatedAt": now,
            "garmentNumber": "GRM-T24-000097777",
        }
        g_result = db.garments.insert_one(garment_doc)

        user_id = ObjectId()
        db.users.insert_one({"_id": user_id, "name": "Override Tailor", "phone": "+910000099777", "role": "TAILOR"})
        profile_doc = {
            "userId": user_id,
            "hubId": hub_id,
            "genderSpecialization": ["GENTS"],
            "skills": ["SHIRT"],
            "dailyCapacity": 5,
            "assignedToday": 5,
            "availability": TailorAvailability.AVAILABLE.value,
            "rating": 4.5,
            "isActive": True,
            "createdAt": now,
            "updatedAt": now,
        }
        p_result = db.tailor_profiles.insert_one(profile_doc)
        manager_user = {"_id": ObjectId(), "role": "HUB_MANAGER", "name": "Mgr"}

        assignment = svc.assign_tailor(
            garment_id=str(g_result.inserted_id),
            tailor_profile_id=str(p_result.inserted_id),
            assigned_by_user=manager_user,
            override_capacity=True,
        )
        assert assignment["status"] == "ACTIVE"
