from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.v1.internal.cloud.auth import verify_cloud_service_token
from app.api.v1.internal.cloud.schemas import CloudShopUsageResponse
from app.models.audit_log import AuditLog
from app.models.bill import Bill
from app.models.customer import Customer
from app.models.product import Product
from app.models.subscription import Subscription
from app.models.tenant import Tenant
from app.models.user import User

router = APIRouter(
    prefix="/shops/{tenant_id}/usage",
    tags=["Cloud Internal - Shop Usage"],
    dependencies=[Depends(verify_cloud_service_token)],
)


@router.get("", response_model=CloudShopUsageResponse)
async def get_shop_usage(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Get operational usage statistics for a shop derived from actual persisted records.
    """
    tenant_res = await db.execute(select(Tenant.id).where(Tenant.id == tenant_id))
    if not tenant_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found",
        )

    # Bills count
    bills_res = await db.execute(
        select(func.count(Bill.id)).where(Bill.tenant_id == tenant_id)
    )
    total_bills = bills_res.scalar() or 0

    # Products count
    prods_res = await db.execute(
        select(func.count(Product.id)).where(Product.tenant_id == tenant_id)
    )
    total_products = prods_res.scalar() or 0

    # Users count
    users_res = await db.execute(
        select(func.count(User.id)).where(User.tenant_id == tenant_id)
    )
    total_users = users_res.scalar() or 0

    # Customers count
    cust_res = await db.execute(
        select(func.count(Customer.id)).where(Customer.tenant_id == tenant_id)
    )
    total_customers = cust_res.scalar() or 0

    # Audit events count
    audit_res = await db.execute(
        select(func.count(AuditLog.id)).where(AuditLog.tenant_id == tenant_id)
    )
    total_audit_events = audit_res.scalar() or 0

    # Active days count (distinct calendar days with bill activity)
    active_days_res = await db.execute(
        select(func.count(func.distinct(func.date_trunc("day", Bill.created_at)))).where(
            Bill.tenant_id == tenant_id
        )
    )
    active_days_count = active_days_res.scalar() or 0

    # Subscription plan
    sub_res = await db.execute(
        select(Subscription.plan).where(Subscription.tenant_id == tenant_id)
    )
    sub_plan = sub_res.scalar_one_or_none()

    return CloudShopUsageResponse(
        tenant_id=tenant_id,
        total_bills=total_bills,
        total_products=total_products,
        total_users=total_users,
        total_customers=total_customers,
        total_audit_events=total_audit_events,
        active_days_count=active_days_count,
        subscription_plan=sub_plan,
        calculated_at=datetime.now(timezone.utc),
    )
