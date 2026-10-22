from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.models.tenant import Tenant
from app.models.user import User
from app.models.role import Role
from app.models.user_role import UserRole

from app.core.security import hash_password, verify_password


# ============================================================
# REGISTER SHOP + FIRST USER
# ============================================================

async def register_shop_and_user(
    db: AsyncSession,
    shop_data,
    user_data,
):
    """
    Register a new Shop and its first User.

    The Shop, User and UserRole are created as part
    of the same database transaction.

    The caller is responsible for commit/rollback.
    """

    # ========================================================
    # 1. CHECK USER PHONE
    # ========================================================

    result = await db.execute(
        select(User).where(
            User.phone == user_data.phone_number
        )
    )

    existing_user_by_phone = result.scalar_one_or_none()

    if existing_user_by_phone:
        raise ValueError(
            "User phone number already registered"
        )

    # ========================================================
    # 2. CHECK USER EMAIL
    # ========================================================

    if user_data.email:

        result = await db.execute(
            select(User).where(
                User.email == user_data.email
            )
        )

        existing_user_by_email = result.scalar_one_or_none()

        if existing_user_by_email:
            raise ValueError(
                "User email already registered"
            )

    # ========================================================
    # 3. CREATE SHOP / TENANT
    # ========================================================

    tenant = Tenant(
        name=shop_data.name,
        business_name=shop_data.business_name,
        phone=shop_data.phone_number,
        email=shop_data.email,
        address=shop_data.address,
    )

    db.add(tenant)

    # Flush sends INSERT to PostgreSQL
    # and makes tenant.id available.
    await db.flush()

    # ========================================================
    # 4. HASH USER PASSWORD
    # ========================================================

    password_hash = hash_password(
        user_data.password
    )

    # ========================================================
    # 5. CREATE USER
    # ========================================================

    user = User(
        tenant_id=tenant.id,
        name=user_data.name,
        email=user_data.email,
        phone=user_data.phone_number,
        password_hash=password_hash,
    )

    db.add(user)

    # Flush so user.id becomes available
    # for user_roles.
    await db.flush()

    # ========================================================
    # 6. FIND OWNER ROLE
    # ========================================================

    result = await db.execute(
        select(Role).where(
            Role.name == "OWNER"
        )
    )

    owner_role = result.scalar_one_or_none()

    if owner_role is None:
        raise ValueError(
            "OWNER role does not exist"
        )

    # ========================================================
    # 7. ASSIGN OWNER ROLE TO USER
    # ========================================================

    user_role = UserRole(
        user_id=user.id,
        role_id=owner_role.id,
    )

    db.add(user_role)

    # ========================================================
    # 8. RETURN CREATED OBJECTS
    # ========================================================

    return tenant, user


# ============================================================
# LOGIN USER
# ============================================================

async def login_user(
    db: AsyncSession,
    identifier: str,
    password: str,
):
    """
    Authenticate a ShopFlow user using email or phone number.

    Authentication checks:

    1. User exists
    2. User is ACTIVE
    3. Tenant exists
    4. Tenant is ACTIVE
    5. Password is correct
    6. User has a role
    7. Update last_login_at

    Returns:

        user
        tenant
        role

    The caller is responsible for commit/rollback.
    """

    # ========================================================
    # 1. FIND USER BY EMAIL OR PHONE
    # ========================================================

    result = await db.execute(
        select(User).where(
            or_(
                User.email == identifier,
                User.phone == identifier,
            )
        )
    )

    user = result.scalar_one_or_none()

    # ========================================================
    # 2. VERIFY USER EXISTS
    # ========================================================

    if user is None:
        raise ValueError(
            "Invalid email/phone or password"
        )

    # ========================================================
    # 3. CHECK USER STATUS
    # ========================================================

    if user.status != "ACTIVE":
        raise ValueError(
            "User account is not active"
        )

    # ========================================================
    # 4. GET USER'S TENANT / SHOP
    # ========================================================

    result = await db.execute(
        select(Tenant).where(
            Tenant.id == user.tenant_id
        )
    )

    tenant = result.scalar_one_or_none()

    # ========================================================
    # 5. VERIFY TENANT EXISTS
    # ========================================================

    if tenant is None:
        raise ValueError(
            "User shop not found"
        )

    # ========================================================
    # 6. CHECK TENANT / SHOP STATUS
    # ========================================================

    if tenant.status != "ACTIVE":
        raise ValueError(
            "Shop account is not active"
        )

    # ========================================================
    # 7. VERIFY PASSWORD
    # ========================================================

    password_valid = verify_password(
        password,
        user.password_hash,
    )

    if not password_valid:
        raise ValueError(
            "Invalid email/phone or password"
        )

    # ========================================================
    # 8. UPDATE LAST LOGIN TIME
    # ========================================================

    user.last_login_at = datetime.now(timezone.utc)

    # Flush makes the UPDATE part of the current transaction.
    await db.flush()

    # ========================================================
    # 9. GET USER'S ROLE
    # ========================================================

    result = await db.execute(
        select(Role)
        .join(
            UserRole,
            UserRole.role_id == Role.id
        )
        .where(
            UserRole.user_id == user.id
        )
    )

    role = result.scalar_one_or_none()

    if role is None:
        raise ValueError(
            "User role not found"
        )

    # ========================================================
    # 10. RETURN AUTHENTICATED DATA
    # ========================================================

    return user, tenant, role