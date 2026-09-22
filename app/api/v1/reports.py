from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db
from app.schemas.reports import ReportResponse
from app.services.report_service import report_service

router = APIRouter(
    prefix="/reports",
    tags=["Reports"],
)


@router.get(
    "/monthly",
    response_model=ReportResponse,
)
async def get_monthly_report(
    month: str = Query(..., description="Month in YYYY-MM format"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get a complete monthly report for the specified month (YYYY-MM).
    """
    return await report_service.get_monthly_report(
        db=db,
        tenant_id=current_user["tenant_id"],
        month_str=month,
    )


@router.get(
    "/weekly",
    response_model=ReportResponse,
)
async def get_weekly_report(
    week_start: str = Query(..., description="Date in YYYY-MM-DD format (will be normalized to Monday)"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get a complete weekly report starting from the specified date (normalized to Monday).
    """
    return await report_service.get_weekly_report(
        db=db,
        tenant_id=current_user["tenant_id"],
        week_start_str=week_start,
    )


# ============================================================
# MOST-SOLD PRODUCT — MONTHLY
# ============================================================

@router.get(
    "/most-sold-product",
)
async def get_most_sold_product(
    month: str = Query(
        ...,
        description="Month in YYYY-MM format",
        example="2026-09",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Return the product variant that sold the highest quantity during the
    selected month.

    Ranking is based on SUM(bill_items.quantity).
    Only COMPLETED bills are included.
    tenant_id is derived from the authenticated user — never from query params.
    """
    # tenant_id comes exclusively from the verified JWT — never from query params.
    tenant_id = current_user["tenant_id"]

    return await report_service.get_most_sold_product(
        db=db,
        tenant_id=tenant_id,
        month_str=month,
    )


# ============================================================
# MOST-SOLD PRODUCT — LAST 3 MONTHS
# ============================================================

@router.get(
    "/most-sold-products/last-3-months",
)
async def get_last_3_months_most_sold(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Return a month-by-month analysis of the top-selling variant for each of
    the last 3 calendar months (Asia/Kolkata), plus the single overall
    top-selling variant across the full 3-month window.

    The 3-month window is calculated automatically from server time in IST.
    tenant_id is derived from the authenticated user — never from query params.
    """
    # tenant_id comes exclusively from the verified JWT — never from query params.
    tenant_id = current_user["tenant_id"]

    return await report_service.get_last_3_months_most_sold(
        db=db,
        tenant_id=tenant_id,
    )
