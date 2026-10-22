"""
Audit Repository
================

Handles all database persistence for AuditLog records.

Design rules:
- `create()` uses db.flush() (NOT db.commit()) so the audit INSERT
  joins the caller's transaction. The caller owns the commit.
- All list/get queries are tenant-scoped — a tenant can never
  access another tenant's audit records.
- No business logic lives here.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


class AuditRepository:

    # ============================================================
    # CREATE
    # ============================================================

    async def create(
        self,
        db: AsyncSession,
        audit_log: AuditLog,
    ) -> AuditLog:
        """
        Add an AuditLog to the current session and flush.

        IMPORTANT: Does NOT commit. The caller's transaction
        is responsible for commit/rollback. This ensures the
        audit record and the business operation are committed
        atomically.
        """
        db.add(audit_log)
        await db.flush()
        return audit_log

    # ============================================================
    # GET BY ID (tenant-scoped)
    # ============================================================

    async def get_by_id(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        audit_id: UUID,
    ) -> AuditLog | None:
        """
        Fetch a single AuditLog by ID, scoped to the tenant.
        Returns None if not found or belongs to a different tenant.
        """
        result = await db.execute(
            select(AuditLog).where(
                AuditLog.id == audit_id,
                AuditLog.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    # ============================================================
    # LIST BY TENANT (paginated, filtered, newest first)
    # ============================================================

    async def list_by_tenant(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        action: str | None = None,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        user_id: UUID | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditLog]:
        """
        List AuditLog records for a tenant with optional filters.

        Always tenant-scoped. Never exposes cross-tenant records.
        Results are ordered newest-first.
        """
        conditions = [AuditLog.tenant_id == tenant_id]

        if action:
            conditions.append(AuditLog.action == action)

        if entity_type:
            conditions.append(AuditLog.entity_type == entity_type)

        if entity_id:
            conditions.append(AuditLog.entity_id == entity_id)

        if user_id:
            conditions.append(AuditLog.user_id == user_id)

        if start_date:
            conditions.append(AuditLog.created_at >= start_date)

        if end_date:
            conditions.append(AuditLog.created_at <= end_date)

        result = await db.execute(
            select(AuditLog)
            .where(and_(*conditions))
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        return list(result.scalars().all())


# ============================================================
# SINGLETON INSTANCE
# ============================================================

audit_repository = AuditRepository()
