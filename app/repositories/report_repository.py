from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.bill import Bill
from app.models.bill_item import BillItem
from app.models.kadan_account import KadanAccount
from app.models.kadan_transaction import KadanTransaction
from app.models.product import Product
from app.models.product_variant import ProductVariant


class ReportRepository:

    async def get_bills_for_period(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        start_date: datetime,
        end_date: datetime,
    ):
        result = await db.execute(
            select(Bill)
            .options(
                selectinload(Bill.payments),
                selectinload(Bill.customer),
            )
            .where(
                Bill.tenant_id == tenant_id,
                Bill.created_at >= start_date,
                Bill.created_at < end_date,
            )
            .order_by(Bill.created_at.desc())
        )

        return list(result.scalars().unique().all())

    async def get_kadan_transactions_for_period(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        start_date: datetime,
        end_date: datetime,
    ):
        result = await db.execute(
            select(KadanTransaction)
            .options(
                selectinload(KadanTransaction.kadan_account)
                .selectinload(KadanAccount.customer),
                selectinload(KadanTransaction.bill)
            )
            .where(
                KadanTransaction.tenant_id == tenant_id,
                KadanTransaction.created_at >= start_date,
                KadanTransaction.created_at < end_date,
            )
            .order_by(KadanTransaction.created_at.desc())
        )

        return list(result.scalars().unique().all())

    async def get_current_kadan_accounts(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        customer_ids: list[UUID],
    ):
        if not customer_ids:
            return []

        result = await db.execute(
            select(KadanAccount)
            .options(
                selectinload(KadanAccount.customer)
            )
            .where(
                KadanAccount.tenant_id == tenant_id,
                KadanAccount.customer_id.in_(customer_ids),
                KadanAccount.status == "ACTIVE",
            )
        )

        return list(result.scalars().unique().all())

    # ----------------------------------------------------------
    # MOST-SOLD PRODUCT REPORTING
    # ----------------------------------------------------------

    def _build_most_sold_query(
        self,
        tenant_id: UUID,
        start_date: datetime,
        end_date: datetime,
    ):
        """
        Build a SQLAlchemy Core aggregation query that returns the top-selling
        product variant by quantity for the given tenant and date range.

        All aggregation happens in PostgreSQL:
            SUM(bill_items.quantity)   → total_quantity_sold
            SUM(bill_items.line_total) → total_sales_value

        Historical pricing is taken from bill_items.unit_price / line_total;
        the current variant.selling_price is NOT used in any calculation here.

        Tie-breaking order:
            1. total_quantity_sold DESC
            2. total_sales_value DESC
            3. product_name ASC
            4. variant_id ASC (deterministic)
        """
        qty_sum = func.sum(BillItem.quantity).label("total_quantity_sold")
        sales_sum = func.sum(BillItem.line_total).label("total_sales_value")

        stmt = (
            select(
                BillItem.product_variant_id.label("variant_id"),
                BillItem.product_id.label("product_id"),
                Product.name.label("product_name"),
                ProductVariant.package_quantity.label("package_quantity"),
                ProductVariant.unit.label("unit"),
                ProductVariant.barcode.label("barcode"),
                ProductVariant.sku.label("sku"),
                qty_sum,
                sales_sum,
            )
            .join(Bill, BillItem.bill_id == Bill.id)
            .join(
                Product,
                BillItem.product_id == Product.id,
            )
            .join(
                ProductVariant,
                BillItem.product_variant_id == ProductVariant.id,
            )
            .where(
                Bill.tenant_id == tenant_id,
                Bill.status == "COMPLETED",
                Bill.created_at >= start_date,
                Bill.created_at < end_date,
                # Exclude items where variant was deleted (SET NULL)
                BillItem.product_variant_id.is_not(None),
                BillItem.product_id.is_not(None),
            )
            .group_by(
                BillItem.product_variant_id,
                BillItem.product_id,
                Product.name,
                ProductVariant.package_quantity,
                ProductVariant.unit,
                ProductVariant.barcode,
                ProductVariant.sku,
            )
            .order_by(
                qty_sum.desc(),
                sales_sum.desc(),
                Product.name.asc(),
                BillItem.product_variant_id.asc(),
            )
        )

        return stmt

    async def get_most_sold_variant_for_period(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        start_date: datetime,
        end_date: datetime,
    ) -> dict | None:
        """
        Return the single top-selling product variant for the given period,
        or None if there were no completed sales.

        Query performs full aggregation inside PostgreSQL (LIMIT 1).
        Tenant isolation enforced via bills.tenant_id filter.
        """
        stmt = self._build_most_sold_query(tenant_id, start_date, end_date).limit(1)
        result = await db.execute(stmt)
        row = result.mappings().first()

        if row is None:
            return None

        total_qty = Decimal(str(row["total_quantity_sold"]))
        total_sales = Decimal(str(row["total_sales_value"]))
        avg_price = (total_sales / total_qty).quantize(Decimal("0.01")) if total_qty else Decimal("0.00")

        return {
            "variant_id": row["variant_id"],
            "product_id": row["product_id"],
            "product_name": row["product_name"],
            "package_quantity": Decimal(str(row["package_quantity"])),
            "unit": row["unit"],
            "barcode": row["barcode"],
            "sku": row["sku"],
            "quantity_sold": total_qty,
            "total_sales_value": total_sales,
            "average_selling_price": avg_price,
        }

    async def get_most_sold_variant_overall(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        start_date: datetime,
        end_date: datetime,
    ) -> dict | None:
        """
        Return the single top-selling product variant across the entire date
        range (used for the 3-month overall summary), or None if no sales.

        Identical aggregation logic to get_most_sold_variant_for_period but
        over the full window without per-month partitioning.
        """
        stmt = self._build_most_sold_query(tenant_id, start_date, end_date).limit(1)
        result = await db.execute(stmt)
        row = result.mappings().first()

        if row is None:
            return None

        total_qty = Decimal(str(row["total_quantity_sold"]))
        total_sales = Decimal(str(row["total_sales_value"]))
        avg_price = (total_sales / total_qty).quantize(Decimal("0.01")) if total_qty else Decimal("0.00")

        return {
            "variant_id": row["variant_id"],
            "product_id": row["product_id"],
            "product_name": row["product_name"],
            "package_quantity": Decimal(str(row["package_quantity"])),
            "unit": row["unit"],
            "barcode": row["barcode"],
            "sku": row["sku"],
            "quantity_sold": total_qty,
            "total_sales_value": total_sales,
            "average_selling_price": avg_price,
        }


report_repository = ReportRepository()
