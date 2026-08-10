from fastapi import APIRouter, Depends

from .. import db
from ..auth import Permission, require


router = APIRouter(
    prefix="/audit",
    tags=["audit"],
    dependencies=[Depends(require(Permission.AUDIT_READ))],
)


@router.get("/events")
async def audit_events(limit: int = 100, before_sequence: int | None = None):
    return await db.list_audit_events(limit, before_sequence)


@router.get("/verify")
async def verify_audit_events():
    return await db.verify_audit_chain()
