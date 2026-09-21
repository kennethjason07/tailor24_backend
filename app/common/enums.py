"""
TAILOR24 Backend — All Domain Enumerations
These are the canonical constants for the entire platform.
"""
from __future__ import annotations

from enum import Enum


# ── User Roles ────────────────────────────────────────────────────────────────
class UserRole(str, Enum):
    CUSTOMER = "CUSTOMER"
    TAILOR = "TAILOR"
    HUB_STAFF = "HUB_STAFF"
    HUB_MANAGER = "HUB_MANAGER"
    RIDER = "RIDER"
    ADMIN_FINANCE = "ADMIN_FINANCE"


# ── Garment Categories ───────────────────────────────────────────────────────
class GarmentType(str, Enum):
    SHIRT = "SHIRT"
    TROUSER = "TROUSER"
    KURTA = "KURTA"
    SUIT = "SUIT"
    SAREE = "SAREE"
    DRESS = "DRESS"
    OTHER = "OTHER"


# ── Gender Categories ─────────────────────────────────────────────────────────
class GenderCategory(str, Enum):
    LADIES = "LADIES"
    GENTS = "GENTS"
    KIDS = "KIDS"
    UNISEX = "UNISEX"


# ── Garment Workflow Stages ───────────────────────────────────────────────────
class GarmentStage(str, Enum):
    INTAKE = "INTAKE"
    CUTTING_STARTED = "CUTTING_STARTED"
    CUTTING_COMPLETED = "CUTTING_COMPLETED"
    STITCHING_ASSIGNED = "STITCHING_ASSIGNED"
    STITCHING_STARTED = "STITCHING_STARTED"
    STITCHING_COMPLETED = "STITCHING_COMPLETED"
    QC_STARTED = "QC_STARTED"
    QC_PASSED = "QC_PASSED"
    QC_REWORK = "QC_REWORK"
    IRONING_STARTED = "IRONING_STARTED"
    IRONING_COMPLETED = "IRONING_COMPLETED"
    PACKED = "PACKED"
    DISPATCHED = "DISPATCHED"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    DELIVERY_FAILED = "DELIVERY_FAILED"


# ── Garment Event Types (mirrors stages + system events) ─────────────────────
class GarmentEventType(str, Enum):
    INTAKE = "INTAKE"
    CUTTING_STARTED = "CUTTING_STARTED"
    CUTTING_COMPLETED = "CUTTING_COMPLETED"
    STITCHING_ASSIGNED = "STITCHING_ASSIGNED"
    STITCHING_STARTED = "STITCHING_STARTED"
    STITCHING_COMPLETED = "STITCHING_COMPLETED"
    QC_STARTED = "QC_STARTED"
    QC_PASSED = "QC_PASSED"
    QC_REWORK = "QC_REWORK"
    IRONING_STARTED = "IRONING_STARTED"
    IRONING_COMPLETED = "IRONING_COMPLETED"
    PACKED = "PACKED"
    DISPATCHED = "DISPATCHED"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    DELIVERY_FAILED = "DELIVERY_FAILED"


# Valid garment stage transitions
# Maps current stage → set of allowed next stages
VALID_TRANSITIONS: dict[GarmentStage, set[GarmentStage]] = {
    GarmentStage.INTAKE: {GarmentStage.CUTTING_STARTED},
    GarmentStage.CUTTING_STARTED: {GarmentStage.CUTTING_COMPLETED},
    GarmentStage.CUTTING_COMPLETED: {GarmentStage.STITCHING_ASSIGNED},
    GarmentStage.STITCHING_ASSIGNED: {GarmentStage.STITCHING_STARTED},
    GarmentStage.STITCHING_STARTED: {GarmentStage.STITCHING_COMPLETED},
    GarmentStage.STITCHING_COMPLETED: {GarmentStage.QC_STARTED},
    GarmentStage.QC_STARTED: {GarmentStage.QC_PASSED, GarmentStage.QC_REWORK},
    GarmentStage.QC_PASSED: {GarmentStage.IRONING_STARTED},
    GarmentStage.QC_REWORK: {GarmentStage.STITCHING_STARTED},  # rework loop
    GarmentStage.IRONING_STARTED: {GarmentStage.IRONING_COMPLETED},
    GarmentStage.IRONING_COMPLETED: {GarmentStage.PACKED},
    GarmentStage.PACKED: {GarmentStage.DISPATCHED},
    GarmentStage.DISPATCHED: {GarmentStage.OUT_FOR_DELIVERY},
    GarmentStage.OUT_FOR_DELIVERY: {GarmentStage.DELIVERED, GarmentStage.DELIVERY_FAILED},
    GarmentStage.DELIVERED: set(),        # terminal
    GarmentStage.DELIVERY_FAILED: {GarmentStage.OUT_FOR_DELIVERY},  # retry
}

# Stages that require specific roles to advance
STAGE_ACTOR_ROLES: dict[GarmentStage, set[UserRole]] = {
    GarmentStage.INTAKE: {UserRole.HUB_STAFF, UserRole.HUB_MANAGER},
    GarmentStage.CUTTING_STARTED: {UserRole.HUB_STAFF, UserRole.HUB_MANAGER},
    GarmentStage.CUTTING_COMPLETED: {UserRole.HUB_STAFF, UserRole.HUB_MANAGER},
    GarmentStage.STITCHING_ASSIGNED: {UserRole.HUB_MANAGER},
    GarmentStage.STITCHING_STARTED: {UserRole.TAILOR, UserRole.HUB_STAFF, UserRole.HUB_MANAGER},
    GarmentStage.STITCHING_COMPLETED: {UserRole.TAILOR, UserRole.HUB_STAFF, UserRole.HUB_MANAGER},
    GarmentStage.QC_STARTED: {UserRole.HUB_STAFF, UserRole.HUB_MANAGER},
    GarmentStage.QC_PASSED: {UserRole.HUB_STAFF, UserRole.HUB_MANAGER},
    GarmentStage.QC_REWORK: {UserRole.HUB_STAFF, UserRole.HUB_MANAGER},
    GarmentStage.IRONING_STARTED: {UserRole.HUB_STAFF, UserRole.HUB_MANAGER},
    GarmentStage.IRONING_COMPLETED: {UserRole.HUB_STAFF, UserRole.HUB_MANAGER},
    GarmentStage.PACKED: {UserRole.HUB_STAFF, UserRole.HUB_MANAGER},
    GarmentStage.DISPATCHED: {UserRole.HUB_STAFF, UserRole.HUB_MANAGER},
    GarmentStage.OUT_FOR_DELIVERY: {UserRole.RIDER, UserRole.HUB_STAFF, UserRole.HUB_MANAGER},
    GarmentStage.DELIVERED: {UserRole.RIDER},
    GarmentStage.DELIVERY_FAILED: {UserRole.RIDER},
}


# ── Order Payment ─────────────────────────────────────────────────────────────
class PaymentMethod(str, Enum):
    ONLINE = "ONLINE"
    COD = "COD"


class PaymentStatus(str, Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


# ── Tailor Availability ───────────────────────────────────────────────────────
class TailorAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    BUSY = "BUSY"
    ON_LEAVE = "ON_LEAVE"


# ── Tailor Application Status ─────────────────────────────────────────────────
class ApplicationStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


# ── Leave Request Status ──────────────────────────────────────────────────────
class LeaveStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


# ── Assignment Type ───────────────────────────────────────────────────────────
class AssignmentType(str, Enum):
    SMART = "SMART"
    MANUAL = "MANUAL"


class AssignmentStatus(str, Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    REASSIGNED = "REASSIGNED"


# ── Payout Ledger Status ──────────────────────────────────────────────────────
class PayoutLedgerStatus(str, Enum):
    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    PAID = "PAID"
    DISPUTED = "DISPUTED"


# ── Payout Claim Status ───────────────────────────────────────────────────────
class PayoutClaimStatus(str, Enum):
    PENDING_MANAGER = "PENDING_MANAGER"
    MANAGER_APPROVED = "MANAGER_APPROVED"
    MANAGER_REJECTED = "MANAGER_REJECTED"
    FINANCE_PAID = "FINANCE_PAID"
    FINANCE_REJECTED = "FINANCE_REJECTED"


# ── Delivery Status ───────────────────────────────────────────────────────────
class DeliveryStatus(str, Enum):
    ASSIGNED = "ASSIGNED"
    PICKED_UP = "PICKED_UP"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"


# ── Notification ─────────────────────────────────────────────────────────────
class NotificationChannel(str, Enum):
    SMS = "SMS"
    WHATSAPP = "WHATSAPP"
    PUSH = "PUSH"
    EMAIL = "EMAIL"


class NotificationStatus(str, Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    READ = "READ"


# ── SLA Status ────────────────────────────────────────────────────────────────
class SLAStatus(str, Enum):
    ON_TIME = "ON_TIME"
    AT_RISK = "AT_RISK"
    OVERDUE = "OVERDUE"
