from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


# =========================================================
# PRODUCT CREATE
# =========================================================

class ProductCreate(BaseModel):

    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
    )

    description: str | None = Field(
        default=None,
        max_length=2000,
    )

    category_id: UUID


# =========================================================
# PRODUCT VARIANT CREATE
# =========================================================

class ProductVariantCreate(BaseModel):

    package_quantity: Decimal = Field(
        ...,
        gt=0,
    )

    unit: str = Field(
        ...,
        min_length=1,
        max_length=30,
    )

    barcode: str | None = Field(
        default=None,
        max_length=50,
    )

    sku: str | None = Field(
        default=None,
        max_length=100,
    )

    selling_price: Decimal = Field(
        ...,
        ge=0,
    )

    offer_price: Decimal | None = Field(
        default=None,
        ge=0,
    )

    tax_rate: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        le=100,
    )

    stock_quantity: Decimal = Field(
        ...,
        ge=0,
    )

    low_stock_threshold: Decimal = Field(
        ...,
        ge=0,
    )


# =========================================================
# PRODUCT + VARIANTS CREATE
# =========================================================

class ProductWithVariantsCreate(BaseModel):

    product: ProductCreate

    variants: list[ProductVariantCreate] = Field(
        ...,
        min_length=1,
    )


# =========================================================
# PRODUCT CREATE RESPONSE
# =========================================================

class ProductCreateData(BaseModel):
    product_id: UUID

class ProductCreateResponse(BaseModel):
    type: str
    message: str
    data: ProductCreateData


# =========================================================
# PRODUCT VARIANT RESPONSE
# =========================================================

class ProductVariantResponse(BaseModel):

    id: UUID
    product_id: UUID
    tenant_id: UUID

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

    model_config = {
        "from_attributes": True
    }


# =========================================================
# PRODUCT RESPONSE
# =========================================================

class ProductResponse(BaseModel):

    id: UUID
    tenant_id: UUID
    category_id: UUID | None

    name: str
    description: str | None

    status: str

    variants: list[ProductVariantResponse]

    model_config = {
        "from_attributes": True
    }


# =========================================================
# BARCODE PRODUCT RESPONSE
# =========================================================

class BarcodeProductResponse(BaseModel):

    product_id: UUID
    variant_id: UUID

    product_name: str

    package_quantity: Decimal
    unit: str

    barcode: str

    selling_price: Decimal
    offer_price: Decimal | None

    tax_rate: Decimal

    stock_quantity: Decimal
    low_stock_threshold: Decimal


# =========================================================
# VARIANT PRODUCT RESPONSE
# =========================================================

class VariantProductResponse(BaseModel):

    variant_id: UUID
    product_id: UUID
    tenant_id: UUID

    # Product details

    product_name: str
    product_description: str | None
    category_id: UUID | None

    # Variant details

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


# =========================================================
# LOW STOCK ALERT RESPONSE
# =========================================================

class LowStockAlertResponse(BaseModel):

    variant_id: UUID
    product_id: UUID

    product_name: str

    package_quantity: Decimal
    unit: str

    barcode: str | None
    sku: str | None

    stock_quantity: Decimal
    low_stock_threshold: Decimal

    selling_price: Decimal
    offer_price: Decimal | None

    alert_type: str


# =========================================================
# PRODUCT STOCK RESPONSE
# =========================================================

class ProductStockResponse(BaseModel):

    variant_id: UUID
    product_id: UUID

    product_name: str

    package_quantity: Decimal
    unit: str

    barcode: str | None
    sku: str | None

    stock_quantity: Decimal
    low_stock_threshold: Decimal

    selling_price: Decimal
    offer_price: Decimal | None

    status: str


# =========================================================
# PRODUCT / VARIANT UPDATE
# =========================================================

class ProductVariantUpdate(BaseModel):

    # -----------------------------------------------------
    # Product details
    # -----------------------------------------------------

    product_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )

    description: str | None = Field(
        default=None,
        max_length=2000,
    )

    category_id: UUID | None = None

    # -----------------------------------------------------
    # Variant details
    # -----------------------------------------------------

    package_quantity: Decimal | None = Field(
        default=None,
        gt=0,
    )

    unit: str | None = Field(
        default=None,
        min_length=1,
        max_length=30,
    )

    barcode: str | None = Field(
        default=None,
        max_length=50,
    )

    sku: str | None = Field(
        default=None,
        max_length=100,
    )

    selling_price: Decimal | None = Field(
        default=None,
        ge=0,
    )

    offer_price: Decimal | None = Field(
        default=None,
        ge=0,
    )

    tax_rate: Decimal | None = Field(
        default=None,
        ge=0,
        le=100,
    )

    stock_quantity: Decimal | None = Field(
        default=None,
        ge=0,
    )

    low_stock_threshold: Decimal | None = Field(
        default=None,
        ge=0,
    )


# =========================================================
# PRODUCT VARIANT INVENTORY UPDATE
# =========================================================

class ProductVariantInventoryUpdate(BaseModel):

    selling_price: Decimal | None = Field(
        default=None,
        ge=0,
    )

    offer_price: Decimal | None = Field(
        default=None,
        ge=0,
    )

    stock_quantity: Decimal | None = Field(
        default=None,
        ge=0,
    )


# =========================================================
# PRODUCT VARIANT INVENTORY RESPONSE
# =========================================================

class ProductVariantInventoryResponse(BaseModel):

    type: str
    message: str
    
    class InventoryData(BaseModel):
        id: UUID
        product_id: UUID
        selling_price: Decimal
        offer_price: Decimal | None
        stock_quantity: Decimal
    
    data: InventoryData | None = None
    reason: str | None = None
    error: str | None = None


# =========================================================
# PRODUCT UPDATE DATA
# =========================================================

class ProductUpdateData(BaseModel):

    variant_id: UUID

    updated_fields: dict[str, str | None]


# =========================================================
# PRODUCT UPDATE RESPONSE
# =========================================================

class ProductUpdateResponse(BaseModel):

    type: str

    message: str

    data: ProductUpdateData | None = None

    reason: str | None = None

    error: str | None = None