"""
TAILOR24 — Garment Transition Engine
Server-side validation of garment workflow transitions.
This is the authoritative source of allowed stage progression.
"""
from __future__ import annotations

from app.common.enums import (
    GarmentStage,
    UserRole,
    VALID_TRANSITIONS,
    STAGE_ACTOR_ROLES,
)
from app.common.exceptions import AuthorizationError, InvalidTransitionError


def validate_transition(
    current_stage: GarmentStage,
    next_stage: GarmentStage,
    actor_role: UserRole,
) -> None:
    """
    Raise InvalidTransitionError or AuthorizationError if the transition is not allowed.
    Does NOT mutate any state — pure validation only.
    """
    allowed_next = VALID_TRANSITIONS.get(current_stage, set())
    if next_stage not in allowed_next:
        raise InvalidTransitionError(
            f"Cannot transition garment from {current_stage.value!r} "
            f"to {next_stage.value!r}. "
            f"Allowed next stages: {[s.value for s in allowed_next]}",
        )
    allowed_roles = STAGE_ACTOR_ROLES.get(next_stage, set())
    if actor_role not in allowed_roles:
        raise AuthorizationError(
            f"Role {actor_role.value!r} is not allowed to perform "
            f"stage {next_stage.value!r} transitions. "
            f"Required roles: {[r.value for r in allowed_roles]}",
        )


def get_current_stage_from_events(events: list[dict]) -> GarmentStage | None:
    """
    Derive the current garment stage from the ordered event log.
    Events should be sorted by occurredAt ascending.
    Returns None if no events exist.
    """
    if not events:
        return None
    latest = events[-1]
    stage_value = latest.get("stage") or latest.get("eventType")
    try:
        return GarmentStage(stage_value)
    except ValueError:
        return None
