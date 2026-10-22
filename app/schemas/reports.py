from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class ReportPeriodResponse(BaseModel):
    start: str
    end: str
    timezone: str


class ReportSummaryResponse(BaseModel):
    total_bills: int
    total_sales: Decimal
    total_subtotal: Decimal
    total_discount: Decimal
    total_tax: Decimal
    total_paid: Decimal
    total_credit_generated: Decimal
    average_bill_value: Decimal
    total_customers: int


class PaymentSummaryResponse(BaseModel):
    total_amount: Decimal
    transaction_count: int
    by_method: dict[str, Decimal]


class DailyBreakdownResponse(BaseModel):
    date: str
    total_bills: int
    total_sales: Decimal
    total_paid: Decimal
    total_credit: Decimal


class BillDetailResponse(BaseModel):
    bill_id: UUID
    bill_number: str
    customer_id: UUID | None
    customer_name: str | None
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    paid_amount: Decimal
    credit_amount: Decimal
    status: str
    created_at: datetime


class KadanPeriodSummaryResponse(BaseModel):
    credit_generated: Decimal
    credit_transactions: int
    collected: Decimal
    repayment_transactions: int


class KadanCurrentSummaryResponse(BaseModel):
    outstanding_amount: Decimal
    customers_with_outstanding: int


class KadanTransactionDetailResponse(BaseModel):
    transaction_id: UUID
    customer_id: UUID
    customer_name: str | None
    customer_phone: str | None
    account_id: UUID
    transaction_type: str
    amount: Decimal
    balance_after: Decimal
    bill_id: UUID | None
    bill_number: str | None
    notes: str | None
    created_by: UUID
    created_at: datetime


class CustomerKadanSummaryResponse(BaseModel):
    customer_id: UUID
    customer_name: str | None
    customer_phone: str | None
    credit_generated: Decimal
    kadan_paid: Decimal
    current_outstanding: Decimal


class KadanReportResponse(BaseModel):
    period: KadanPeriodSummaryResponse
    current: KadanCurrentSummaryResponse
    transactions: list[KadanTransactionDetailResponse]
    customers: list[CustomerKadanSummaryResponse]


class ReportResponse(BaseModel):
    report_type: Literal["MONTHLY", "WEEKLY"]
    period: ReportPeriodResponse
    summary: ReportSummaryResponse
    payments: PaymentSummaryResponse
    daily_breakdown: list[DailyBreakdownResponse]
    bills: list[BillDetailResponse]
    kadan: KadanReportResponse


# ===========================================================
# MOST-SOLD PRODUCT REPORTING SCHEMAS
# ===========================================================


class MostSoldVariantData(BaseModel):
    """Data for a single most-sold product variant."""

    product_id: UUID
    variant_id: UUID
    product_name: str
    package_quantity: Decimal
    unit: str
    barcode: str | None
    sku: str | None
    quantity_sold: Decimal
    total_sales_value: Decimal
    average_selling_price: Decimal


class MostSoldProductResponse(BaseModel):
    """Response for GET /reports/most-sold-product?month=YYYY-MM."""

    type: str
    message: str
    data: MostSoldVariantData | None


class MonthlyMostSoldEntry(BaseModel):
    """One month's top-selling variant entry inside the 3-month analysis."""

    month: str  # "YYYY-MM"
    product_id: UUID
    variant_id: UUID
    product_name: str
    package_quantity: Decimal
    unit: str
    barcode: str | None
    sku: str | None
    quantity_sold: Decimal
    total_sales_value: Decimal
    average_selling_price: Decimal


class OverallTopSellingVariant(BaseModel):
    """The single top-selling variant across the full 3-month window."""

    product_id: UUID
    variant_id: UUID
    product_name: str
    package_quantity: Decimal
    unit: str
    barcode: str | None
    sku: str | None
    quantity_sold: Decimal
    total_sales_value: Decimal
    average_selling_price: Decimal


class Last3MonthsData(BaseModel):
    """Payload inside the last-3-months response."""

    months: list[MonthlyMostSoldEntry]
    overall_top_selling_variant: OverallTopSellingVariant | None


class Last3MonthsResponse(BaseModel):
    """Response for GET /reports/most-sold-products/last-3-months."""

    type: str
    message: str
    data: Last3MonthsData
