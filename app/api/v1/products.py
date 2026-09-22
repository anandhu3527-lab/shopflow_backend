from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_roles

from app.schemas.product import (
    BarcodeProductResponse,
    LowStockAlertResponse,
    ProductCreateData,
    ProductCreateResponse,
    ProductResponse,
    ProductStockResponse,
    ProductUpdateResponse,
    ProductVariantUpdate,
    ProductVariantInventoryUpdate,
    ProductVariantInventoryResponse,
    ProductWithVariantsCreate,
    VariantProductResponse,
)

from app.services.product_service import product_service


# =========================================================
# ROUTER
# =========================================================

router = APIRouter(
    prefix="/products",
    tags=["Products"],
)


# =========================================================
# CREATE PRODUCT
# =========================================================

@router.post(
    "",
    response_model=ProductCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_product(
    data: ProductWithVariantsCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["OWNER", "MANAGER"])),
):

    tenant_id = current_user["tenant_id"]

    product = await product_service.create_product(
        db=db,
        tenant_id=tenant_id,
        user_id=current_user["user_id"],
        data=data,
    )

    return ProductCreateResponse(
        type="success",
        message="Product created successfully",
        data=ProductCreateData(
            product_id=product.id
        )
    )


# =========================================================
# GET ALL PRODUCTS
# =========================================================

@router.get(
    "",
    response_model=list[ProductResponse],
)
async def get_all_products(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):

    tenant_id = current_user["tenant_id"]

    products = await product_service.get_all_products(
        db=db,
        tenant_id=tenant_id,
    )

    return products


# =========================================================
# SEARCH PRODUCTS BY NAME
# =========================================================

@router.get(
    "/search",
    response_model=list[ProductResponse],
)
async def search_products(
    q: str = Query(
        ...,
        min_length=1,
        max_length=100,
        description="Product name to search for",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):

    tenant_id = current_user["tenant_id"]

    products = await product_service.search_products(
        db=db,
        tenant_id=tenant_id,
        search_term=q,
    )

    return products


# =========================================================
# LOW STOCK ALERTS
#
# GET /api/v1/products/low-stock
#
# Returns ACTIVE variants where:
#
# stock_quantity <= low_stock_threshold
#
# Example:
#
# Stock = 3
# Threshold = 5
# -> LOW_STOCK
#
# Stock = 0
# Threshold = 5
# -> OUT_OF_STOCK
# =========================================================

@router.get(
    "/low-stock",
    response_model=list[LowStockAlertResponse],
)
async def get_low_stock_alerts(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):

    tenant_id = current_user["tenant_id"]

    alerts = await product_service.get_low_stock_alerts(
        db=db,
        tenant_id=tenant_id,
    )

    return alerts


# =========================================================
# GET ALL VARIANTS ORDERED BY STOCK ASC
#
# GET /api/v1/products/stock
#
# Returns all ACTIVE variants for the tenant ordered by
# stock_quantity ASC (lowest stock first).
# =========================================================

@router.get(
    "/stock",
    response_model=list[ProductStockResponse],
)
async def get_stock_overview(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):

    tenant_id = current_user["tenant_id"]

    return await product_service.get_stock_overview(
        db=db,
        tenant_id=tenant_id,
    )


# =========================================================
# GET PRODUCT BY BARCODE
# =========================================================

@router.get(
    "/barcode/{barcode}",
    response_model=BarcodeProductResponse,
)
async def get_product_by_barcode(
    barcode: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):

    tenant_id = current_user["tenant_id"]

    variant = await product_service.get_product_by_barcode(
        db=db,
        tenant_id=tenant_id,
        barcode=barcode,
    )

    return BarcodeProductResponse(
        product_id=variant.product_id,
        variant_id=variant.id,
        product_name=variant.product.name,
        package_quantity=variant.package_quantity,
        unit=variant.unit,
        barcode=variant.barcode,
        selling_price=variant.selling_price,
        offer_price=variant.offer_price,
        tax_rate=variant.tax_rate,
        stock_quantity=variant.stock_quantity,
        low_stock_threshold=variant.low_stock_threshold,
    )


# =========================================================
# GET PRODUCT VARIANT BY ID
# =========================================================

@router.get(
    "/variant/{variant_id}",
    response_model=VariantProductResponse,
)
async def get_variant_by_id(
    variant_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):

    tenant_id = current_user["tenant_id"]

    variant = await product_service.get_variant_by_id(
        db=db,
        tenant_id=tenant_id,
        variant_id=variant_id,
    )

    return VariantProductResponse(
        variant_id=variant.id,
        product_id=variant.product_id,
        tenant_id=variant.tenant_id,

        product_name=variant.product.name,
        product_description=variant.product.description,
        category_id=variant.product.category_id,

        package_quantity=variant.package_quantity,
        unit=variant.unit,

        barcode=variant.barcode,
        sku=variant.sku,

        selling_price=variant.selling_price,
        offer_price=variant.offer_price,

        tax_rate=variant.tax_rate,

        stock_quantity=variant.stock_quantity,
        low_stock_threshold=variant.low_stock_threshold,

        status=variant.status,
    )


# =========================================================
# UPDATE PRODUCT / VARIANT
# =========================================================

@router.patch(
    "/variant/{variant_id}",
    response_model=ProductUpdateResponse,
)
async def update_variant(
    variant_id: UUID,
    data: ProductVariantUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["OWNER", "MANAGER"])),
):

    # -----------------------------------------------------
    # Get tenant from authenticated context
    # -----------------------------------------------------

    tenant_id = current_user["tenant_id"]

    try:

        # -------------------------------------------------
        # Update product / variant
        # -------------------------------------------------

        result = await product_service.update_variant(
            db=db,
            tenant_id=tenant_id,
            user_id=current_user["user_id"],
            variant_id=variant_id,
            data=data,
        )

        # -------------------------------------------------
        # Success response
        # -------------------------------------------------

        return ProductUpdateResponse(
            type="success",
            message="Product updated successfully",
            data=result,
            reason=None,
            error=None,
        )

    except HTTPException as exc:

        # -------------------------------------------------
        # Expected application failure
        # -------------------------------------------------

        return ProductUpdateResponse(
            type="failed",
            message="Product update failed",
            data=None,
            reason=str(exc.detail),
            error=None,
        )

    except Exception:

        # -------------------------------------------------
        # Unexpected server error
        # -------------------------------------------------

        return ProductUpdateResponse(
            type="failed",
            message="Product update failed",
            data=None,
            reason=None,
            error="Internal server error",
        )


# =========================================================
# UPDATE PRODUCT VARIANT INVENTORY
# =========================================================

@router.patch(
    "/variants/{variant_id}/inventory",
    response_model=ProductVariantInventoryResponse,
)
async def update_variant_inventory(
    variant_id: UUID,
    data: ProductVariantInventoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["OWNER", "MANAGER", "EMPLOYEE"])),
):

    # -----------------------------------------------------
    # Get tenant from authenticated context
    # -----------------------------------------------------

    tenant_id = current_user["tenant_id"]

    try:
        # -------------------------------------------------
        # Update product variant inventory
        # -------------------------------------------------

        result = await product_service.update_variant_inventory(
            db=db,
            tenant_id=tenant_id,
            user_id=current_user["user_id"],
            variant_id=variant_id,
            data=data,
        )

        # -------------------------------------------------
        # Success response
        # -------------------------------------------------

        return ProductVariantInventoryResponse(
            type="success",
            message="Product variant inventory updated successfully",
            data=result,
            reason=None,
            error=None,
        )

    except HTTPException as exc:
        return ProductVariantInventoryResponse(
            type="failed",
            message="Inventory update failed",
            data=None,
            reason=str(exc.detail),
            error=None,
        )

    except Exception:
        return ProductVariantInventoryResponse(
            type="failed",
            message="Inventory update failed",
            data=None,
            reason=None,
            error="Internal server error",
        )


# =========================================================
# GET PRODUCT BY ID
#
# IMPORTANT:
# This dynamic route must remain AFTER:
#
# /search
# /low-stock
# /barcode/{barcode}
# /variant/{variant_id}
# /variants/{variant_id}/inventory
# =========================================================

@router.get(
    "/{product_id}",
    response_model=ProductResponse,
)
async def get_product_by_id(
    product_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):

    tenant_id = current_user["tenant_id"]

    product = await product_service.get_product_by_id(
        db=db,
        tenant_id=tenant_id,
        product_id=product_id,
    )

    return product