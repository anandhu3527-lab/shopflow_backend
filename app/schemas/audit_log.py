"""
Audit Log Schemas (Read‑only)
==============================

Only owners can read audit logs, and the response never contains any
sensitive fields – the model already excludes passwords/keys.
"""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class AuditLogBase(BaseModel):
    id: UUID
    tenant_id: UUID
    user_id: Optional[UUID] = None
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[UUID] = None
    description: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: datetime

    model_config = {
        "from_attributes": True
    }


class AuditLogResponse(AuditLogBase):
    old_values: Optional[Dict[str, Any]] = Field(default=None)
    new_values: Optional[Dict[str, Any]] = Field(default=None)


class AuditLogListResponse(BaseModel):
    total: int = Field(..., description="Total number of records matching the filter")
    items: list[AuditLogResponse]
