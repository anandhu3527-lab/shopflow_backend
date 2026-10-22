from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.v1.internal.cloud.auth import verify_cloud_service_token
from app.api.v1.internal.cloud.schemas import (
    CloudAuditLogItem,
    CloudAuditLogListResponse,
    PaginatedMeta,
)
from app.models.audit_log import AuditLog
from app.models.tenant import Tenant

router = APIRouter(
    prefix="/shops/{tenant_id}/audit-logs",
    tags=["Cloud Internal - Audit Logs"],
    dependencies=[Depends(verify_cloud_service_token)],
)

# Sensitive keys that must never be exposed in audit snapshots
SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "jwt",
}


def _sanitize_snapshot(data: dict | None) -> dict | None:
    if not isinstance(data, dict):
        return data
    sanitized = {}
    for k, v in data.items():
        if k.lower() in SENSITIVE_KEYS or any(s in k.lower() for s in ["password", "secret", "token"]):
            sanitized[k] = "[REDACTED]"
        elif isinstance(v, dict):
            sanitized[k] = _sanitize_snapshot(v)
        else:
            sanitized[k] = v
    return sanitized


@router.get("", response_model=CloudAuditLogListResponse)
async def list_shop_audit_logs(
    tenant_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    action: str | None = Query(None),
    entity_type: str | None = Query(None),
    entity_id: UUID | None = Query(None),
    user_id: UUID | None = Query(None),
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    List audit logs for a shop with filtering, pagination, and sensitive data sanitization.
    Strictly tenant-scoped.
    """
    tenant_res = await db.execute(select(Tenant.id).where(Tenant.id == tenant_id))
    if not tenant_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found",
        )

    count_query = select(func.count(AuditLog.id)).where(AuditLog.tenant_id == tenant_id)
    query = select(AuditLog).where(AuditLog.tenant_id == tenant_id)

    if action:
        query = query.where(AuditLog.action == action)
        count_query = count_query.where(AuditLog.action == action)

    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
        count_query = count_query.where(AuditLog.entity_type == entity_type)

    if entity_id:
        query = query.where(AuditLog.entity_id == entity_id)
        count_query = count_query.where(AuditLog.entity_id == entity_id)

    if user_id:
        query = query.where(AuditLog.user_id == user_id)
        count_query = count_query.where(AuditLog.user_id == user_id)

    if start_date:
        query = query.where(AuditLog.created_at >= start_date)
        count_query = count_query.where(AuditLog.created_at >= start_date)

    if end_date:
        query = query.where(AuditLog.created_at <= end_date)
        count_query = count_query.where(AuditLog.created_at <= end_date)

    query = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit).offset(offset)

    total_res = await db.execute(count_query)
    total = total_res.scalar() or 0

    results = await db.execute(query)
    logs = results.scalars().all()

    audit_items = [
        CloudAuditLogItem(
            id=log.id,
            tenant_id=log.tenant_id,
            user_id=log.user_id,
            action=log.action,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            description=log.description,
            old_values=_sanitize_snapshot(log.old_values),
            new_values=_sanitize_snapshot(log.new_values),
            ip_address=log.ip_address,
            created_at=log.created_at,
        )
        for log in logs
    ]

    return CloudAuditLogListResponse(
        meta=PaginatedMeta(total=total, limit=limit, offset=offset),
        audit_logs=audit_items,
    )
