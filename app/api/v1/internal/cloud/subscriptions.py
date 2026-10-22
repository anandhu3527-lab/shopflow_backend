import uuid
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.v1.internal.cloud.auth import verify_cloud_service_token
from app.api.v1.internal.cloud.schemas import (
    ActivityItem,
    CloudShopSubscriptionItem,
    CloudShopSubscriptionListResponse,
    CloudSubscriptionActionRequest,
    CloudSubscriptionActivationRequest,
    CloudSubscriptionActivationResponse,
    CloudSubscriptionChangeRequest,
    CloudSubscriptionDetail,
    CloudSubscriptionHistoryResponse,
    CloudSubscriptionOperationResponse,
    PaginatedMeta,
)
from app.models.audit_log import AuditLog
from app.models.subscription import Subscription
from app.models.tenant import Tenant
from app.services.audit_service import log as audit_log

router = APIRouter(
    tags=["Cloud Internal - Subscription Management"],
    dependencies=[Depends(verify_cloud_service_token)],
)


# ============================================================
# GLOBAL SUBSCRIPTION ENDPOINTS
# ============================================================

@router.get("/subscriptions", response_model=CloudShopSubscriptionListResponse)
async def list_shop_subscriptions(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    plan: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
):
    """
    List all shop subscriptions joined with shop details for CRYVEX Cloud administration.
    Supports bounded pagination and filtering by plan and status.
    Returns HTTP 200 with an empty list if no subscriptions exist.
    """
    query = (
        select(Subscription, Tenant)
        .join(Tenant, Tenant.id == Subscription.tenant_id)
    )
    count_query = (
        select(func.count(Subscription.id))
        .join(Tenant, Tenant.id == Subscription.tenant_id)
    )

    if plan:
        query = query.where(Subscription.plan.ilike(plan.strip()))
        count_query = count_query.where(Subscription.plan.ilike(plan.strip()))

    if status_filter:
        query = query.where(Subscription.status.ilike(status_filter.strip()))
        count_query = count_query.where(Subscription.status.ilike(status_filter.strip()))

    query = (
        query.order_by(Subscription.created_at.desc(), Subscription.id.desc())
        .limit(limit)
        .offset(offset)
    )

    total_res = await db.execute(count_query)
    total = total_res.scalar() or 0

    results = await db.execute(query)
    rows = results.all()

    sub_items = [
        CloudShopSubscriptionItem(
            id=s.id,
            tenant_id=s.tenant_id,
            shop_name=t.name,
            business_name=t.business_name,
            shop_status=t.status,
            plan=s.plan,
            status=s.status,
            start_date=s.start_date,
            end_date=s.end_date,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s, t in rows
    ]

    return CloudShopSubscriptionListResponse(
        meta=PaginatedMeta(total=total, limit=limit, offset=offset),
        subscriptions=sub_items,
    )


@router.get("/subscriptions/{subscription_id}", response_model=CloudSubscriptionDetail)
async def get_subscription_by_id(
    subscription_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Get subscription by ID across shops for CRYVEX Cloud administration.
    """
    res = await db.execute(
        select(Subscription).where(Subscription.id == subscription_id)
    )
    sub = res.scalar_one_or_none()
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )
    return CloudSubscriptionDetail(
        id=sub.id,
        tenant_id=sub.tenant_id,
        plan=sub.plan,
        status=sub.status,
        start_date=sub.start_date,
        end_date=sub.end_date,
        created_at=sub.created_at,
        updated_at=sub.updated_at,
    )


# ============================================================
# SHOP-SPECIFIC SUBSCRIPTION ENDPOINTS
# ============================================================

@router.get("/shops/{tenant_id}/subscription", response_model=CloudSubscriptionDetail)
async def get_shop_subscription(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Get the subscription for a specific shop.
    """
    # Verify tenant exists
    tenant_res = await db.execute(select(Tenant.id).where(Tenant.id == tenant_id))
    if not tenant_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found",
        )

    res = await db.execute(
        select(Subscription).where(Subscription.tenant_id == tenant_id)
    )
    sub = res.scalar_one_or_none()
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No subscription found for this shop",
        )

    return CloudSubscriptionDetail(
        id=sub.id,
        tenant_id=sub.tenant_id,
        plan=sub.plan,
        status=sub.status,
        start_date=sub.start_date,
        end_date=sub.end_date,
        created_at=sub.created_at,
        updated_at=sub.updated_at,
    )


@router.get("/shops/{tenant_id}/subscription/history", response_model=CloudSubscriptionHistoryResponse)
async def get_shop_subscription_history(
    tenant_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    Get subscription event history for a shop derived from the audit log.
    Truthfully notes the schema single-row design.
    """
    tenant_res = await db.execute(select(Tenant.id).where(Tenant.id == tenant_id))
    if not tenant_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found",
        )

    # Current subscription
    sub_res = await db.execute(
        select(Subscription).where(Subscription.tenant_id == tenant_id)
    )
    sub = sub_res.scalar_one_or_none()
    current_sub = (
        CloudSubscriptionDetail(
            id=sub.id,
            tenant_id=sub.tenant_id,
            plan=sub.plan,
            status=sub.status,
            start_date=sub.start_date,
            end_date=sub.end_date,
            created_at=sub.created_at,
            updated_at=sub.updated_at,
        )
        if sub
        else None
    )

    # Audit records for subscription changes
    audit_query = (
        select(AuditLog)
        .where(
            AuditLog.tenant_id == tenant_id,
            (AuditLog.entity_type == "subscription") | (AuditLog.action.like("CLOUD_SUBSCRIPTION_%")),
        )
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
        .offset(offset)
    )
    audit_res = await db.execute(audit_query)
    logs = audit_res.scalars().all()

    events = [
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

    return CloudSubscriptionHistoryResponse(
        tenant_id=tenant_id,
        current_subscription=current_sub,
        history_events=events,
        history_tracking_note=(
            "The database schema maintains a single subscription row per tenant (with a unique constraint on tenant_id) "
            "and does not have a separate subscription_history table. Historical changes are tracked via the audit trail."
        ),
    )


@router.post("/shops/{tenant_id}/subscription/upgrade", response_model=CloudSubscriptionOperationResponse)
async def upgrade_subscription(
    tenant_id: UUID,
    payload: CloudSubscriptionChangeRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Upgrade shop subscription plan with transactional auditing.
    """
    tenant_res = await db.execute(select(Tenant.id).where(Tenant.id == tenant_id))
    if not tenant_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found",
        )

    res = await db.execute(
        select(Subscription).where(Subscription.tenant_id == tenant_id)
    )
    sub = res.scalar_one_or_none()
    if not sub:
        # Create a new subscription record if none exists for this tenant
        now = datetime.now(timezone.utc)
        sub = Subscription(
            tenant_id=tenant_id,
            plan=payload.new_plan.upper(),
            status="ACTIVE",
            start_date=now,
            end_date=payload.end_date,
        )
        db.add(sub)
        await db.flush()

        await audit_log(
            db=db,
            tenant_id=tenant_id,
            user_id=None,
            action="CLOUD_SUBSCRIPTION_UPGRADED",
            entity_type="subscription",
            entity_id=sub.id,
            description=f"CRYVEX Cloud created upgraded subscription with plan {sub.plan}. Reason: {payload.reason or 'Not specified'}",
            old_values=None,
            new_values={"plan": sub.plan, "status": sub.status, "reason": payload.reason, "actor": "CRYVEX_CLOUD_SERVICE"},
        )
    else:
        old_plan = sub.plan
        old_status = sub.status
        sub.plan = payload.new_plan.upper()
        sub.status = "ACTIVE"
        if payload.end_date:
            sub.end_date = payload.end_date
        sub.updated_at = datetime.now(timezone.utc)

        await audit_log(
            db=db,
            tenant_id=tenant_id,
            user_id=None,
            action="CLOUD_SUBSCRIPTION_UPGRADED",
            entity_type="subscription",
            entity_id=sub.id,
            description=f"CRYVEX Cloud upgraded subscription from {old_plan} to {sub.plan}. Reason: {payload.reason or 'Not specified'}",
            old_values={"plan": old_plan, "status": old_status},
            new_values={"plan": sub.plan, "status": sub.status, "reason": payload.reason, "actor": "CRYVEX_CLOUD_SERVICE"},
        )

    await db.commit()
    await db.refresh(sub)

    return CloudSubscriptionOperationResponse(
        success=True,
        subscription_id=sub.id,
        tenant_id=sub.tenant_id,
        plan=sub.plan,
        status=sub.status,
        start_date=sub.start_date,
        end_date=sub.end_date,
        message=f"Subscription successfully upgraded to {sub.plan}",
    )


@router.post("/shops/{tenant_id}/subscription/downgrade", response_model=CloudSubscriptionOperationResponse)
async def downgrade_subscription(
    tenant_id: UUID,
    payload: CloudSubscriptionChangeRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Downgrade shop subscription plan with transactional auditing.
    """
    tenant_res = await db.execute(select(Tenant.id).where(Tenant.id == tenant_id))
    if not tenant_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found",
        )

    res = await db.execute(
        select(Subscription).where(Subscription.tenant_id == tenant_id)
    )
    sub = res.scalar_one_or_none()
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active subscription found to downgrade",
        )

    old_plan = sub.plan
    old_status = sub.status
    sub.plan = payload.new_plan.upper()
    if payload.end_date:
        sub.end_date = payload.end_date
    sub.updated_at = datetime.now(timezone.utc)

    await audit_log(
        db=db,
        tenant_id=tenant_id,
        user_id=None,
        action="CLOUD_SUBSCRIPTION_DOWNGRADED",
        entity_type="subscription",
        entity_id=sub.id,
        description=f"CRYVEX Cloud downgraded subscription from {old_plan} to {sub.plan}. Reason: {payload.reason or 'Not specified'}",
        old_values={"plan": old_plan, "status": old_status},
        new_values={"plan": sub.plan, "status": sub.status, "reason": payload.reason, "actor": "CRYVEX_CLOUD_SERVICE"},
    )

    await db.commit()
    await db.refresh(sub)

    return CloudSubscriptionOperationResponse(
        success=True,
        subscription_id=sub.id,
        tenant_id=sub.tenant_id,
        plan=sub.plan,
        status=sub.status,
        start_date=sub.start_date,
        end_date=sub.end_date,
        message=f"Subscription successfully downgraded to {sub.plan}",
    )


@router.post("/shops/{tenant_id}/subscription/suspend", response_model=CloudSubscriptionOperationResponse)
async def suspend_subscription(
    tenant_id: UUID,
    payload: CloudSubscriptionActionRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Suspend shop subscription with transactional auditing.
    """
    tenant_res = await db.execute(select(Tenant.id).where(Tenant.id == tenant_id))
    if not tenant_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found",
        )

    res = await db.execute(
        select(Subscription).where(Subscription.tenant_id == tenant_id)
    )
    sub = res.scalar_one_or_none()
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No subscription found for this shop",
        )

    prev_status = sub.status
    sub.status = "SUSPENDED"
    sub.updated_at = datetime.now(timezone.utc)

    await audit_log(
        db=db,
        tenant_id=tenant_id,
        user_id=None,
        action="CLOUD_SUBSCRIPTION_SUSPENDED",
        entity_type="subscription",
        entity_id=sub.id,
        description=f"CRYVEX Cloud suspended subscription. Reason: {payload.reason or 'Not specified'}",
        old_values={"status": prev_status},
        new_values={"status": sub.status, "reason": payload.reason, "actor": "CRYVEX_CLOUD_SERVICE"},
    )

    await db.commit()
    await db.refresh(sub)

    return CloudSubscriptionOperationResponse(
        success=True,
        subscription_id=sub.id,
        tenant_id=sub.tenant_id,
        plan=sub.plan,
        status=sub.status,
        start_date=sub.start_date,
        end_date=sub.end_date,
        message="Subscription suspended successfully",
    )


@router.post(
    "/shops/{tenant_id}/subscription/activate",
    response_model=CloudSubscriptionActivationResponse,
    status_code=status.HTTP_200_OK,
    summary="Activate shop subscription",
    description="Activates a subscription configuration for a shop with transactional auditing.",
)
async def activate_subscription(
    tenant_id: UUID,
    payload: CloudSubscriptionActivationRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Activate shop subscription with complete configuration and transactional auditing.
    """
    # 1. Confirm that the tenant exists
    tenant_res = await db.execute(select(Tenant.id).where(Tenant.id == tenant_id))
    if not tenant_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shop with id '{tenant_id}' not found",
        )

    # 2. Check whether the tenant already has a subscription
    res = await db.execute(
        select(Subscription).where(Subscription.tenant_id == tenant_id)
    )
    existing_sub = res.scalar_one_or_none()
    if existing_sub:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tenant '{tenant_id}' already has a subscription. Duplicate subscriptions are not permitted.",
        )

    # 3. Create the new subscription record (system-managed ID, created_at, updated_at)
    sub = Subscription(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        plan=payload.plan,
        status=payload.status,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    db.add(sub)
    await db.flush()

    # 4. Record the activation and reason in the audit infrastructure
    await audit_log(
        db=db,
        tenant_id=tenant_id,
        user_id=None,
        action="CLOUD_SUBSCRIPTION_ACTIVATED",
        entity_type="subscription",
        entity_id=sub.id,
        description=f"CRYVEX Cloud activated subscription with plan {sub.plan}. Reason: {payload.reason}",
        old_values=None,
        new_values={
            "subscription_id": sub.id,
            "plan": sub.plan,
            "status": sub.status,
            "start_date": sub.start_date,
            "end_date": sub.end_date,
            "reason": payload.reason,
            "actor": "CRYVEX_CLOUD_SERVICE",
        },
    )

    # 5. Apply the operation transactionally with conflict handling
    try:
        await db.commit()
        await db.refresh(sub)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Subscription conflict: Tenant '{tenant_id}' already has a subscription.",
        )

    # 6. Return saved subscription details in explicit response schema
    return CloudSubscriptionActivationResponse(
        success=True,
        subscription_id=sub.id,
        tenant_id=sub.tenant_id,
        plan=sub.plan,
        status=sub.status,
        start_date=sub.start_date,
        end_date=sub.end_date,
        created_at=sub.created_at,
        updated_at=sub.updated_at,
        message="Subscription activated successfully",
    )


@router.post("/shops/{tenant_id}/subscription/cancel", response_model=CloudSubscriptionOperationResponse)
async def cancel_subscription(
    tenant_id: UUID,
    payload: CloudSubscriptionActionRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Cancel shop subscription with transactional auditing.
    """
    tenant_res = await db.execute(select(Tenant.id).where(Tenant.id == tenant_id))
    if not tenant_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found",
        )

    res = await db.execute(
        select(Subscription).where(Subscription.tenant_id == tenant_id)
    )
    sub = res.scalar_one_or_none()
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No subscription found for this shop",
        )

    prev_status = sub.status
    sub.status = "CANCELLED"
    sub.updated_at = datetime.now(timezone.utc)

    await audit_log(
        db=db,
        tenant_id=tenant_id,
        user_id=None,
        action="CLOUD_SUBSCRIPTION_CANCELLED",
        entity_type="subscription",
        entity_id=sub.id,
        description=f"CRYVEX Cloud cancelled subscription. Reason: {payload.reason or 'Not specified'}",
        old_values={"status": prev_status},
        new_values={"status": sub.status, "reason": payload.reason, "actor": "CRYVEX_CLOUD_SERVICE"},
    )

    await db.commit()
    await db.refresh(sub)

    return CloudSubscriptionOperationResponse(
        success=True,
        subscription_id=sub.id,
        tenant_id=sub.tenant_id,
        plan=sub.plan,
        status=sub.status,
        start_date=sub.start_date,
        end_date=sub.end_date,
        message="Subscription cancelled successfully",
    )
