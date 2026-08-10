from fastapi import APIRouter

from .. import dashboard_service
from ..auth import CurrentPrincipal
from ..dashboard_models import DashboardOverview

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/overview")
async def overview(principal: CurrentPrincipal) -> DashboardOverview:
    return await dashboard_service.get_overview(principal)
