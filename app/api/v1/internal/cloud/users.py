from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.v1.internal.cloud.auth import verify_cloud_service_token
from app.api.v1.internal.cloud.schemas import (
    ActivityItem,
    CloudShopActivityResponse,
    CloudUserAccessResetRequest,
    CloudUserAccessResetResponse,
    CloudUserDetailResponse,
    CloudUserListItem,
    CloudUserListResponse,
    CloudUserStatusUpdateRequest,
    CloudUserStatusUpdateResponse,
    PaginatedMeta,
)
from app.models.audit_log import AuditLog
from app.models.role import Role
from app.models.tenant import Tenant
from app.models.user import User
from app.models.user_role import UserRole
from app.services.audit_service import log as audit_log

router = APIRouter(
    prefix="/shops/{tenant_id}/users",
    tags=["Cloud Internal - Shop User Management"],
    dependencies=[Depends(verify_cloud_service_token)],
)


@router.get("", response_model=CloudUserListResponse)
async def list_shop_users(
    tenant_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    List all users scoped strictly to the specified tenant.
    Never returns password hashes or auth secrets.
    """
    # Verify tenant exists
    tenant_res = await db.execute(select(Tenant.id).where(Tenant.id == tenant_id))
    if not tenant_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found",
        )

    count_res = await db.execute(
        select(func.count(User.id)).where(User.tenant_id == tenant_id)
    )
    total = count_res.scalar() or 0

    query = (
        select(User, Role.name.label("role_name"))
        .outerjoin(UserRole, UserRole.user_id == User.id)
        .outerjoin(Role, Role.id == UserRole.role_id)
        .where(User.tenant_id == tenant_id)
        .order_by(User.created_at.desc(), User.id.desc())
        .limit(limit)
        .offset(offset)
    )

    results = await db.execute(query)
    rows = results.all()

    user_items = [
        CloudUserListItem(
            id=u.id,
            tenant_id=u.tenant_id,
            name=u.name,
            phone=u.phone,
            email=u.email,
            status=u.status,
            role_name=r_name,
            last_login_at=u.last_login_at,
            created_at=u.created_at,
        )
        for u, r_name in rows
    ]

    return CloudUserListResponse(
        meta=PaginatedMeta(total=total, limit=limit, offset=offset),
        users=user_items,
    )


@router.get("/{user_id}", response_model=CloudUserDetailResponse)
async def get_shop_user(
    tenant_id: UUID,
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Get user details strictly scoped to the tenant.
    """
    query = (
        select(User, Role.id.label("role_id"), Role.name.label("role_name"))
        .outerjoin(UserRole, UserRole.user_id == User.id)
        .outerjoin(Role, Role.id == UserRole.role_id)
        .where(User.id == user_id, User.tenant_id == tenant_id)
    )

    result = await db.execute(query)
    row = result.first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found for this shop",
        )

    u, r_id, r_name = row
    return CloudUserDetailResponse(
        id=u.id,
        tenant_id=u.tenant_id,
        name=u.name,
        phone=u.phone,
        email=u.email,
        status=u.status,
        role_name=r_name,
        role_id=r_id,
        last_login_at=u.last_login_at,
        created_at=u.created_at,
        updated_at=u.updated_at,
    )


@router.patch("/{user_id}/status", response_model=CloudUserStatusUpdateResponse)
async def update_user_status(
    tenant_id: UUID,
    user_id: UUID,
    payload: CloudUserStatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Update a shop user's status with tenant isolation and audit logging.
    """
    user_res = await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == tenant_id)
    )
    user = user_res.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found for this shop",
        )

    prev_status = user.status
    target_status = payload.status

    if prev_status == target_status:
        return CloudUserStatusUpdateResponse(
            success=True,
            user_id=user.id,
            tenant_id=tenant_id,
            previous_status=prev_status,
            new_status=target_status,
            message=f"User is already in {target_status} status",
        )

    user.status = target_status
    user.updated_at = datetime.now(timezone.utc)

    # Record in audit trail
    await audit_log(
        db=db,
        tenant_id=tenant_id,
        user_id=None,
        action="CLOUD_USER_STATUS_CHANGED",
        entity_type="user",
        entity_id=user.id,
        description=f"CRYVEX Cloud changed user {user.name} status from {prev_status} to {target_status}. Reason: {payload.reason or 'Not specified'}",
        old_values={"status": prev_status},
        new_values={"status": target_status, "reason": payload.reason, "actor": "CRYVEX_CLOUD_SERVICE"},
    )

    await db.commit()
    await db.refresh(user)

    return CloudUserStatusUpdateResponse(
        success=True,
        user_id=user.id,
        tenant_id=tenant_id,
        previous_status=prev_status,
        new_status=user.status,
        message=f"User status successfully updated to {user.status}",
    )


@router.post("/{user_id}/access-reset", response_model=CloudUserAccessResetResponse)
async def initiate_access_reset(
    tenant_id: UUID,
    user_id: UUID,
    payload: CloudUserAccessResetRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Initiate controlled account access reset.
    Accurately reports the lack of automated email/SMS dispatch without inventing notifications.
    """
    user_res = await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == tenant_id)
    )
    user = user_res.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found for this shop",
        )

    # Record the administrative action without exposing or inventing tokens
    await audit_log(
        db=db,
        tenant_id=tenant_id,
        user_id=None,
        action="CLOUD_USER_ACCESS_RESET_REQUESTED",
        entity_type="user",
        entity_id=user.id,
        description=f"CRYVEX Cloud requested access reset for user {user.name}. Reason: {payload.reason or 'Not specified'}",
        old_values=None,
        new_values={"target_user_id": str(user.id), "reason": payload.reason, "actor": "CRYVEX_CLOUD_SERVICE"},
    )
    await db.commit()

    return CloudUserAccessResetResponse(
        success=True,
        user_id=user.id,
        tenant_id=tenant_id,
        status="pending_integration",
        message="Access reset request has been logged by CRYVEX Cloud.",
        notification_delivery_supported=False,
        details=(
            "ShopFlow does not currently configure an automated email or SMS delivery channel. "
            "The administrative reset action was audited. An administrator or owner must coordinate credentials securely."
        ),
    )


@router.get("/{user_id}/activity", response_model=CloudShopActivityResponse)
async def get_user_activity(
    tenant_id: UUID,
    user_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    Get paginated, chronological activity timeline for a specific shop user.
    """
    # Verify user exists for this tenant
    user_res = await db.execute(
        select(User.id).where(User.id == user_id, User.tenant_id == tenant_id)
    )
    if not user_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found for this shop",
        )

    count_res = await db.execute(
        select(func.count(AuditLog.id)).where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.user_id == user_id,
        )
    )
    total = count_res.scalar() or 0

    query = (
        select(AuditLog)
        .where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.user_id == user_id,
        )
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
