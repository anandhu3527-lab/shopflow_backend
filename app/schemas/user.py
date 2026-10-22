from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Literal


# ============================================================
# CREATE EMPLOYEE REQUEST
# ============================================================

class CreateEmployeeRequest(BaseModel):
    name: str = Field(
        ...,
        min_length=2,
        max_length=150
    )

    email: EmailStr | None = None

    phone_number: str = Field(
        ...,
        min_length=7,
        max_length=20
    )

    password: str = Field(
        ...,
        min_length=8,
        max_length=128
    )

    role: Literal["EMPLOYEE", "MANAGER"]

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Name cannot be empty")

        return value

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Phone number cannot be empty")

        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value:
            return value.strip().lower()

        return value

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        return value.upper()


# ============================================================
# CREATE EMPLOYEE RESPONSE
# ============================================================

class EmployeeResponse(BaseModel):
    user_id: str
    tenant_id: str
    name: str
    email: str | None
    phone_number: str
    role_id: str
    role: str
    status: str


class CreateEmployeeResponse(BaseModel):
    success: bool
    message: str
    employee: EmployeeResponse