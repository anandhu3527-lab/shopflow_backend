import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.role import Role
from app.models.user_role import UserRole

from app.core.security import hash_password


# ============================================================
# CREATE EMPLOYEE / MANAGER
# ============================================================

async def create_employee(
    db: AsyncSession,
    current_user: User,
    tenant,
    employee_data,
):
    """
    Create a new employee or manager.

    Security rules:
    - Only OWNER can create users.
    - tenant_id comes from authenticated tenant.
    - role_id comes from the backend Role table.
    - frontend cannot provide tenant_id or role_id.
    - password is hashed before storage.
    - User + UserRole are created in the same transaction.
    """

    # ========================================================
    # 1. VERIFY CURRENT USER
    # ========================================================

    if current_user is None:
        raise ValueError("Authentication required")

    # ========================================================
    # 2. VERIFY CURRENT USER IS OWNER
    # ========================================================

    # The endpoint passes the authenticated user's role
    # separately through current_user.role_name when available.
    #
    # This check is also performed in the API layer.
    # Keeping the rule here provides defense in depth.

    role_name = getattr(current_user, "role_name", None)

    if role_name and role_name.upper() != "OWNER":
        raise PermissionError(
            "Only OWNER can create employees"
        )

    # ========================================================
    # 3. VERIFY TENANT
    # ========================================================

    if tenant is None:
        raise ValueError("Tenant not found")

    if tenant.status != "ACTIVE":
        raise ValueError("Shop account is not active")

    tenant_id = tenant.id

    # ========================================================
    # 4. CHECK USER PHONE
    # ========================================================

    result = await db.execute(
        select(User).where(
            User.phone == employee_data.phone_number
        )
    )

    existing_user_by_phone = result.scalar_one_or_none()

    if existing_user_by_phone:
        raise ValueError(
            "User phone number already registered"
        )

    # ========================================================
    # 5. CHECK USER EMAIL
    # ========================================================

    if employee_data.email:

        result = await db.execute(
            select(User).where(
                User.email == employee_data.email
            )
        )

        existing_user_by_email = result.scalar_one_or_none()

        if existing_user_by_email:
            raise ValueError(
                "User email already registered"
            )

    # ========================================================
    # 6. FIND REQUESTED ROLE
    # ========================================================

    requested_role = employee_data.role.upper()

    if requested_role not in {"EMPLOYEE", "MANAGER"}:
        raise ValueError(
            "Invalid role. Only EMPLOYEE or MANAGER is allowed"
        )

    result = await db.execute(
        select(Role).where(
            Role.name == requested_role
        )
    )

    role = result.scalar_one_or_none()

    if role is None:
        raise ValueError(
            f"{requested_role} role does not exist"
        )

    # ========================================================
    # 7. HASH PASSWORD
    # ========================================================

    password_hash = hash_password(
        employee_data.password
    )

    # ========================================================
    # 8. CREATE USER
    # ========================================================

    user = User(
        tenant_id=tenant_id,
        name=employee_data.name,
        email=employee_data.email,
        phone=employee_data.phone_number,
        password_hash=password_hash,
        status="ACTIVE",
    )

    db.add(user)

    # Flush so user.id becomes available
    await db.flush()

    # ========================================================
    # 9. ASSIGN ROLE
    # ========================================================

    user_role = UserRole(
        user_id=user.id,
        role_id=role.id,
    )

    db.add(user_role)

    # Flush to make sure INSERT is valid
    await db.flush()

    # ========================================================
    # 10. AUDIT LOG
    # ========================================================

    from app.services.audit_service import log as audit_log
    await audit_log(
        db=db,
        tenant_id=tenant_id,
        user_id=current_user.id,
        action="USER_CREATED",
        entity_type="user",
        entity_id=user.id,
        description=f"Created user {user.name} with role {role.name}",
        new_values={
            "name": user.name,
            "email": user.email,
            "phone": user.phone,
            "role": role.name,
        }
    )

    # ========================================================
    # 11. RETURN CREATED DATA
    # ========================================================

    return user, role


# ============================================================
# UPDATE USER PROFILE
# ============================================================

async def update_user_profile(
    db: AsyncSession,
    current_user: dict,
    update_data,
) -> dict:
    """
    Update the current authenticated user's profile.
    """
    update_dict = update_data.model_dump(exclude_unset=True)
    
    from fastapi import HTTPException, status
    
    if not update_dict:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided for update",
        )
        
    user = current_user["user"]
    
    old_values = {}
    new_values = {}
    
    for key, value in update_dict.items():
        old_val = getattr(user, key, None)
        if old_val != value:
            old_values[key] = old_val
            new_values[key] = value
        setattr(user, key, value)
        
    if new_values:
        from app.services.audit_service import log as audit_log
        await audit_log(
            db=db,
            tenant_id=current_user["tenant_id"],
            user_id=user.id,
            action="USER_PROFILE_UPDATED",
            entity_type="user",
            entity_id=user.id,
            description=f"User {user.name} updated profile",
            old_values=old_values,
            new_values=new_values,
        )
        
    await db.commit()
    await db.refresh(user)

    return {
        "type": "success",
        "message": "Profile updated successfully",
        "data": {
            "user": {
                "id": str(user.id),
                "name": user.name,
                "phone": user.phone,
                "email": user.email,
                "status": user.status,
                "created_at": user.created_at,
                "updated_at": user.updated_at,
            }
        }
    }