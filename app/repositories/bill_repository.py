from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Integer, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.bill import Bill
from app.models.bill_item import BillItem
from app.models.payment import Payment
from app.models.product_variant import ProductVariant
from app.models.customer import Customer
from app.models.kadan_account import KadanAccount
from app.models.kadan_transaction import KadanTransaction


class BillRepository:

    # ============================================================
    # GET PRODUCT VARIANTS FOR BILLING
    # ============================================================

    async def get_variants_for_billing(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        variant_ids: list[UUID],
    ):
        result = await db.execute(
            select(ProductVariant)
            .options(
                selectinload(ProductVariant.product)
            )
            .where(
                ProductVariant.id.in_(variant_ids),
                ProductVariant.tenant_id == tenant_id,
                ProductVariant.status == "ACTIVE",
            )
            # Lock the variants while creating the bill.
            # This helps prevent two simultaneous bills from
            # reducing the same stock incorrectly.
            .with_for_update()
        )

        return list(
            result.scalars().all()
        )

    # ============================================================
    # GET CUSTOMER BY PHONE
    # ============================================================

    async def get_customer_by_phone(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        phone: str,
    ):
        result = await db.execute(
            select(Customer)
            .where(
                Customer.tenant_id == tenant_id,
                Customer.phone == phone,
                Customer.status == "ACTIVE",
            )
        )

        return result.scalar_one_or_none()

    # ============================================================
    # CREATE CUSTOMER
    # ============================================================

    async def create_customer(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        name: str,
        phone: str,
    ):
        customer = Customer(
            tenant_id=tenant_id,
            name=name,
            phone=phone,
            status="ACTIVE",
        )

        db.add(customer)

        await db.flush()

        return customer

    # ============================================================
    # GET HIGHEST BILL NUMBER
    #
    # Existing database:
    #
    # BILL-000001
    # BILL-000002
    # BILL-000003
    # BILL-000004
    # BILL-000005
    # 1
    # 2
    # 3
    #
    # This query ONLY looks at BILL-XXXXXX format.
    #
    # Result:
    #
    # 5
    #
    # Service then generates:
    #
    # BILL-000006
    # ============================================================

    async def get_latest_bill_number(
        self,
        db: AsyncSession,
        tenant_id: UUID,
    ):
        # Serialize bill generation for this tenant using a row lock
        from app.models.tenant import Tenant
        await db.execute(
            select(Tenant.id)
            .where(Tenant.id == tenant_id)
            .with_for_update()
        )

        result = await db.execute(
            select(
                func.max(
                    func.cast(
                        func.substring(
                            Bill.bill_number,
                            6,
                        ),
                        Integer,
                    )
                )
            )
            .where(
                Bill.tenant_id == tenant_id,
                Bill.bill_number.like("BILL-%"),
            )
        )

        return result.scalar_one_or_none()

    # ============================================================
    # CREATE BILL
    # ============================================================

    async def create_bill(
        self,
        db: AsyncSession,
        bill: Bill,
    ):
        db.add(bill)

        await db.flush()

        return bill

    # ============================================================
    # CREATE SINGLE BILL ITEM
    # ============================================================

    async def create_bill_item(
        self,
        db: AsyncSession,
        bill_item: BillItem,
    ):
        db.add(bill_item)

        await db.flush()

        return bill_item

    # ============================================================
    # CREATE MULTIPLE BILL ITEMS
    # ============================================================

    async def create_bill_items(
        self,
        db: AsyncSession,
        bill_items: list[BillItem],
    ):
        db.add_all(bill_items)

        await db.flush()

        return bill_items

    # ============================================================
    # CREATE PAYMENT
    # ============================================================

    async def create_payment(
        self,
        db: AsyncSession,
        payment: Payment,
    ):
        db.add(payment)

        await db.flush()

        return payment

    # ============================================================
    # GET KADAN ACCOUNT
    # ============================================================

    async def get_kadan_account(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        customer_id: UUID,
        for_update: bool = False,
    ):
        query = (
            select(KadanAccount)
            .where(
                KadanAccount.tenant_id == tenant_id,
                KadanAccount.customer_id == customer_id,
                KadanAccount.status == "ACTIVE",
            )
        )

        # Lock Kadan account when updating the balance.
        if for_update:
            query = query.with_for_update()

        result = await db.execute(query)

        return result.scalar_one_or_none()

    # ============================================================
    # CREATE KADAN ACCOUNT
    # ============================================================

    async def create_kadan_account(
        self,
        db: AsyncSession,
        kadan_account: KadanAccount,
    ):
        db.add(kadan_account)

        await db.flush()

        return kadan_account

    # ============================================================
    # CREATE KADAN TRANSACTION
    # ============================================================

    async def create_kadan_transaction(
        self,
        db: AsyncSession,
        transaction: KadanTransaction,
    ):
        db.add(transaction)

        await db.flush()

        return transaction

    # ============================================================
    # UPDATE STOCK
    # ============================================================

    async def update_stock(
        self,
        variant: ProductVariant,
        quantity: Decimal,
    ):
        variant.stock_quantity -= quantity

        return variant

    # ============================================================
    # GET BILL BY ID
    # ============================================================

    async def get_bill_by_id(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        bill_id: UUID,
    ):
        result = await db.execute(
            select(Bill)
            .options(
                selectinload(Bill.items),
                selectinload(Bill.payments),
                selectinload(Bill.customer),
            )
            .where(
                Bill.id == bill_id,
                Bill.tenant_id == tenant_id,
            )
        )

        return result.scalar_one_or_none()

    # ============================================================
    # GET BILL BY BILL NUMBER
    # ============================================================

    async def get_bill_by_number(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        bill_number: str,
    ):
        result = await db.execute(
            select(Bill)
            .options(
                selectinload(Bill.items),
                selectinload(Bill.payments),
                selectinload(Bill.customer),
            )
            .where(
                Bill.tenant_id == tenant_id,
                Bill.bill_number == bill_number,
            )
        )

        return result.scalar_one_or_none()

    # ============================================================
    # GET BILLS
    # ============================================================

    async def get_bills(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ):
        result = await db.execute(
            select(Bill)
            .options(
                selectinload(Bill.items),
                selectinload(Bill.payments),
                selectinload(Bill.customer),
            )
            .where(
                Bill.tenant_id == tenant_id
            )
            .order_by(
                Bill.created_at.desc()
            )
            .limit(limit)
            .offset(offset)
        )

        return list(
            result.scalars().unique().all()
        )


    # ============================================================
    # DATE SUMMARY STATS
    # ============================================================

    async def get_date_summary_stats(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        start_date: datetime,
        end_date: datetime,
    ):
        result = await db.execute(
            select(
                func.count(Bill.id),
                func.coalesce(
                    func.sum(Bill.total_amount),
                    Decimal("0.00"),
                ),
            )
            .where(
                Bill.tenant_id == tenant_id,
                Bill.status != "CANCELLED",
                Bill.created_at >= start_date,
                Bill.created_at < end_date,
            )
        )

        row = result.first()
        return {
            "total_bills": row[0] or 0,
            "total_sales": row[1] or Decimal("0.00"),
        }

    # ============================================================
    # GET BILLS BY DATE RANGE
    # ============================================================

    async def get_bills_by_date_range(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        start_date: datetime,
        end_date: datetime,
    ):
        result = await db.execute(
            select(Bill)
            .where(
                Bill.tenant_id == tenant_id,
                Bill.created_at >= start_date,
                Bill.created_at < end_date,
            )
            .order_by(Bill.created_at.desc())
        )

        return list(result.scalars().all())


# ================================================================
# REPOSITORY INSTANCE
# ================================================================

bill_repository = BillRepository()