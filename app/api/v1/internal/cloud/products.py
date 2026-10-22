from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.api.v1.internal.cloud.auth import verify_cloud_service_token
from app.api.v1.internal.cloud.schemas import (
    CloudProductDetailResponse,
    CloudProductListItem,
    CloudProductListResponse,
    CloudProductUsageResponse,
    CloudProductVariantItem,
    CloudStockSummaryResponse,
    PaginatedMeta,
    ProductUsageItem,
)
from app.models.bill import Bill
from app.models.bill_item import BillItem
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.tenant import Tenant

router = APIRouter(
    prefix="/shops/{tenant_id}/products",
    tags=["Cloud Internal - Product & Inventory Management"],
    dependencies=[Depends(verify_cloud_service_token)],
)


@router.get("", response_model=CloudProductListResponse)
async def list_shop_products(
    tenant_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status_filter: str | None = Query(None, alias="status"),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    List products scoped to the shop with bounded pagination and optional filtering.
    """
    tenant_res = await db.execute(select(Tenant.id).where(Tenant.id == tenant_id))
    if not tenant_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found",
        )

    # Subquery for variant count to prevent N+1
    variant_count_sub = (
        select(
            ProductVariant.product_id,
            func.count(ProductVariant.id).label("v_count"),
        )
        .where(ProductVariant.tenant_id == tenant_id)
        .group_by(ProductVariant.product_id)
        .subquery()
    )

    query = (
        select(Product, func.coalesce(variant_count_sub.c.v_count, 0).label("variant_count"))
        .outerjoin(variant_count_sub, variant_count_sub.c.product_id == Product.id)
        .where(Product.tenant_id == tenant_id)
    )

    count_query = select(func.count(Product.id)).where(Product.tenant_id == tenant_id)

    if status_filter:
        query = query.where(Product.status == status_filter.upper())
        count_query = count_query.where(Product.status == status_filter.upper())

    if search:
        search_pattern = f"%{search.strip()}%"
        query = query.where(Product.name.ilike(search_pattern))
        count_query = count_query.where(Product.name.ilike(search_pattern))

    query = query.order_by(Product.created_at.desc(), Product.id.desc()).limit(limit).offset(offset)

    total_res = await db.execute(count_query)
    total = total_res.scalar() or 0

    results = await db.execute(query)
    rows = results.all()

    product_items = [
        CloudProductListItem(
            id=p.id,
            tenant_id=p.tenant_id,
            category_id=p.category_id,
            name=p.name,
            description=p.description,
            status=p.status,
            variant_count=v_cnt,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p, v_cnt in rows
    ]

    return CloudProductListResponse(
        meta=PaginatedMeta(total=total, limit=limit, offset=offset),
        products=product_items,
    )


# -------------------------------------------------------------
# STATIC ROUTES: Register BEFORE dynamic /{product_id}
# -------------------------------------------------------------

@router.get("/stock/summary", response_model=CloudStockSummaryResponse)
async def get_stock_summary(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Get aggregated inventory stock statistics for the shop.
    """
    tenant_res = await db.execute(select(Tenant.id).where(Tenant.id == tenant_id))
    if not tenant_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found",
        )

    # 1. Total products
    prod_res = await db.execute(
        select(func.count(Product.id)).where(Product.tenant_id == tenant_id)
    )
    total_products = prod_res.scalar() or 0

    # 2. Total variants
    var_res = await db.execute(
        select(func.count(ProductVariant.id)).where(
            ProductVariant.tenant_id == tenant_id
        )
    )
    total_variants = var_res.scalar() or 0

    # 3. Total stock units
    units_res = await db.execute(
        select(
            func.coalesce(func.sum(ProductVariant.stock_quantity), Decimal("0.000"))
        ).where(ProductVariant.tenant_id == tenant_id)
    )
    total_stock_units = units_res.scalar() or Decimal("0.000")

    # 4. Low stock variants
    low_res = await db.execute(
        select(func.count(ProductVariant.id)).where(
            ProductVariant.tenant_id == tenant_id,
            ProductVariant.status == "ACTIVE",
            ProductVariant.stock_quantity <= ProductVariant.low_stock_threshold,
        )
    )
    low_stock_count = low_res.scalar() or 0

    # 5. Out of stock variants
    out_res = await db.execute(
        select(func.count(ProductVariant.id)).where(
            ProductVariant.tenant_id == tenant_id,
            ProductVariant.status == "ACTIVE",
            ProductVariant.stock_quantity <= Decimal("0.000"),
        )
    )
    out_of_stock_count = out_res.scalar() or 0

    # 6. Total inventory value (stock_quantity * selling_price)
    inv_res = await db.execute(
        select(
            func.coalesce(
                func.sum(ProductVariant.stock_quantity * ProductVariant.selling_price),
                Decimal("0.00"),
            )
        ).where(
            ProductVariant.tenant_id == tenant_id,
            ProductVariant.status == "ACTIVE",
        )
    )
    total_inventory_value = inv_res.scalar() or Decimal("0.00")

    return CloudStockSummaryResponse(
        tenant_id=tenant_id,
        total_products=total_products,
        total_variants=total_variants,
        total_stock_units=total_stock_units,
        low_stock_variants_count=low_stock_count,
        out_of_stock_variants_count=out_of_stock_count,
        total_inventory_value=total_inventory_value,
    )


@router.get("/usage", response_model=CloudProductUsageResponse)
async def get_product_usage(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Get product utilization and top sales analytics for the shop.
    """
    tenant_res = await db.execute(select(Tenant.id).where(Tenant.id == tenant_id))
    if not tenant_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found",
        )

    # Total catalog products
    prod_cnt_res = await db.execute(
        select(func.count(Product.id)).where(Product.tenant_id == tenant_id)
    )
    total_catalog = prod_cnt_res.scalar() or 0

    # Top selling products derived from completed bills
    sales_query = (
        select(
            ProductVariant.product_id,
            Product.name,
            func.coalesce(func.sum(BillItem.quantity), Decimal("0.000")).label("units_sold"),
            func.coalesce(func.sum(BillItem.line_total), Decimal("0.00")).label("revenue_gen"),
        )
        .join(Bill, Bill.id == BillItem.bill_id)
        .join(ProductVariant, ProductVariant.id == BillItem.product_variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(
            Bill.tenant_id == tenant_id,
            Bill.status != "CANCELLED",
        )
        .group_by(ProductVariant.product_id, Product.name)
        .order_by(func.sum(BillItem.line_total).desc())
        .limit(10)
    )

    sales_results = await db.execute(sales_query)
    top_items = [
        ProductUsageItem(
            product_id=row[0],
            product_name=row[1],
            units_sold=row[2],
            revenue_generated=row[3],
        )
        for row in sales_results.fetchall()
    ]

    # Total distinct products sold
    sold_cnt_res = await db.execute(
        select(func.count(func.distinct(ProductVariant.product_id)))
        .join(BillItem, BillItem.product_variant_id == ProductVariant.id)
        .join(Bill, Bill.id == BillItem.bill_id)
        .where(
            Bill.tenant_id == tenant_id,
            Bill.status != "CANCELLED",
        )
    )
    total_distinct_sold = sold_cnt_res.scalar() or 0

    utilization = (
        (Decimal(str(total_distinct_sold)) / Decimal(str(total_catalog)) * Decimal("100.00")).quantize(Decimal("0.01"))
        if total_catalog > 0
        else Decimal("0.00")
    )

    return CloudProductUsageResponse(
        tenant_id=tenant_id,
        top_selling_products=top_items,
        total_distinct_products_sold=total_distinct_sold,
        total_catalog_products=total_catalog,
        catalog_utilization_percent=utilization,
    )


# -------------------------------------------------------------
# DYNAMIC ROUTES: Scoped by /{product_id}
# -------------------------------------------------------------

@router.get("/{product_id}", response_model=CloudProductDetailResponse)
async def get_shop_product_detail(
    tenant_id: UUID,
    product_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Get full details of a product and its variants strictly scoped to the tenant.
    """
    query = (
        select(Product)
        .options(selectinload(Product.variants))
        .where(Product.id == product_id, Product.tenant_id == tenant_id)
    )
    result = await db.execute(query)
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found for this shop",
        )

    variant_items = [
        CloudProductVariantItem(
            id=v.id,
            product_id=v.product_id,
            package_quantity=v.package_quantity,
            unit=v.unit,
            barcode=v.barcode,
            sku=v.sku,
            selling_price=v.selling_price,
            offer_price=v.offer_price,
            tax_rate=v.tax_rate,
            stock_quantity=v.stock_quantity,
            low_stock_threshold=v.low_stock_threshold,
            status=v.status,
            created_at=v.created_at,
            updated_at=v.updated_at,
        )
        for v in product.variants
    ]

    return CloudProductDetailResponse(
        id=product.id,
        tenant_id=product.tenant_id,
        category_id=product.category_id,
        name=product.name,
        description=product.description,
        status=product.status,
        variants=variant_items,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


@router.get("/{product_id}/variants", response_model=list[CloudProductVariantItem])
async def get_shop_product_variants(
    tenant_id: UUID,
    product_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Get list of variants for a specific product strictly scoped to the tenant.
    """
    # Verify product belongs to this tenant
    prod_res = await db.execute(
        select(Product.id).where(Product.id == product_id, Product.tenant_id == tenant_id)
    )
    if not prod_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found for this shop",
        )

    query = (
        select(ProductVariant)
        .where(
            ProductVariant.product_id == product_id,
            ProductVariant.tenant_id == tenant_id,
        )
        .order_by(ProductVariant.created_at.asc(), ProductVariant.id.asc())
    )
    result = await db.execute(query)
    variants = result.scalars().all()

    return [
        CloudProductVariantItem(
            id=v.id,
            product_id=v.product_id,
            package_quantity=v.package_quantity,
            unit=v.unit,
            barcode=v.barcode,
            sku=v.sku,
            selling_price=v.selling_price,
            offer_price=v.offer_price,
            tax_rate=v.tax_rate,
            stock_quantity=v.stock_quantity,
            low_stock_threshold=v.low_stock_threshold,
            status=v.status,
            created_at=v.created_at,
            updated_at=v.updated_at,
        )
        for v in variants
    ]
