from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)


# ============================================================
# BASE & COMMON SCHEMAS
# ============================================================

class PaginatedMeta(BaseModel):
    total: int
    limit: int
    offset: int


class StandardSuccessResponse(BaseModel):
    success: bool = True
    message: str


# ============================================================
# A. OVERVIEW DASHBOARD SCHEMAS
# ============================================================

class OverallDashboardMetrics(BaseModel):
    total_shops: int
    active_shops: int
    trial_shops: int
    suspended_shops: int
    expired_shops: int
    new_shops_this_month: int
    active_users: int
    bills_generated_today: int
    monthly_revenue: Decimal

    model_config = ConfigDict(from_attributes=True)


class SystemHealthResponse(BaseModel):
    status: Literal["ok", "degraded", "error"]
    database_connected: bool
    service: str = "shopflow-api-internal-cloud"
    timestamp: datetime


class SubscriptionOverviewMetrics(BaseModel):
    total_subscriptions: int
    by_plan: dict[str, int]
    by_status: dict[str, int]
    expiring_soon_count: int  # within next 7 days


class BillsOverviewMetrics(BaseModel):
    total_bills_all_time: int
    bills_today: int
    bills_this_month: int
    total_billed_amount: Decimal
    total_collected_revenue: Decimal
    by_status: dict[str, int]


# ============================================================
# B. SHOP MANAGEMENT SCHEMAS
# ============================================================

class CloudShopListItem(BaseModel):
    id: UUID
    name: str
    business_name: str
    phone: str
    email: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    subscription_plan: str | None = None
    subscription_status: str | None = None

    model_config = ConfigDict(from_attributes=True)


class CloudShopListResponse(BaseModel):
    meta: PaginatedMeta
    shops: list[CloudShopListItem]


class CloudShopDetailResponse(BaseModel):
    id: UUID
    name: str
    business_name: str
    phone: str
    email: str | None
    address: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    subscription: dict[str, Any] | None = None
    stats: dict[str, Any] | None = None

    model_config = ConfigDict(from_attributes=True)


class CloudShopKPIs(BaseModel):
    tenant_id: UUID
    tenant_name: str
    status: str
    total_users: int
    active_users: int
    total_products: int
    active_products: int
    low_stock_variants_count: int
    total_customers: int
    total_bills: int
    bills_today: int
    bills_this_month: int
    total_sales_amount: Decimal
    total_revenue_collected: Decimal
    subscription_plan: str | None
    subscription_status: str | None
    subscription_end_date: datetime | None


class ActivityItem(BaseModel):
    id: UUID
    action: str
    entity_type: str | None
    entity_id: UUID | None
    description: str | None
    actor_user_id: UUID | None
    created_at: datetime
    changes: dict[str, Any] | None = None

    model_config = ConfigDict(from_attributes=True)


class CloudShopActivityResponse(BaseModel):
    meta: PaginatedMeta
    activity: list[ActivityItem]


class CloudShopStatusUpdateRequest(BaseModel):
    status: Literal["ACTIVE", "SUSPENDED", "INACTIVE"]
    reason: str | None = Field(default=None, max_length=500)


class CloudShopStatusUpdateResponse(BaseModel):
    success: bool
    tenant_id: UUID
    previous_status: str
    new_status: str
    message: str


class ShopWithoutSubscriptionItem(BaseModel):
    tenant_id: UUID
    name: str
    business_name: str
    status: str
    created_at: datetime
    subscription_configuration_status: Literal["MISSING", "INCOMPLETE"]
    subscription_id: UUID | None = None
    missing_fields: list[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ShopsWithoutSubscriptionResponse(BaseModel):
    meta: PaginatedMeta
    shops: list[ShopWithoutSubscriptionItem]



# ============================================================
# C. SHOP USER MANAGEMENT SCHEMAS
# ============================================================

class CloudUserListItem(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    phone: str
    email: str | None
    status: str
    role_name: str | None = None
    last_login_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CloudUserListResponse(BaseModel):
    meta: PaginatedMeta
    users: list[CloudUserListItem]


class CloudUserDetailResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    phone: str
    email: str | None
    status: str
    role_name: str | None = None
    role_id: UUID | None = None
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CloudUserStatusUpdateRequest(BaseModel):
    status: Literal["ACTIVE", "INACTIVE", "SUSPENDED"]
    reason: str | None = Field(default=None, max_length=500)


class CloudUserStatusUpdateResponse(BaseModel):
    success: bool
    user_id: UUID
    tenant_id: UUID
    previous_status: str
    new_status: str
    message: str


class CloudUserAccessResetRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class CloudUserAccessResetResponse(BaseModel):
    success: bool
    user_id: UUID
    tenant_id: UUID
    status: Literal["initiated", "pending_integration", "completed"]
    message: str
    notification_delivery_supported: bool = False
    details: str


# ============================================================
# D. PRODUCT AND INVENTORY SCHEMAS
# ============================================================

class CloudProductVariantItem(BaseModel):
    id: UUID
    product_id: UUID
    package_quantity: Decimal
    unit: str
    barcode: str | None
    sku: str | None
    selling_price: Decimal
    offer_price: Decimal | None
    tax_rate: Decimal
    stock_quantity: Decimal
    low_stock_threshold: Decimal
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CloudProductListItem(BaseModel):
    id: UUID
    tenant_id: UUID
    category_id: UUID | None
    name: str
    description: str | None
    status: str
    variant_count: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CloudProductListResponse(BaseModel):
    meta: PaginatedMeta
    products: list[CloudProductListItem]


class CloudProductDetailResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    category_id: UUID | None
    name: str
    description: str | None
    status: str
    variants: list[CloudProductVariantItem]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CloudStockSummaryResponse(BaseModel):
    tenant_id: UUID
    total_products: int
    total_variants: int
    total_stock_units: Decimal
    low_stock_variants_count: int
    out_of_stock_variants_count: int
    total_inventory_value: Decimal


class ProductUsageItem(BaseModel):
    product_id: UUID
    product_name: str
    units_sold: Decimal
    revenue_generated: Decimal


class CloudProductUsageResponse(BaseModel):
    tenant_id: UUID
    top_selling_products: list[ProductUsageItem]
    total_distinct_products_sold: int
    total_catalog_products: int
    catalog_utilization_percent: Decimal


# ============================================================
# E. CUSTOMER SCHEMAS
# ============================================================

class CloudCustomerListItem(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    phone: str
    status: str
    created_at: datetime
    updated_at: datetime
    kadan_balance: Decimal | None = None

    model_config = ConfigDict(from_attributes=True)


class CloudCustomerListResponse(BaseModel):
    meta: PaginatedMeta
    customers: list[CloudCustomerListItem]


# ============================================================
# F. BILLING SCHEMAS
# ============================================================

class CloudShopBillingSummary(BaseModel):
    tenant_id: UUID
    total_bills_count: int
    completed_bills_count: int
    cancelled_bills_count: int
    total_billed_amount: Decimal
    total_collected_amount: Decimal
    total_discount_given: Decimal
    total_tax_collected: Decimal
    total_outstanding_credit: Decimal


class CloudBillItemResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    bill_number: str
    customer_id: UUID | None
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    paid_amount: Decimal
    status: str
    created_by: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CloudBillListResponse(BaseModel):
    meta: PaginatedMeta
    bills: list[CloudBillItemResponse]


# ============================================================
# G. SUBSCRIPTION SCHEMAS
# ============================================================

class CloudSubscriptionDetail(BaseModel):
    id: UUID
    tenant_id: UUID
    plan: str
    status: str
    start_date: datetime
    end_date: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CloudShopSubscriptionItem(BaseModel):
    id: UUID
    tenant_id: UUID
    shop_name: str
    business_name: str
    shop_status: str
    plan: str
    status: str
    start_date: datetime
    end_date: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CloudShopSubscriptionListResponse(BaseModel):
    meta: PaginatedMeta
    subscriptions: list[CloudShopSubscriptionItem]



class CloudSubscriptionHistoryResponse(BaseModel):
    tenant_id: UUID
    current_subscription: CloudSubscriptionDetail | None
    history_events: list[ActivityItem]
    history_tracking_note: str


SUPPORTED_SUBSCRIPTION_PLANS: set[str] = {"SHOPFLOW", "TRIAL"}
PERMITTED_ACTIVATION_STATUSES: set[str] = {"ACTIVE"}


class CloudSubscriptionChangeRequest(BaseModel):
    new_plan: str = Field(
        ...,
        min_length=2,
        max_length=50,
        description="Supported subscription plan (SHOPFLOW, TRIAL).",
        examples=["SHOPFLOW"],
    )
    end_date: datetime | None = None
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("new_plan")
    @classmethod
    def validate_new_plan(cls, v: str) -> str:
        clean = v.strip().upper() if v else ""
        if clean == "TRAIL":
            clean = "TRIAL"
        if clean not in SUPPORTED_SUBSCRIPTION_PLANS:
            raise ValueError(
                f"Unsupported plan '{v}'. Supported plans are: {', '.join(sorted(SUPPORTED_SUBSCRIPTION_PLANS))}"
            )
        return clean


class CloudSubscriptionActivationRequest(BaseModel):
    plan: str = Field(
        ...,
        description="Supported subscription plan (SHOPFLOW, TRIAL).",
        examples=["SHOPFLOW"],
    )
    status: Literal["ACTIVE"] = Field(
        default="ACTIVE",
        description="Permitted activation status. Must be 'ACTIVE'.",
        examples=["ACTIVE"],
    )
    start_date: datetime = Field(
        ...,
        description="Timezone-aware start datetime (e.g. ISO 8601 with UTC 'Z' or offset).",
        examples=["2026-10-22T00:00:00Z"],
    )
    end_date: datetime = Field(
        ...,
        description="Timezone-aware end datetime strictly later than start_date.",
        examples=["2027-10-22T00:00:00Z"],
    )
    reason: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Non-empty explanation for administrative activation.",
        examples=["Initial shop onboarding and plan activation by admin."],
    )

    @field_validator("plan")
    @classmethod
    def validate_plan(cls, v: str) -> str:
        clean = v.strip().upper() if v else ""
        if clean == "TRAIL":
            clean = "TRIAL"
        if clean not in SUPPORTED_SUBSCRIPTION_PLANS:
            raise ValueError(
                f"Unsupported plan '{v}'. Supported plans are: {', '.join(sorted(SUPPORTED_SUBSCRIPTION_PLANS))}"
            )
        return clean

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, v: Any) -> str:
        if v is None:
            return "ACTIVE"
        if isinstance(v, str):
            clean = v.strip().upper()
            if clean not in PERMITTED_ACTIVATION_STATUSES:
                raise ValueError("Permitted subscription status for activation is 'ACTIVE'.")
            return clean
        return v

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_timezone(cls, v: datetime, info: ValidationInfo) -> datetime:
        if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
            raise ValueError(
                f"{info.field_name} must be a timezone-aware datetime (e.g. ISO 8601 with 'Z' or '+00:00')."
            )
        return v

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("reason must be a non-empty explanation.")
        return v.strip()

    @model_validator(mode="after")
    def validate_date_range(self) -> "CloudSubscriptionActivationRequest":
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be strictly later than start_date")
        return self


class CloudSubscriptionActivationResponse(BaseModel):
    success: bool = True
    subscription_id: UUID
    tenant_id: UUID
    plan: str
    status: str
    start_date: datetime
    end_date: datetime
    created_at: datetime
    updated_at: datetime
    message: str = "Subscription activated successfully"

    model_config = ConfigDict(from_attributes=True)


class CloudSubscriptionActionRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
    end_date: datetime | None = None


class CloudSubscriptionOperationResponse(BaseModel):
    success: bool
    subscription_id: UUID
    tenant_id: UUID
    plan: str
    status: str
    start_date: datetime
    end_date: datetime | None
    message: str


# ============================================================
# H. AUDIT LOGS, USAGE, SUPPORT SCHEMAS
# ============================================================

class CloudAuditLogItem(BaseModel):
    id: UUID
    tenant_id: UUID
    user_id: UUID | None
    action: str
    entity_type: str | None
    entity_id: UUID | None
    description: str | None
    old_values: dict[str, Any] | None = None
    new_values: dict[str, Any] | None = None
    ip_address: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CloudAuditLogListResponse(BaseModel):
    meta: PaginatedMeta
    audit_logs: list[CloudAuditLogItem]


class CloudShopUsageResponse(BaseModel):
    tenant_id: UUID
    total_bills: int
    total_products: int
    total_users: int
    total_customers: int
    total_audit_events: int
    active_days_count: int
    subscription_plan: str | None
    calculated_at: datetime


class CloudSupportResponse(BaseModel):
    supported: bool = False
    message: str
    tenant_id: UUID
    tickets: list[Any] = []
