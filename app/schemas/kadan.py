from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ============================================================
# KADAN PAYMENT CREATE
# ============================================================

class KadanPaymentCreate(BaseModel):
    """
    Data required when a customer pays an existing Kadan balance.
    """

    amount: Decimal = Field(
        ...,
        gt=0,
    )

    payment_method: str = Field(
        ...,
        min_length=1,
        max_length=20,
    )

    notes: str | None = Field(
        default=None,
        max_length=500,
    )

    @field_validator("payment_method")
    @classmethod
    def validate_payment_method(cls, value):
        value = value.strip().upper()

        allowed_methods = {
            "CASH",
            "UPI",
        }

        if value not in allowed_methods:
            raise ValueError(
                "Payment method must be CASH or UPI"
            )

        return value

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, value):
        if value is None:
            return None

        value = value.strip()

        if not value:
            return None

        return value


# ============================================================
# KADAN SUMMARY
# ============================================================

class KadanSummaryResponse(BaseModel):
    total_kadan_amount: Decimal
    total_customers_with_kadan: int
    total_kadan_accounts: int
    active_kadan_accounts: int
    settled_kadan_accounts: int


# ============================================================
# KADAN ACCOUNT RESPONSE
# ============================================================

class KadanAccountResponse(BaseModel):
    account_id: UUID
    customer_id: UUID

    customer_name: str
    customer_phone: str

    outstanding_amount: Decimal
    status: str

    created_at: datetime

    model_config = {
        "from_attributes": True
    }


# ============================================================
# CUSTOMER KADAN RESPONSE
# ============================================================

class CustomerKadanResponse(BaseModel):
    account_id: UUID
    customer_id: UUID

    customer_name: str
    customer_phone: str

    total_kadan_amount: Decimal
    outstanding_amount: Decimal

    status: str

    created_at: datetime


# ============================================================
# KADAN TRANSACTION RESPONSE
# ============================================================

class KadanTransactionResponse(BaseModel):
    transaction_id: UUID

    account_id: UUID
    customer_id: UUID

    customer_name: str
    customer_phone: str

    transaction_type: str
    amount: Decimal
    balance_after: Decimal

    bill_id: UUID | None
    bill_number: str | None

    notes: str | None

    created_by: UUID
    created_at: datetime


# ============================================================
# SINGLE TRANSACTION RESPONSE
# ============================================================

class KadanTransactionDetailResponse(BaseModel):
    transaction_id: UUID

    account_id: UUID
    customer_id: UUID

    customer_name: str
    customer_phone: str

    transaction_type: str
    amount: Decimal
    balance_after: Decimal

    bill_id: UUID | None
    bill_number: str | None

    notes: str | None

    created_by: UUID
    created_at: datetime


# ============================================================
# KADAN PAYMENT RESPONSE
# ============================================================

class KadanPaymentResponse(BaseModel):
    transaction_id: UUID

    customer_id: UUID
    account_id: UUID

    previous_outstanding: Decimal
    paid_amount: Decimal
    remaining_outstanding: Decimal

    payment_method: str
    notes: str | None

    created_at: datetime