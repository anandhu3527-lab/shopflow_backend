from datetime import datetime
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


class VegetableCreate(BaseModel):
    product_id: UUID
    price_per_kg: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    tax_rate: Decimal = Field(default=Decimal("0"), ge=0, le=100, max_digits=5, decimal_places=2)
    stock_kg: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=3)
    unit: str = Field(default="kg", min_length=1, max_length=20)

    @field_validator("unit")
    @classmethod
    def normalize_unit(cls, value):
        value = value.strip().lower()
        if value not in {"kg", "g"}:
            raise ValueError("unit must be kg or g")
        return value


class VegetableUpdate(BaseModel):
    price_per_kg: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    tax_rate: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    stock_kg: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=3)
    status: str | None = Field(default=None, pattern="^(ACTIVE|INACTIVE)$")


class VegetableResponse(BaseModel):
    id: UUID
    product_id: UUID
    name: str
    unit: str
    price_per_kg: Decimal
    tax_rate: Decimal
    stock_kg: Decimal
    status: str
    created_at: datetime


class VegetableBillLine(BaseModel):
    vegetable_id: UUID
    weight_kg: Decimal = Field(gt=0, max_digits=12, decimal_places=3)


class VegetableBillCreate(BaseModel):
    items: list[VegetableBillLine] = Field(min_length=1)
    discount_amount: Decimal = Field(default=Decimal("0.00"), ge=0)
    paid_amount: Decimal = Field(ge=0)
    payment_method: str = Field(min_length=1, max_length=20)
    customer_name: str | None = Field(default=None, max_length=150)
    customer_phone: str | None = Field(default=None, max_length=20)

    @field_validator("payment_method")
    @classmethod
    def normalize_payment_method(cls, value):
        value = value.strip().upper()
        if value not in {"CASH", "UPI", "KADAN"}:
            raise ValueError("payment_method must be CASH, UPI, or KADAN")
        return value
