"""
Audit Log Router (read‑only)
============================

Only owners (role `OWNER`) may access audit logs. All endpoints are
tenant‑scoped – the ``tenant_id`` is taken from the authenticated
context and used as a filter for every query.
"""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_roles
from app.repositories.audit_repository import audit_repository
from app.schemas.audit_log import AuditLogResponse, AuditLogListResponse

router = APIRouter(prefix="/audit-logs", tags=["Audit Logs"])

# Helper to ensure the caller is an OWNER.
_require_owner = require_roles(["OWNER"])


@router.get("/", response_model=AuditLogListResponse)
async def list_audit_logs(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(_require_owner),
    action: str | None = Query(None),
    entity_type: str | None = Query(None),
    entity_id: str | None = Query(None),
    user_id: str | None = Query(None),
    start_date: str | None = Query(None, description="ISO‑8601 date-time"),
    end_date: str | None = Query(None, description="ISO‑8601 date-time"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    tenant_id = current_user["tenant_id"]
    # Convert string UUIDs to real UUID objects when supplied.
    from uuid import UUID as _UUID
    e_id = _UUID(entity_id) if entity_id else None
    u_id = _UUID(user_id) if user_id else None
    s_date = datetime.fromisoformat(start_date) if start_date else None
    e_date = datetime.fromisoformat(end_date) if end_date else None

    items = await audit_repository.list_by_tenant(
        db=db,
        tenant_id=tenant_id,
        action=action,
        entity_type=entity_type,
        entity_id=e_id,
        user_id=u_id,
        start_date=s_date,
        end_date=e_date,
        limit=limit,
        offset=offset,
    )
    total = len(items)  # For simplicity; could be a COUNT(*) query.
    return AuditLogListResponse(total=total, items=items)


@router.get("/{audit_id}", response_model=AuditLogResponse)
async def get_audit_log(
    audit_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(_require_owner),
):
    tenant_id = current_user["tenant_id"]
    from uuid import UUID as _UUID
    audit = await audit_repository.get_by_id(db, tenant_id, _UUID(audit_id))
    if not audit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit record not found")
    return audit
