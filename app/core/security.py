from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from jose import jwt

from app.core.config import settings


# ==================================================
# PASSWORD HASHING
# ==================================================

password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """
    Hash a plain-text password using Argon2.
    """
    return password_hasher.hash(password)


def verify_password(
    password: str,
    password_hash: str,
) -> bool:
    """
    Verify a plain-text password against an Argon2 hash.
    """
    try:
        return password_hasher.verify(
            password_hash,
            password,
        )
    except VerifyMismatchError:
        return False


# ==================================================
# JWT ACCESS TOKEN
# ==================================================

def create_access_token(
    user_id,
    tenant_id,
    role_id,
) -> str:
    """
    Create a JWT access token for an authenticated
    ShopFlow user.
    """

    now = datetime.now(timezone.utc)

    expire = now + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role_id": str(role_id),
        "iat": now,
        "exp": expire,
    }

    token = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    return token

    