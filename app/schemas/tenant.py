from datetime import datetime
from pydantic import BaseModel, Field


class TenantUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=150)
    business_name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=255)
    address: str | None = None



class TenantEmployeeResponse(BaseModel):
    id: str
    name: str
    phone: str
    status: str
    role: str
    created_at: datetime


class TenantShopResponse(BaseModel):
    id: str
    name: str
    business_name: str
    phone: str
    email: str | None
    address: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class TenantMeData(BaseModel):
    shop: TenantShopResponse
    owner: TenantEmployeeResponse
    employees: list[TenantEmployeeResponse]


class TenantMeResponse(BaseModel):
    type: str
    message: str
    data: TenantMeData
