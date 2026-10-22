from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.v1.internal.cloud.auth import verify_cloud_service_token
from app.api.v1.internal.cloud.schemas import (
    CloudBillItemResponse,
    CloudBillListResponse,
    CloudShopBillingSummary,
    PaginatedMeta,
)
from app.models.bill import Bill
from app.models.kadan_account import KadanAccount
from app.models.payment import Payment
from app.models.tenant import Tenant

router = APIRouter(
    tags=["Cloud Internal - Billing & Bills"],
    dependencies=[Depends(verify_cloud_service_token)],
)


# ============================================================
# SHOP-SPECIFIC BILLING ENDPOINTS
# ============================================================

@router.get("/shops/{tenant_id}/billing/summary", response_model=CloudShopBillingSummary)
async def get_shop_billing_summary(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Get aggregated financial summary for a specific shop.
    Revenue is calculated strictly from completed payments.
    """
    tenant_res = await db.execute(select(Tenant.id).where(Tenant.id == tenant_id))
    if not tenant_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found",
        )

    # Bills counts & amounts
    bills_stat_res = await db.execute(
        select(
            func.count(Bill.id).label("total_bills"),
            func.count(Bill.id).filter(Bill.status == "COMPLETED").label("completed_bills"),
            func.count(Bill.id).filter(Bill.status == "CANCELLED").label("cancelled_bills"),
            func.coalesce(
                func.sum(Bill.total_amount).filter(Bill.status != "CANCELLED"),
                Decimal("0.00"),
            ).label("billed_amount"),
            func.coalesce(
                func.sum(Bill.discount_amount).filter(Bill.status != "CANCELLED"),
                Decimal("0.00"),
            ).label("discount_amount"),
            func.coalesce(
                func.sum(Bill.tax_amount).filter(Bill.status != "CANCELLED"),
                Decimal("0.00"),
            ).label("tax_amount"),
        ).where(Bill.tenant_id == tenant_id)
    )
    b_stat = bills_stat_res.first()

    # Collected amount from completed payments
    payments_res = await db.execute(
        select(
            func.coalesce(func.sum(Payment.amount), Decimal("0.00"))
        ).where(
            Payment.tenant_id == tenant_id,
            Payment.status == "COMPLETED",
        )
    )
    collected_amount = payments_res.scalar() or Decimal("0.00")

    # Kadan / Credit outstanding balance
    kadan_res = await db.execute(
        select(
            func.coalesce(func.sum(KadanAccount.outstanding_amount), Decimal("0.00"))
        ).where(
            KadanAccount.tenant_id == tenant_id,
            KadanAccount.status == "ACTIVE",
        )
    )
    outstanding_credit = kadan_res.scalar() or Decimal("0.00")

    return CloudShopBillingSummary(
        tenant_id=tenant_id,
        total_bills_count=b_stat.total_bills if b_stat else 0,
        completed_bills_count=b_stat.completed_bills if b_stat else 0,
        cancelled_bills_count=b_stat.cancelled_bills if b_stat else 0,
        total_billed_amount=b_stat.billed_amount if b_stat else Decimal("0.00"),
        total_collected_amount=collected_amount,
        total_discount_given=b_stat.discount_amount if b_stat else Decimal("0.00"),
        total_tax_collected=b_stat.tax_amount if b_stat else Decimal("0.00"),
        total_outstanding_credit=outstanding_credit,
    )


@router.get("/shops/{tenant_id}/billing/bills", response_model=CloudBillListResponse)
async def list_shop_bills(
    tenant_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status_filter: str | None = Query(None, alias="status"),
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    List bills scoped strictly to a specific shop with filtering and pagination.
    """
    tenant_res = await db.execute(select(Tenant.id).where(Tenant.id == tenant_id))
    if not tenant_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found",
        )

    # Subquery for completed paid amount per bill
    paid_sub = (
        select(
            Payment.bill_id,
            func.coalesce(func.sum(Payment.amount), Decimal("0.00")).label("paid_amt"),
        )
        .where(
            Payment.tenant_id == tenant_id,
            Payment.status == "COMPLETED",
        )
        .group_by(Payment.bill_id)
        .subquery()
    )

    query = (
        select(Bill, func.coalesce(paid_sub.c.paid_amt, Decimal("0.00")).label("paid_amount"))
        .outerjoin(paid_sub, paid_sub.c.bill_id == Bill.id)
        .where(Bill.tenant_id == tenant_id)
    )

    count_query = select(func.count(Bill.id)).where(Bill.tenant_id == tenant_id)

    if status_filter:
        query = query.where(Bill.status == status_filter.upper())
        count_query = count_query.where(Bill.status == status_filter.upper())

    if start_date:
        query = query.where(Bill.created_at >= start_date)
        count_query = count_query.where(Bill.created_at >= start_date)

    if end_date:
        query = query.where(Bill.created_at <= end_date)
        count_query = count_query.where(Bill.created_at <= end_date)

    query = query.order_by(Bill.created_at.desc(), Bill.id.desc()).limit(limit).offset(offset)

    total_res = await db.execute(count_query)
    total = total_res.scalar() or 0

    results = await db.execute(query)
    rows = results.all()

    bill_items = [
        CloudBillItemResponse(
            id=b.id,
            tenant_id=b.tenant_id,
            bill_number=b.bill_number,
            customer_id=b.customer_id,
            subtotal=b.subtotal,
            discount_amount=b.discount_amount,
            tax_amount=b.tax_amount,
            total_amount=b.total_amount,
            paid_amount=paid_amt,
            status=b.status,
            created_by=b.created_by,
            created_at=b.created_at,
        )
        for b, paid_amt in rows
    ]

    return CloudBillListResponse(
        meta=PaginatedMeta(total=total, limit=limit, offset=offset),
        bills=bill_items,
    )


# ============================================================
# CROSS-SHOP GLOBAL BILLS ENDPOINT
# ============================================================

@router.get("/billing/bills", response_model=CloudBillListResponse)
async def list_global_bills(
    tenant_id: UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status_filter: str | None = Query(None, alias="status"),
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    List bills across all shops for CRYVEX Cloud administration.
    Protected by dedicated service authentication.
    """
    paid_sub = (
        select(
            Payment.bill_id,
            func.coalesce(func.sum(Payment.amount), Decimal("0.00")).label("paid_amt"),
        )
        .where(Payment.status == "COMPLETED")
        .group_by(Payment.bill_id)
        .subquery()
    )

    query = (
        select(Bill, func.coalesce(paid_sub.c.paid_amt, Decimal("0.00")).label("paid_amount"))
        .outerjoin(paid_sub, paid_sub.c.bill_id == Bill.id)
    )

    count_query = select(func.count(Bill.id))

    if tenant_id:
        query = query.where(Bill.tenant_id == tenant_id)
        count_query = count_query.where(Bill.tenant_id == tenant_id)

    if status_filter:
        query = query.where(Bill.status == status_filter.upper())
        count_query = count_query.where(Bill.status == status_filter.upper())

    if start_date:
        query = query.where(Bill.created_at >= start_date)
        count_query = count_query.where(Bill.created_at >= start_date)

    if end_date:
        query = query.where(Bill.created_at <= end_date)
        count_query = count_query.where(Bill.created_at <= end_date)

    query = query.order_by(Bill.created_at.desc(), Bill.id.desc()).limit(limit).offset(offset)

    total_res = await db.execute(count_query)
    total = total_res.scalar() or 0

    results = await db.execute(query)
    rows = results.all()

    bill_items = [
        CloudBillItemResponse(
            id=b.id,
            tenant_id=b.tenant_id,
            bill_number=b.bill_number,
            customer_id=b.customer_id,
            subtotal=b.subtotal,
            discount_amount=b.discount_amount,
            tax_amount=b.tax_amount,
            total_amount=b.total_amount,
            paid_amount=paid_amt,
            status=b.status,
            created_by=b.created_by,
            created_at=b.created_at,
        )
        for b, paid_amt in rows
    ]

    return CloudBillListResponse(
        meta=PaginatedMeta(total=total, limit=limit, offset=offset),
        bills=bill_items,
    )
