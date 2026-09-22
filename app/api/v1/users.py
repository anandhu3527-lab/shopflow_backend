from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user

from app.schemas.user import (
    CreateEmployeeRequest,
    CreateEmployeeResponse,
    EmployeeResponse,
)

from app.services.user_service import create_employee


router = APIRouter()


# ============================================================
# CREATE EMPLOYEE / MANAGER
# ============================================================

@router.post(
    "/users/employees",
    response_model=CreateEmployeeResponse,
)
async def create_employee_endpoint(
    data: CreateEmployeeRequest,
    db: AsyncSession = Depends(get_db),
    auth_context=Depends(get_current_user),
):
    """
    Create an EMPLOYEE or MANAGER under the authenticated OWNER's shop.

    Only OWNER can access this endpoint.
    """

    try:

        # ====================================================
        # 1. GET AUTHENTICATED USER / TENANT / ROLE
        # ====================================================

        if isinstance(auth_context, dict):

            user = auth_context.get("user")
            tenant = auth_context.get("tenant")
            role = auth_context.get("role")

        elif isinstance(auth_context, tuple):

            user, tenant, role = auth_context

        else:
            raise HTTPException(
                status_code=500,
                detail="Invalid authentication context",
            )

        # ====================================================
        # 2. VERIFY AUTHENTICATED USER
        # ====================================================

        if user is None:
            raise HTTPException(
                status_code=401,
                detail="Authentication required",
            )

        # ====================================================
        # 3. VERIFY TENANT
        # ====================================================

        if tenant is None:
            raise HTTPException(
                status_code=403,
                detail="Shop not found",
            )

        if tenant.status != "ACTIVE":
            raise HTTPException(
                status_code=403,
                detail="Shop account is not active",
            )

        # ====================================================
        # 4. VERIFY USER STATUS
        # ====================================================

        if user.status != "ACTIVE":
            raise HTTPException(
                status_code=403,
                detail="User account is not active",
            )

        # ====================================================
        # 5. VERIFY ROLE
        # ====================================================

        if role is None:
            raise HTTPException(
                status_code=403,
                detail="User role not found",
            )

        authenticated_role = role.name.upper()

        # ONLY OWNER CAN CREATE
        if authenticated_role != "OWNER":
            raise HTTPException(
                status_code=403,
                detail="Only OWNER can create employees",
            )

        # ====================================================
        # 6. CREATE USER
        # ====================================================

        created_user, created_role = await create_employee(
            db=db,
            current_user=user,
            tenant=tenant,
            employee_data=data,
        )

        # ====================================================
        # 7. COMMIT TRANSACTION
        # ====================================================

        await db.commit()

        # ====================================================
        # 8. RETURN RESPONSE
        # ====================================================

        return {
            "success": True,
            "message": "Employee created successfully",
            "employee": {
                "user_id": str(created_user.id),
                "tenant_id": str(created_user.tenant_id),
                "name": created_user.name,
                "email": created_user.email,
                "phone_number": created_user.phone,
                "role_id": str(created_role.id),
                "role": created_role.name,
                "status": created_user.status,
            },
        }

    except HTTPException:
        # Do not convert our intentional HTTP errors
        raise

    except PermissionError as exc:

        await db.rollback()

        raise HTTPException(
            status_code=403,
            detail=str(exc),
        )

    except ValueError as exc:

        await db.rollback()

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except Exception:

        await db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Failed to create employee",
        )