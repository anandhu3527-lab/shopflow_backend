from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)


class BillItemCreate(BaseModel):
    variant_id: UUID
    quantity: Decimal = Field(..., gt=0)


class BillCreate(BaseModel):
    customer_name: str | None = Field(
        default=None, min_length=1, max_length=150
    )
    customer_phone: str | None = Field(
        default=None, min_length=1, max_length=20
    )
    items: list[BillItemCreate] = Field(..., min_length=1)
    discount_amount: Decimal = Field(
        default=Decimal("0.00"), ge=0
    )
    paid_amount: Decimal = Field(..., ge=0)
    payment_method: str = Field(
        ..., min_length=1, max_length=20
    )

    @field_validator("customer_name")
    @classmethod
    def validate_customer_name(cls, value):
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("customer_phone")
    @classmethod
    def validate_customer_phone(cls, value):
        if value is None:
            return None

        value = (
            value.strip()
            .replace(" ", "")
            .replace("-", "")
        )

        if value.startswith("+91"):
            value = value[3:]

        return value or None

    @field_validator("discount_amount")
    @classmethod
    def validate_discount_amount(cls, value):
        value = Decimal(str(value))
        if value < Decimal("0.00"):
            raise ValueError(
                "Discount amount cannot be negative."
            )
        return value.quantize(Decimal("0.01"))

    @field_validator("payment_method")
    @classmethod
    def validate_payment_method(cls, value):
        value = value.strip().upper()
        allowed_methods = {"CASH", "UPI", "KADAN"}

        if value not in allowed_methods:
            raise ValueError(
                "Payment method must be CASH, UPI, or KADAN"
            )

        return value

    @model_validator(mode="after")
    def validate_payment_combination(self):
        if (
            self.payment_method == "KADAN"
            and self.paid_amount != Decimal("0")
        ):
            raise ValueError(
                "KADAN payment method requires paid_amount to be 0"
            )

        return self


class BillCreateResponseData(BaseModel):
    bill_id: UUID
    bill_number: str
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    paid_amount: Decimal
    kadan_amount: Decimal
    payment_method: str
    created_at: datetime


class BillCreateResponse(BaseModel):
    type: str
    message: str
    data: BillCreateResponseData


class BillItemResponse(BaseModel):
    id: UUID
    bill_id: UUID
    product_id: UUID | None
    product_variant_id: UUID | None
    item_name: str
    quantity: Decimal
    unit_price: Decimal
    discount_amount: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    line_total: Decimal
    created_at: datetime

    model_config = {"from_attributes": True}


class PaymentResponse(BaseModel):
    id: UUID
    bill_id: UUID
    amount: Decimal
    payment_method: str
    status: str
    created_by: UUID
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class KadanSummary(BaseModel):
    # Keep the existing fields for frontend compatibility.
    paid_amount: Decimal
    kadan_amount: Decimal
    outstanding_amount: Decimal

    # Details of the CREDIT transaction linked to this bill.
    transaction_id: UUID | None = None
    account_id: UUID | None = None
    transaction_type: str | None = None
    balance_after_transaction: Decimal | None = None
    notes: str | None = None
    created_at: datetime | None = None


class BillCustomerResponse(BaseModel):
    id: UUID
    name: str
    phone: str

    model_config = {"from_attributes": True}


class BillResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    customer_id: UUID | None
    bill_number: str
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    status: str
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    items: list[BillItemResponse]
    payments: list[PaymentResponse]
    customer: BillCustomerResponse | None = None
    kadan: KadanSummary | None = None

    model_config = {"from_attributes": True}


class MonthSummary(BaseModel):
    total_bills: int
    total_sales: Decimal


class DateSummary(BaseModel):
    total_bills: int
    total_sales: Decimal


class DateSummaryBillResponse(BaseModel):
    id: UUID
    bill_number: str
    total_amount: Decimal
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DateSummaryResponse(BaseModel):
    date: str
    month: str
    month_summary: MonthSummary
    date_summary: DateSummary
    bills: list[DateSummaryBillResponse]
