"""
Audit Service
==============

A thin wrapper around :class:`AuditRepository`. It builds an
:class:`AuditLog` instance, normalises values to JSON‑safe types, and
flushes the record into the caller's transaction.

All callers **must** pass the same ``db`` session that they will later
``await db.commit()`` on. This guarantees atomicity – if the business
operation rolls back, the audit row is rolled back as well.
"""

import json
from datetime import datetime
from uuid import UUID
from typing import Any, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.repositories.audit_repository import audit_repository


def _json_safe(value: Any) -> Any:
    """Convert Python values to JSON‑serialisable equivalents.

    * ``UUID`` → ``str``
    * ``datetime`` → ISO‑8601 string (UTC)
    * ``Decimal`` → ``str`` to avoid float rounding
    * ``Enum`` → ``value`` (usually a string or int)
    Anything else is returned unchanged – ``json.dumps`` will raise if
    something truly unsafe is passed.
    """
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.isoformat() + "Z"
        return value.astimezone(datetime.timezone.utc).isoformat()
    # ``Decimal`` is imported lazily to avoid a hard dependency on
    # ``decimal`` if the project never uses it.
    try:
        from decimal import Decimal
    except Exception:  # pragma: no cover – defensive only
        Decimal = None  # type: ignore
    if Decimal and isinstance(value, Decimal):
        return str(value)
    # Enums are usually subclassed from ``str`` or ``int``. ``value``
    # returns the underlying primitive.
    try:
        from enum import Enum
    except Exception:  # pragma: no cover
        Enum = None  # type: ignore
    if Enum and isinstance(value, Enum):
        return value.value
    return value


def _prepare_snapshot(data: Mapping[str, Any] | None) -> dict | None:
    """Return a JSON‑safe ``dict`` from a mapping.

    ``None`` stays ``None`` – callers can choose to omit the field.
    """
    if data is None:
        return None
    return {k: _json_safe(v) for k, v in data.items()}


async def log(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID | None = None,
    action: str,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    description: str | None = None,
    old_values: Mapping[str, Any] | None = None,
    new_values: Mapping[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Create a new audit log entry.

    The function does **not** commit – it merely adds the record to the
    supplied ``db`` session and flushes it. The calling service/router
    should subsequently ``await db.commit()`` as it normally does.
    """
    audit = AuditLog(
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        description=description,
        old_values=_prepare_snapshot(old_values),
        new_values=_prepare_snapshot(new_values),
        ip_address=ip_address,
        user_agent=user_agent,
        created_at=datetime.utcnow(),
    )
    await audit_repository.create(db, audit)


# Export a singleton for convenient import elsewhere.

__all__ = ["log"]
