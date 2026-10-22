from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.auth import RegistrationRequest
from app.services.auth_service import register_shop_and_user

from app.core.security import create_access_token
from app.schemas.auth import LoginRequest, AuthMeResponse, UserProfileUpdateRequest
from app.services.auth_service import login_user
from app.services.user_service import update_user_profile

from fastapi import Depends
from app.core.dependencies import get_current_user

from app.core.rate_limit import limiter


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


# endpoints for user and shop registration 
@router.post("/register")
async def register(
    data: RegistrationRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        tenant, user = await register_shop_and_user(
            db=db,
            shop_data=data.shop,
            user_data=data.user,
        )

        await db.commit()

        return {
            "success": True,
            "message": "Shop and user registered successfully",
            "shop": {
                "id": str(tenant.id),
                "name": tenant.name,
            },
            "user": {
                "id": str(user.id),
                "name": user.name,
            },
        }

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
            detail="Registration failed",
        )



#enpoints for user login and token generation------

@router.post("/login")
@limiter.limit("5/minute")
async def login(
    request: Request,
    data: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        # Authenticate user
        user, tenant, role = await login_user(
            db=db,
            identifier=data.identifier,
            password=data.password,
        )

        from app.services.audit_service import log as audit_log
        await audit_log(
            db=db,
            tenant_id=tenant.id,
            user_id=user.id,
            action="AUTH_LOGIN",
            entity_type="user",
            entity_id=user.id,
            description=f"User {user.name} logged in",
        )

        # Commit login-related database changes
        # This permanently saves last_login_at and audit log.
        await db.commit()

        # Create JWT access token
        access_token = create_access_token(
            user_id=user.id,
            tenant_id=tenant.id,
            role_id=role.id,
        )

        return {
            "success": True,
            "message": "Login successful",
            "access_token": access_token,
            "token_type": "bearer",
        }

    except ValueError as exc:
        await db.rollback()

        raise HTTPException(
            status_code=401,
            detail=str(exc),
        )

    except Exception:
        await db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Login failed",
        )

#for find the user-------

@router.get(
    "/me",
    response_model=AuthMeResponse,
)
async def get_me(
    current_user: dict = Depends(get_current_user),
):
    user = current_user["user"]
    tenant = current_user["tenant"]
    role = current_user["role"]

    return {
        "type": "success",
        "message": "Authenticated user verified successfully",
        "data": {
            "user": {
                "id": str(user.id),
                "name": user.name,
                "phone": user.phone,
                "email": user.email,
                "status": user.status,
            },
            "tenant": {
                "id": str(tenant.id),
                "name": tenant.name,
                "business_name": tenant.business_name,
                "status": tenant.status,
            },
            "role": {
                "id": str(role.id),
                "name": role.name,
                "description": role.description,
            },
            "authenticated": True,
        }
    }


@router.patch(
    "/me",
)
async def update_auth_me(
    update_data: UserProfileUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Update the authenticated user's profile details.
    """
    return await update_user_profile(
        db=db,
        current_user=current_user,
        update_data=update_data,
    )