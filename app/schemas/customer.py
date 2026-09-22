from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class CustomerResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    phone: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }


class CustomerListResponse(BaseModel):
    id: UUID
    name: str
    phone: str
    status: str
    created_at: datetime

    model_config = {
        "from_attributes": True
    }


class CustomerSummaryResponse(BaseModel):
    total_bills: int
    total_purchase_amount: Decimal
    total_kadan_amount: Decimal
    has_kadan: bool


class CustomerDetailResponse(BaseModel):
    id: UUID
    name: str
    phone: str
    status: str
    created_at: datetime

    summary: CustomerSummaryResponse


class CustomerBillResponse(BaseModel):
    bill_id: UUID
    bill_number: str
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    paid_amount: Decimal
    kadan_amount: Decimal
    status: str
    created_at: datetime


class CustomerCreditBillResponse(BaseModel):
    bill_id: UUID
    bill_number: str
    total_amount: Decimal
    paid_amount: Decimal
    credit_amount: Decimal
    status: str
    created_at: datetime