from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.v1.internal.cloud.auth import verify_cloud_service_token
from app.api.v1.internal.cloud.schemas import (
    ActivityItem,
    CloudShopActivityResponse,
    CloudShopDetailResponse,
    CloudShopKPIs,
    CloudShopListItem,
    CloudShopListResponse,
    CloudShopStatusUpdateRequest,
    CloudShopStatusUpdateResponse,
    PaginatedMeta,
    ShopWithoutSubscriptionItem,
    ShopsWithoutSubscriptionResponse,
)
from app.models.audit_log import AuditLog
from app.models.bill import Bill
from app.models.customer import Customer
from app.models.payment import Payment
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.subscription import Subscription
from app.models.tenant import Tenant
from app.models.user import User
from app.services.audit_service import log as audit_log

router = APIRouter(
    prefix="/shops",
    tags=["Cloud Internal - Shop Management"],
    dependencies=[Depends(verify_cloud_service_token)],
)


@router.get("", response_model=CloudShopListResponse)
async def list_shops(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status_filter: str | None = Query(None, alias="status"),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    List shops with bounded pagination, deterministic ordering, and optional filters.
    """
    query = (
        select(
            Tenant,
            Subscription.plan.label("sub_plan"),
            Subscription.status.label("sub_status"),
        )
        .outerjoin(Subscription, Subscription.tenant_id == Tenant.id)
    )

    count_query = select(func.count(Tenant.id))

    if status_filter:
        query = query.where(Tenant.status == status_filter.upper())
        count_query = count_query.where(Tenant.status == status_filter.upper())

    if search:
        search_pattern = f"%{search.strip()}%"
        search_cond = or_(
            Tenant.name.ilike(search_pattern),
            Tenant.business_name.ilike(search_pattern),
            Tenant.phone.ilike(search_pattern),
            Tenant.email.ilike(search_pattern),
        )
        query = query.where(search_cond)
        count_query = count_query.where(search_cond)

    # Deterministic sorting
    query = query.order_by(Tenant.created_at.desc(), Tenant.id.desc()).limit(limit).offset(offset)

    total_res = await db.execute(count_query)
    total = total_res.scalar() or 0

    results = await db.execute(query)
    rows = results.all()

    shop_items = [
        CloudShopListItem(
            id=t.id,
            name=t.name,
            business_name=t.business_name,
            phone=t.phone,
            email=t.email,
            status=t.status,
            created_at=t.created_at,
            updated_at=t.updated_at,
            subscription_plan=sub_plan,
            subscription_status=sub_status,
        )
        for t, sub_plan, sub_status in rows
    ]

    return CloudShopListResponse(
        meta=PaginatedMeta(total=total, limit=limit, offset=offset),
        shops=shop_items,
    )


@router.get("/without-subscription", response_model=ShopsWithoutSubscriptionResponse)
async def list_shops_without_subscription(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    Find shops that lack a subscription record or have missing/blank essential subscription fields.
    Clearly distinguishes MISSING from INCOMPLETE subscriptions.
    """
    incomplete_condition = or_(
        Subscription.id.is_(None),
        Subscription.plan.is_(None),
        func.trim(Subscription.plan) == "",
        Subscription.status.is_(None),
        func.trim(Subscription.status) == "",
    )

    count_query = (
        select(func.count(Tenant.id))
        .outerjoin(Subscription, Subscription.tenant_id == Tenant.id)
        .where(incomplete_condition)
    )

    query = (
        select(Tenant, Subscription)
        .outerjoin(Subscription, Subscription.tenant_id == Tenant.id)
        .where(incomplete_condition)
        .order_by(Tenant.created_at.desc(), Tenant.id.desc())
        .limit(limit)
        .offset(offset)
    )

    total_res = await db.execute(count_query)
    total = total_res.scalar() or 0

    results = await db.execute(query)
    rows = results.all()

    items = []
    for tenant, sub in rows:
        missing_fields = []
        if sub is None:
            config_status = "MISSING"
            missing_fields.append("subscription_record")
            sub_id = None
        else:
            config_status = "INCOMPLETE"
            sub_id = sub.id
            if not sub.plan or not sub.plan.strip():
                missing_fields.append("plan")
            if not sub.status or not sub.status.strip():
                missing_fields.append("status")

        items.append(
            ShopWithoutSubscriptionItem(
                tenant_id=tenant.id,
                name=tenant.name,
                business_name=tenant.business_name,
                status=tenant.status,
                created_at=tenant.created_at,
                subscription_configuration_status=config_status,
                subscription_id=sub_id,
                missing_fields=missing_fields,
            )
        )

    return ShopsWithoutSubscriptionResponse(
        meta=PaginatedMeta(total=total, limit=limit, offset=offset),
        shops=items,
    )


@router.get("/{tenant_id}", response_model=CloudShopDetailResponse)
async def get_shop_detail(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Get detailed information for a specific shop.
    """
    tenant_res = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = tenant_res.scalar_one_or_none()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found",
        )

    # Subscription
    sub_res = await db.execute(
        select(Subscription).where(Subscription.tenant_id == tenant_id)
    )
    sub = sub_res.scalar_one_or_none()
    sub_data = None
    if sub:
        sub_data = {
            "id": str(sub.id),
            "plan": sub.plan,
            "status": sub.status,
            "start_date": sub.start_date.isoformat(),
            "end_date": sub.end_date.isoformat() if sub.end_date else None,
        }

    # Counts
    user_count_res = await db.execute(
        select(func.count(User.id)).where(User.tenant_id == tenant_id)
    )
    product_count_res = await db.execute(
        select(func.count(Product.id)).where(Product.tenant_id == tenant_id)
    )

    stats = {
        "user_count": user_count_res.scalar() or 0,
        "product_count": product_count_res.scalar() or 0,
    }

    return CloudShopDetailResponse(
        id=tenant.id,
        name=tenant.name,
        business_name=tenant.business_name,
        phone=tenant.phone,
        email=tenant.email,
        address=tenant.address,
        status=tenant.status,
        created_at=tenant.created_at,
        updated_at=tenant.updated_at,
        subscription=sub_data,
        stats=stats,
    )


@router.get("/{tenant_id}/overview", response_model=CloudShopKPIs)
async def get_shop_kpis(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Get verified shop-specific operational KPIs for CRYVEX Cloud administration.
    """
    tenant_res = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = tenant_res.scalar_one_or_none()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found",
        )

    now_utc = datetime.now(timezone.utc)
    today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = today_start.replace(day=1)

    # Users
    users_total_res = await db.execute(
        select(func.count(User.id)).where(User.tenant_id == tenant_id)
    )
    total_users = users_total_res.scalar() or 0

    users_active_res = await db.execute(
        select(func.count(User.id)).where(
            User.tenant_id == tenant_id, User.status == "ACTIVE"
        )
    )
    active_users = users_active_res.scalar() or 0

    # Products
    products_total_res = await db.execute(
        select(func.count(Product.id)).where(Product.tenant_id == tenant_id)
    )
    total_products = products_total_res.scalar() or 0

    products_active_res = await db.execute(
        select(func.count(Product.id)).where(
            Product.tenant_id == tenant_id, Product.status == "ACTIVE"
        )
    )
    active_products = products_active_res.scalar() or 0

    # Low stock variants
    low_stock_res = await db.execute(
        select(func.count(ProductVariant.id)).where(
            ProductVariant.tenant_id == tenant_id,
            ProductVariant.status == "ACTIVE",
            ProductVariant.stock_quantity <= ProductVariant.low_stock_threshold,
        )
    )
    low_stock_count = low_stock_res.scalar() or 0

    # Customers
    customers_res = await db.execute(
        select(func.count(Customer.id)).where(Customer.tenant_id == tenant_id)
    )
    total_customers = customers_res.scalar() or 0

    # Bills
    bills_total_res = await db.execute(
        select(func.count(Bill.id)).where(Bill.tenant_id == tenant_id)
    )
    total_bills = bills_total_res.scalar() or 0

    bills_today_res = await db.execute(
        select(func.count(Bill.id)).where(
            Bill.tenant_id == tenant_id, Bill.created_at >= today_start
        )
    )
    bills_today = bills_today_res.scalar() or 0

    bills_month_res = await db.execute(
        select(func.count(Bill.id)).where(
            Bill.tenant_id == tenant_id, Bill.created_at >= month_start
        )
    )
    bills_this_month = bills_month_res.scalar() or 0

    # Sales & Revenue
    sales_res = await db.execute(
        select(func.coalesce(func.sum(Bill.total_amount), Decimal("0.00"))).where(
            Bill.tenant_id == tenant_id, Bill.status != "CANCELLED"
        )
    )
    total_sales_amount = sales_res.scalar() or Decimal("0.00")

    rev_res = await db.execute(
        select(func.coalesce(func.sum(Payment.amount), Decimal("0.00"))).where(
            Payment.tenant_id == tenant_id, Payment.status == "COMPLETED"
        )
    )
    total_revenue_collected = rev_res.scalar() or Decimal("0.00")

    # Subscription
    sub_res = await db.execute(
        select(Subscription).where(Subscription.tenant_id == tenant_id)
    )
    sub = sub_res.scalar_one_or_none()

    return CloudShopKPIs(
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        status=tenant.status,
        total_users=total_users,
        active_users=active_users,
        total_products=total_products,
        active_products=active_products,
        low_stock_variants_count=low_stock_count,
        total_customers=total_customers,
        total_bills=total_bills,
        bills_today=bills_today,
        bills_this_month=bills_this_month,
        total_sales_amount=total_sales_amount,
        total_revenue_collected=total_revenue_collected,
        subscription_plan=sub.plan if sub else None,
        subscription_status=sub.status if sub else None,
        subscription_end_date=sub.end_date if sub else None,
    )


@router.get("/{tenant_id}/activity", response_model=CloudShopActivityResponse)
async def get_shop_activity(
    tenant_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    Get paginated, chronological activity timeline for this shop.
    """
    # Verify tenant exists
    tenant_res = await db.execute(select(Tenant.id).where(Tenant.id == tenant_id))
    if not tenant_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found",
        )

    count_res = await db.execute(
        select(func.count(AuditLog.id)).where(AuditLog.tenant_id == tenant_id)
    )
    total = count_res.scalar() or 0

    query = (
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
        .offset(offset)
    )
    results = await db.execute(query)
    logs = results.scalars().all()

    activity_items = [
        ActivityItem(
            id=log.id,
            action=log.action,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            description=log.description,
            actor_user_id=log.user_id,
            created_at=log.created_at,
            changes={"old": log.old_values, "new": log.new_values}
            if (log.old_values or log.new_values)
            else None,
        )
        for log in logs
    ]

    return CloudShopActivityResponse(
        meta=PaginatedMeta(total=total, limit=limit, offset=offset),
        activity=activity_items,
    )


@router.patch("/{tenant_id}/status", response_model=CloudShopStatusUpdateResponse)
async def update_shop_status(
    tenant_id: UUID,
    payload: CloudShopStatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Update shop status with transaction safety and audit tracking.
    """
    tenant_res = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = tenant_res.scalar_one_or_none()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found",
        )

    prev_status = tenant.status
    target_status = payload.status

    if prev_status == target_status:
        return CloudShopStatusUpdateResponse(
            success=True,
            tenant_id=tenant.id,
            previous_status=prev_status,
            new_status=target_status,
            message=f"Shop is already in {target_status} status",
        )

    tenant.status = target_status
    tenant.updated_at = datetime.now(timezone.utc)

    # Record in audit trail
    await audit_log(
        db=db,
        tenant_id=tenant.id,
        user_id=None,
        action="CLOUD_SHOP_STATUS_CHANGED",
        entity_type="tenant",
        entity_id=tenant.id,
        description=f"CRYVEX Cloud changed shop status from {prev_status} to {target_status}. Reason: {payload.reason or 'Not specified'}",
        old_values={"status": prev_status},
        new_values={"status": target_status, "reason": payload.reason, "actor": "CRYVEX_CLOUD_SERVICE"},
    )

    await db.commit()
    await db.refresh(tenant)

    return CloudShopStatusUpdateResponse(
        success=True,
        tenant_id=tenant.id,
        previous_status=prev_status,
        new_status=tenant.status,
        message=f"Shop status successfully updated to {tenant.status}",
    )
