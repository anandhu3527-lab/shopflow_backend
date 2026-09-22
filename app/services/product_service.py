from uuid import UUID

from fastapi import HTTPException, status

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.category import Category
from app.models.product import Product
from app.models.product_variant import ProductVariant

from app.repositories.product_repository import ProductRepository

from app.schemas.product import (
    ProductVariantUpdate,
    ProductWithVariantsCreate,
    ProductVariantInventoryUpdate,
)


class ProductService:

    def __init__(self):
        self.repository = ProductRepository()

    # =====================================================
    # CREATE PRODUCT
    # =====================================================

    async def create_product(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        user_id: UUID,
        data: ProductWithVariantsCreate,
    ):

        try:

            # -------------------------------------------------
            # Validate product name
            # -------------------------------------------------

            product_name = data.product.name.strip()

            if not product_name:

                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Product name cannot be empty",
                )

            # -------------------------------------------------
            # Clean description
            # -------------------------------------------------

            description = (
                data.product.description.strip()
                if data.product.description
                else None
            )

            # -------------------------------------------------
            # Validate category
            # -------------------------------------------------

            result = await db.execute(
                select(Category).where(
                    Category.id == data.product.category_id,
                    Category.tenant_id == tenant_id,
                    Category.status == "ACTIVE",
                )
            )

            category = result.scalar_one_or_none()

            if category is None:

                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid category",
                )

            # -------------------------------------------------
            # Validate variants
            # -------------------------------------------------

            if not data.variants:

                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "At least one product variant "
                        "is required"
                    ),
                )

            # -------------------------------------------------
            # Validate duplicate barcodes
            # -------------------------------------------------

            barcodes: set[str] = set()

            for variant_data in data.variants:

                if variant_data.barcode:

                    barcode = variant_data.barcode.strip()

                    if barcode:

                        if barcode in barcodes:

                            raise HTTPException(
                                status_code=status.HTTP_409_CONFLICT,
                                detail=(
                                    "Duplicate barcode in "
                                    f"request: {barcode}"
                                ),
                            )

                        barcodes.add(barcode)

                        existing_variant = (
                            await self.repository.get_variant_by_barcode(
                                db=db,
                                tenant_id=tenant_id,
                                barcode=barcode,
                            )
                        )

                        if existing_variant:

                            raise HTTPException(
                                status_code=status.HTTP_409_CONFLICT,
                                detail=(
                                    "Barcode already exists: "
                                    f"{barcode}"
                                ),
                            )

            # -------------------------------------------------
            # Validate offer prices
            # -------------------------------------------------

            for variant_data in data.variants:

                if (
                    variant_data.offer_price is not None
                    and variant_data.offer_price
                    > variant_data.selling_price
                ):

                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            "Offer price cannot be greater "
                            "than selling price"
                        ),
                    )

            # -------------------------------------------------
            # Create Product
            # -------------------------------------------------

            product = Product(
                tenant_id=tenant_id,
                category_id=data.product.category_id,
                name=product_name,
                description=description,
                status="ACTIVE",
            )

            await self.repository.create_product(
                db=db,
                product=product,
            )

            # -------------------------------------------------
            # Create Product Variants
            # -------------------------------------------------

            for variant_data in data.variants:

                barcode = (
                    variant_data.barcode.strip()
                    if variant_data.barcode
                    else None
                )

                sku = (
                    variant_data.sku.strip()
                    if variant_data.sku
                    else None
                )

                variant = ProductVariant(
                    tenant_id=tenant_id,
                    product_id=product.id,
                    package_quantity=variant_data.package_quantity,
                    unit=variant_data.unit.strip(),
                    barcode=barcode,
                    sku=sku,
                    selling_price=variant_data.selling_price,
                    offer_price=variant_data.offer_price,
                    tax_rate=variant_data.tax_rate,
                    stock_quantity=variant_data.stock_quantity,
                    low_stock_threshold=variant_data.low_stock_threshold,
                    status="ACTIVE",
                )

                await self.repository.create_variant(
                    db=db,
                    variant=variant,
                )

            # -------------------------------------------------
            # Audit Logs
            # -------------------------------------------------

            from app.services.audit_service import log as audit_log
            await audit_log(
                db=db,
                tenant_id=tenant_id,
                user_id=user_id,
                action="PRODUCT_CREATED",
                entity_type="product",
                entity_id=product.id,
                description=f"Product '{product.name}' created",
                new_values={"name": product.name, "category_id": str(product.category_id)}
            )

            for variant_data in data.variants:
                # We need the inserted variant's ID. Wait, the variant doesn't have ID until flushed?
                pass  # We'll just flush again below to get IDs if needed, but variants are already flushed in repository.create_variant!

            # Actually, let's log the variants too. We already created them.
            # (Wait, variant object is lost in the loop above? Let's just log the product creation to be safe, the variants are part of it).

            # -------------------------------------------------
            # Commit
            # -------------------------------------------------

            await db.commit()

            # -------------------------------------------------
            # Reload product with variants
            # -------------------------------------------------

            result = await db.execute(
                select(Product)
                .options(
                    selectinload(Product.variants)
                )
                .where(
                    Product.id == product.id,
                    Product.tenant_id == tenant_id,
                )
            )

            saved_product = result.scalar_one()

            return saved_product

        except HTTPException:

            await db.rollback()

            raise

        except Exception:

            await db.rollback()

            raise

    # =====================================================
    # GET PRODUCT BY ID
    # =====================================================

    async def get_product_by_id(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        product_id: UUID,
    ) -> Product:

        product = await self.repository.get_product_by_id(
            db=db,
            tenant_id=tenant_id,
            product_id=product_id,
        )

        if product is None:

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found",
            )

        return product

    # =====================================================
    # GET ALL PRODUCTS
    # =====================================================

    async def get_all_products(
        self,
        db: AsyncSession,
        tenant_id: UUID,
    ) -> list[Product]:

        return await self.repository.get_all_products(
            db=db,
            tenant_id=tenant_id,
        )

    # =====================================================
    # SEARCH PRODUCTS BY NAME
    # =====================================================

    async def search_products(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        search_term: str,
    ) -> list[Product]:

        search_term = search_term.strip()

        if not search_term:

            return await self.repository.get_all_products(
                db=db,
                tenant_id=tenant_id,
            )

        return await self.repository.search_products(
            db=db,
            tenant_id=tenant_id,
            search_term=search_term,
        )

    # =====================================================
    # GET PRODUCT BY BARCODE
    # =====================================================

    async def get_product_by_barcode(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        barcode: str,
    ) -> ProductVariant:

        barcode = barcode.strip()

        if not barcode:

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Barcode cannot be empty",
            )

        variant = await self.repository.get_variant_by_barcode(
            db=db,
            tenant_id=tenant_id,
            barcode=barcode,
        )

        if variant is None:

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found for this barcode",
            )

        return variant

    # =====================================================
    # GET PRODUCT VARIANT BY ID
    # =====================================================

    async def get_variant_by_id(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        variant_id: UUID,
    ) -> ProductVariant:

        variant = await self.repository.get_variant_by_id(
            db=db,
            tenant_id=tenant_id,
            variant_id=variant_id,
        )

        if variant is None:

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product variant not found",
            )

        return variant

    # =====================================================
    # GET LOW STOCK ALERTS
    #
    # Variant-level alert:
    #
    # stock_quantity <= low_stock_threshold
    #
    # OUT_OF_STOCK:
    # stock_quantity <= 0
    #
    # LOW_STOCK:
    # stock_quantity > 0
    # and
    # stock_quantity <= threshold
    # =====================================================

    async def get_low_stock_alerts(
        self,
        db: AsyncSession,
        tenant_id: UUID,
    ):

        variants = await self.repository.get_low_stock_variants(
            db=db,
            tenant_id=tenant_id,
        )

        alerts = []

        for variant in variants:

            if variant.stock_quantity <= 0:

                alert_type = "OUT_OF_STOCK"

            else:

                alert_type = "LOW_STOCK"

            alerts.append(
                {
                    "variant_id": variant.id,
                    "product_id": variant.product_id,

                    "product_name": (
                        variant.product.name
                        if variant.product
                        else "Unknown product"
                    ),

                    "package_quantity": variant.package_quantity,
                    "unit": variant.unit,

                    "barcode": variant.barcode,
                    "sku": variant.sku,

                    "stock_quantity": variant.stock_quantity,
                    "low_stock_threshold": (
                        variant.low_stock_threshold
                    ),

                    "selling_price": variant.selling_price,
                    "offer_price": variant.offer_price,

                    "alert_type": alert_type,
                }
            )

        return alerts

    # =====================================================
    # GET STOCK OVERVIEW (ALL ACTIVE, ORDERED BY STOCK ASC)
    # =====================================================

    async def get_stock_overview(
        self,
        db: AsyncSession,
        tenant_id: UUID,
    ) -> list[dict]:

        variants = await self.repository.get_variants_ordered_by_stock(
            db=db,
            tenant_id=tenant_id,
        )

        return [
            {
                "variant_id": variant.id,
                "product_id": variant.product_id,
                "product_name": (
                    variant.product.name
                    if variant.product
                    else "Unknown product"
                ),
                "package_quantity": variant.package_quantity,
                "unit": variant.unit,
                "barcode": variant.barcode,
                "sku": variant.sku,
                "stock_quantity": variant.stock_quantity,
                "low_stock_threshold": variant.low_stock_threshold,
                "selling_price": variant.selling_price,
                "offer_price": variant.offer_price,
                "status": variant.status,
            }
            for variant in variants
        ]

    # =====================================================
    # UPDATE PRODUCT / VARIANT
    # =====================================================

    async def update_variant(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        user_id: UUID,
        variant_id: UUID,
        data: ProductVariantUpdate,
    ) -> dict:

        try:

            # -------------------------------------------------
            # Find variant
            # -------------------------------------------------

            variant = await self.repository.get_variant_by_id(
                db=db,
                tenant_id=tenant_id,
                variant_id=variant_id,
            )

            if variant is None:

                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Product variant not found",
                )

            product = variant.product

            # -------------------------------------------------
            # Save ID BEFORE COMMIT
            # -------------------------------------------------

            saved_variant_id = variant.id

            # -------------------------------------------------
            # Get only fields sent by frontend
            # -------------------------------------------------

            update_data = data.model_dump(
                exclude_unset=True
            )

            # -------------------------------------------------
            # No fields
            # -------------------------------------------------

            if not update_data:

                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No fields provided for update",
                )

            # -------------------------------------------------
            # Track only changed fields
            # -------------------------------------------------

            updated_fields: dict[str, str | None] = {}

            # =================================================
            # PRODUCT NAME
            # =================================================

            if "product_name" in update_data:

                product_name = update_data["product_name"]

                if product_name is None:

                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Product name cannot be null",
                    )

                product_name = product_name.strip()

                if not product_name:

                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Product name cannot be empty",
                    )

                product.name = product_name

                updated_fields["product_name"] = product.name

            # =================================================
            # DESCRIPTION
            # =================================================

            if "description" in update_data:

                description = update_data["description"]

                product.description = (
                    description.strip()
                    if description is not None
                    else None
                )

                updated_fields["description"] = (
                    product.description
                )

            # =================================================
            # CATEGORY
            # =================================================

            if "category_id" in update_data:

                category_id = update_data["category_id"]

                if category_id is None:

                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Category cannot be null",
                    )

                result = await db.execute(
                    select(Category).where(
                        Category.id == category_id,
                        Category.tenant_id == tenant_id,
                        Category.status == "ACTIVE",
                    )
                )

                category = result.scalar_one_or_none()

                if category is None:

                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid category",
                    )

                product.category_id = category_id

                updated_fields["category_id"] = str(
                    category_id
                )

            # =================================================
            # PACKAGE QUANTITY
            # =================================================

            if "package_quantity" in update_data:

                variant.package_quantity = (
                    update_data["package_quantity"]
                )

                updated_fields["package_quantity"] = str(
                    variant.package_quantity
                )

            # =================================================
            # UNIT
            # =================================================

            if "unit" in update_data:

                unit = update_data["unit"]

                if unit is None:

                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Unit cannot be null",
                    )

                unit = unit.strip()

                if not unit:

                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Unit cannot be empty",
                    )

                variant.unit = unit

                updated_fields["unit"] = variant.unit

            # =================================================
            # BARCODE
            # =================================================

            if "barcode" in update_data:

                barcode = update_data["barcode"]

                if barcode is not None:

                    barcode = barcode.strip()

                    if not barcode:

                        barcode = None

                # ---------------------------------------------
                # Check duplicate barcode
                # ---------------------------------------------

                if barcode is not None:

                    existing_variant = (
                        await self.repository.get_variant_by_barcode(
                            db=db,
                            tenant_id=tenant_id,
                            barcode=barcode,
                        )
                    )

                    if (
                        existing_variant is not None
                        and existing_variant.id != variant.id
                    ):

                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail=(
                                f"Barcode already exists: "
                                f"{barcode}"
                            ),
                        )

                variant.barcode = barcode

                updated_fields["barcode"] = (
                    variant.barcode
                )

            # =================================================
            # SKU
            # =================================================

            if "sku" in update_data:

                sku = update_data["sku"]

                if sku is not None:

                    sku = sku.strip()

                    if not sku:

                        sku = None

                variant.sku = sku

                updated_fields["sku"] = variant.sku

            # =================================================
            # SELLING PRICE
            # =================================================

            if "selling_price" in update_data:

                variant.selling_price = (
                    update_data["selling_price"]
                )

                updated_fields["selling_price"] = str(
                    variant.selling_price
                )

            # =================================================
            # OFFER PRICE
            # =================================================

            if "offer_price" in update_data:

                offer_price = update_data["offer_price"]

                variant.offer_price = offer_price

                updated_fields["offer_price"] = (
                    str(offer_price)
                    if offer_price is not None
                    else None
                )

            # =================================================
            # TAX RATE
            # =================================================

            if "tax_rate" in update_data:

                variant.tax_rate = (
                    update_data["tax_rate"]
                )

                updated_fields["tax_rate"] = str(
                    variant.tax_rate
                )

            # =================================================
            # CURRENT STOCK
            # =================================================

            if "stock_quantity" in update_data:

                variant.stock_quantity = (
                    update_data["stock_quantity"]
                )

                updated_fields["stock_quantity"] = str(
                    variant.stock_quantity
                )

            # =================================================
            # LOW STOCK THRESHOLD
            # =================================================

            if "low_stock_threshold" in update_data:

                variant.low_stock_threshold = (
                    update_data["low_stock_threshold"]
                )

                updated_fields["low_stock_threshold"] = str(
                    variant.low_stock_threshold
                )

            # =================================================
            # FINAL OFFER PRICE VALIDATION
            # =================================================

            if (
                variant.offer_price is not None
                and variant.offer_price
                > variant.selling_price
            ):

                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Offer price cannot be greater "
                        "than selling price"
                    ),
                )

            # -------------------------------------------------
            # Capture everything BEFORE commit
            # -------------------------------------------------

            result_data = {
                "variant_id": saved_variant_id,
                "updated_fields": updated_fields,
            }

            # -------------------------------------------------
            # Audit Log
            # -------------------------------------------------

            if updated_fields:
                from app.services.audit_service import log as audit_log
                await audit_log(
                    db=db,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    action="PRODUCT_UPDATED",
                    entity_type="product_variant",
                    entity_id=saved_variant_id,
                    description=f"Product variant updated",
                    new_values=updated_fields,
                )

            # -------------------------------------------------
            # Commit changes
            # -------------------------------------------------

            await db.commit()

            # -------------------------------------------------
            # Return plain dictionary
            # -------------------------------------------------

            return result_data

        except HTTPException:

            await db.rollback()

            raise

        except Exception:

            await db.rollback()

            raise


    # =====================================================
    # UPDATE PRODUCT VARIANT INVENTORY
    # =====================================================

    async def update_variant_inventory(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        user_id: UUID,
        variant_id: UUID,
        data: ProductVariantInventoryUpdate,
    ) -> dict:

        try:
            # -------------------------------------------------
            # Get only fields sent by frontend
            # -------------------------------------------------

            update_data = data.model_dump(
                exclude_unset=True
            )

            if not update_data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="At least one of selling_price, offer_price, or stock_quantity must be provided.",
                )

            # -------------------------------------------------
            # Find variant (implicitly enforces tenant isolation)
            # -------------------------------------------------

            variant = await self.repository.get_variant_by_id(
                db=db,
                tenant_id=tenant_id,
                variant_id=variant_id,
            )

            if variant is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Product variant not found",
                )
                
            # -------------------------------------------------
            # Apply changes in memory
            # -------------------------------------------------
            
            if "selling_price" in update_data:
                variant.selling_price = update_data["selling_price"]
                
            if "offer_price" in update_data:
                variant.offer_price = update_data["offer_price"]
                
            if "stock_quantity" in update_data:
                variant.stock_quantity = update_data["stock_quantity"]
                
            # -------------------------------------------------
            # Final state validation
            # -------------------------------------------------
            
            if (
                variant.offer_price is not None
                and variant.offer_price > variant.selling_price
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Offer price cannot be greater than selling price",
                )
                
            if variant.stock_quantity < 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Stock quantity cannot be negative",
                )

            # -------------------------------------------------
            # Audit Log
            # -------------------------------------------------

            # We can figure out if price or stock changed
            old_vals = {}
            new_vals = {}
            if "selling_price" in update_data:
                new_vals["selling_price"] = update_data["selling_price"]
            if "offer_price" in update_data:
                new_vals["offer_price"] = update_data["offer_price"]
            if "stock_quantity" in update_data:
                new_vals["stock_quantity"] = update_data["stock_quantity"]

            if new_vals:
                from app.services.audit_service import log as audit_log
                await audit_log(
                    db=db,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    action="INVENTORY_UPDATED",
                    entity_type="product_variant",
                    entity_id=variant.id,
                    description=f"Inventory/Price updated for variant",
                    new_values=new_vals,
                )

            # -------------------------------------------------
            # Commit changes
            # -------------------------------------------------

            await db.commit()
            await db.refresh(variant)

            return {
                "id": variant.id,
                "product_id": variant.product_id,
                "selling_price": variant.selling_price,
                "offer_price": variant.offer_price,
                "stock_quantity": variant.stock_quantity,
            }

        except HTTPException:
            await db.rollback()
            raise

        except Exception:
            await db.rollback()
            raise


# =========================================================
# SERVICE INSTANCE
# =========================================================

product_service = ProductService()