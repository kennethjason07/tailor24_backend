"""
Garments router — includes the critical scan API.
IMPORTANT: There is NO PATCH /garments/{id} endpoint that accepts a raw status field.
All workflow progression happens exclusively through POST /garments/{id}/scan.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from app.common.responses import ok
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_hub_ops
from app.modules.garments.qr_service import generate_qr_image_bytes
from app.modules.garments.service import GarmentsService
from app.modules.orders.schemas import GarmentScanRequest

router = APIRouter()


def get_svc():
    return GarmentsService(get_db())


@router.get("", summary="List garments")
def list_garments(
    hub_id: str = Query(None),
    stage: str = Query(None),
    order_id: str = Query(None),
    tailor_id: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    svc: GarmentsService = Depends(get_svc),
):
    role = current_user.get("role")
    if role == "HUB_MANAGER":
        db = get_db()
        from bson import ObjectId
        hub = db.hubs.find_one({"managerUserId": ObjectId(str(current_user["_id"]))})
        if hub:
            hub_id = str(hub["_id"])

    skip = (page - 1) * page_size
    garments = svc.list_garments(
        hub_id=hub_id,
        stage=stage,
        order_id=order_id,
        tailor_id=tailor_id,
        skip=skip,
        limit=page_size,
    )
    return ok(data=garments)


@router.get("/{garment_id}", summary="Get garment by ID")
def get_garment(
    garment_id: str,
    _: dict = Depends(get_current_user),
    svc: GarmentsService = Depends(get_svc),
):
    g = svc.get_garment(garment_id)
    from app.common.utils import doc_to_dict
    return ok(data=doc_to_dict(g))


@router.get("/{garment_id}/events", summary="Get garment event history")
def get_events(
    garment_id: str,
    _: dict = Depends(get_current_user),
    svc: GarmentsService = Depends(get_svc),
):
    events = svc.get_event_history(garment_id)
    return ok(data=events)


@router.get("/qr/{qr_code}", summary="Look up garment by QR value")
def get_by_qr(
    qr_code: str,
    _: dict = Depends(get_current_user),
    svc: GarmentsService = Depends(get_svc),
):
    from app.common.utils import doc_to_dict
    g = svc.get_garment_by_qr(qr_code)
    return ok(data=doc_to_dict(g))



@router.get("/{garment_id}/qr-image", summary="Generate QR image PNG")
def get_qr_image(
    garment_id: str,
    _: dict = Depends(require_hub_ops),
    svc: GarmentsService = Depends(get_svc),
):
    """
    Generates a QR image on-the-fly.
    The PNG is NOT stored in MongoDB — it is generated from the garment's stable qrCode value.
    In production, serve from object storage or cache.
    """
    g = svc.get_garment(garment_id)
    from app.common.utils import doc_to_dict
    gd = doc_to_dict(g)
    qr_value = gd["qrCode"]
    png_bytes = generate_qr_image_bytes(qr_value)
    return Response(content=png_bytes, media_type="image/png")


@router.post("/{garment_id}/scan", summary="Scan garment QR to advance workflow")
def scan_garment(
    garment_id: str,
    body: GarmentScanRequest,
    current_user: dict = Depends(get_current_user),
    svc: GarmentsService = Depends(get_svc),
):
    """
    **The central workflow endpoint.**

    Advancing a garment always goes through this endpoint.
    There is deliberately no PATCH endpoint that accepts a raw `status` field.

    The backend:
    1. Authenticates the actor
    2. Loads the garment
    3. Derives current stage from the event log
    4. Validates actor role for this transition
    5. Validates the transition is allowed
    6. Creates an immutable garment event
    7. Updates the projection cache
    8. Creates payout on delivery (idempotent)
    9. Returns the new derived state
    """
    target_stage = body.action or body.targetStage or body.target_stage or ""
    result = svc.process_scan(
        garment_id=garment_id,
        target_stage_str=target_stage,
        actor_user=current_user,
        hub_id_override=body.hubId,
        metadata=body.metadata,
    )
    return ok(data=result, message=f"Garment advanced to {result['currentStage']}")
