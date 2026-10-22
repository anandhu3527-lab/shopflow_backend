from pydantic import BaseModel,EmailStr,Field
from pytest import Class

#for shop and user registartaion process
class ShopRegistration(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    business_name: str | None = Field(default=None, max_length=200)
    phone_number: str | None = Field(default=None, max_length=20)
    email: EmailStr | None = None
    address: str | None = None

class UserRegistration(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    email: EmailStr | None = None
    phone_number: str = Field(..., min_length=10, max_length=20)
    password: str = Field(..., min_length=8)

class RegistrationRequest(BaseModel):
    shop: ShopRegistration
    user: UserRegistration

#for login process

class LoginRequest(BaseModel):
    identifier: str = Field(
        ...,
        min_length=3,
        max_length=255,
        description="User email address or phone number",
    )

    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
    )


class AuthMeUser(BaseModel):
    id: str
    name: str
    phone: str
    email: str | None
    status: str


class AuthMeTenant(BaseModel):
    id: str
    name: str
    business_name: str
    status: str


class AuthMeRole(BaseModel):
    id: str
    name: str
    description: str | None


class AuthMeData(BaseModel):
    user: AuthMeUser
    tenant: AuthMeTenant
    role: AuthMeRole
    authenticated: bool


class AuthMeResponse(BaseModel):
    type: str
    message: str
    data: AuthMeData


class UserProfileUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    email: EmailStr | None = None

