from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.product import Product
from app.models.product_variant import ProductVariant


class ProductRepository:

    # =========================================================
    # CREATE PRODUCT
    # =========================================================

    async def create_product(
        self,
        db: AsyncSession,
        product: Product,
    ) -> Product:

        db.add(product)

        await db.flush()

        return product

    # =========================================================
    # CREATE PRODUCT VARIANT
    # =========================================================

    async def create_variant(
        self,
        db: AsyncSession,
        variant: ProductVariant,
    ) -> ProductVariant:

        db.add(variant)

        await db.flush()

        return variant

    # =========================================================
    # GET PRODUCT BY ID
    # =========================================================

    async def get_product_by_id(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        product_id: UUID,
    ) -> Product | None:

        result = await db.execute(
            select(Product)
            .options(
                selectinload(Product.variants)
            )
            .where(
                Product.id == product_id,
                Product.tenant_id == tenant_id,
                Product.status == "ACTIVE",
            )
        )

        return result.scalar_one_or_none()

    # =========================================================
    # GET ALL PRODUCTS
    # =========================================================

    async def get_all_products(
        self,
        db: AsyncSession,
        tenant_id: UUID,
    ) -> list[Product]:

        result = await db.execute(
            select(Product)
            .options(
                selectinload(Product.variants)
            )
            .where(
                Product.tenant_id == tenant_id,
                Product.status == "ACTIVE",
            )
            .order_by(
                Product.name.asc()
            )
        )

        return list(
            result.scalars().unique().all()
        )

    # =========================================================
    # SEARCH PRODUCTS BY NAME
    # =========================================================

    async def search_products(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        search_term: str,
    ) -> list[Product]:

        search_pattern = f"%{search_term}%"

        result = await db.execute(
            select(Product)
            .options(
                selectinload(Product.variants)
            )
            .where(
                Product.tenant_id == tenant_id,
                Product.status == "ACTIVE",
                Product.name.ilike(search_pattern),
            )
            .order_by(
                Product.name.asc()
            )
        )

        return list(
            result.scalars().unique().all()
        )

    # =========================================================
    # GET VARIANT BY BARCODE
    # =========================================================

    async def get_variant_by_barcode(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        barcode: str,
    ) -> ProductVariant | None:

        result = await db.execute(
            select(ProductVariant)
            .options(
                selectinload(ProductVariant.product)
            )
            .where(
                ProductVariant.tenant_id == tenant_id,
                ProductVariant.barcode == barcode,
                ProductVariant.status == "ACTIVE",
            )
        )

        return result.scalar_one_or_none()

    # =========================================================
    # GET VARIANT BY ID
    # =========================================================

    async def get_variant_by_id(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        variant_id: UUID,
    ) -> ProductVariant | None:

        result = await db.execute(
            select(ProductVariant)
            .options(
                selectinload(ProductVariant.product)
            )
            .where(
                ProductVariant.id == variant_id,
                ProductVariant.tenant_id == tenant_id,
                ProductVariant.status == "ACTIVE",
            )
        )

        return result.scalar_one_or_none()

    # =========================================================
    # GET LOW STOCK VARIANTS
    #
    # A variant is considered low stock when:
    #
    # stock_quantity <= low_stock_threshold
    #
    # Example:
    #
    # Stock = 4
    # Threshold = 5
    # -> LOW_STOCK
    #
    # Stock = 5
    # Threshold = 5
    # -> LOW_STOCK
    #
    # Stock = 0
    # Threshold = 5
    # -> OUT_OF_STOCK
    #
    # Only ACTIVE variants belonging to the current tenant
    # are returned.
    # =========================================================

    async def get_low_stock_variants(
        self,
        db: AsyncSession,
        tenant_id: UUID,
    ) -> list[ProductVariant]:

        result = await db.execute(
            select(ProductVariant)
            .options(
                selectinload(ProductVariant.product)
            )
            .where(
                ProductVariant.tenant_id == tenant_id,
                ProductVariant.status == "ACTIVE",
                ProductVariant.stock_quantity
                <= ProductVariant.low_stock_threshold,
            )
            .order_by(
                ProductVariant.stock_quantity.asc()
            )
        )

        return list(
            result.scalars().all()
        )

    # =========================================================
    # GET ALL VARIANTS ORDERED BY STOCK ASC
    # =========================================================

    async def get_variants_ordered_by_stock(
        self,
        db: AsyncSession,
        tenant_id: UUID,
    ) -> list[ProductVariant]:

        result = await db.execute(
            select(ProductVariant)
            .options(
                selectinload(ProductVariant.product)
            )
            .where(
                ProductVariant.tenant_id == tenant_id,
                ProductVariant.status == "ACTIVE",
            )
            .order_by(
                ProductVariant.stock_quantity.asc(),
                ProductVariant.created_at.desc(),
            )
        )

        return list(
            result.scalars().all()
        )


# =========================================================
# REPOSITORY INSTANCE
# =========================================================

product_repository = ProductRepository()