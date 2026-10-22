from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.bill import Bill
from app.models.payment import Payment
from app.models.kadan_account import KadanAccount


class CustomerRepository:

    async def get_customers(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ):
        result = await db.execute(
            select(Customer)
            .where(
                Customer.tenant_id == tenant_id,
                Customer.status == "ACTIVE",
            )
            .order_by(Customer.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        return list(result.scalars().all())

    async def get_customer_by_id(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        customer_id: UUID,
    ):
        result = await db.execute(
            select(Customer)
            .where(
                Customer.id == customer_id,
                Customer.tenant_id == tenant_id,
                Customer.status == "ACTIVE",
            )
        )

        return result.scalar_one_or_none()

    async def get_customer_bill_count(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        customer_id: UUID,
    ):
        result = await db.execute(
            select(func.count(Bill.id))
            .where(
                Bill.tenant_id == tenant_id,
                Bill.customer_id == customer_id,
            )
        )

        return result.scalar_one() or 0

    async def get_customer_total_purchase(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        customer_id: UUID,
    ):
        result = await db.execute(
            select(
                func.coalesce(
                    func.sum(Bill.total_amount),
                    Decimal("0.00"),
                )
            )
            .where(
                Bill.tenant_id == tenant_id,
                Bill.customer_id == customer_id,
                Bill.status != "CANCELLED",
            )
        )

        return result.scalar_one() or Decimal("0.00")

    async def get_customer_kadan_account(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        customer_id: UUID,
    ):
        result = await db.execute(
            select(KadanAccount)
            .where(
                KadanAccount.tenant_id == tenant_id,
                KadanAccount.customer_id == customer_id,
            )
        )

        return result.scalar_one_or_none()

    async def get_customer_bills(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        customer_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ):
        result = await db.execute(
            select(Bill)
            .where(
                Bill.tenant_id == tenant_id,
                Bill.customer_id == customer_id,
            )
            .order_by(Bill.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        return list(result.scalars().all())

    async def get_bill_paid_amount(
        self,
        db: AsyncSession,
        bill_id: UUID,
    ):
        result = await db.execute(
            select(
                func.coalesce(
                    func.sum(Payment.amount),
                    Decimal("0.00"),
                )
            )
            .where(
                Payment.bill_id == bill_id,
                Payment.status == "COMPLETED",
            )
        )

        return result.scalar_one() or Decimal("0.00")

    async def get_customer_credit_bills(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        customer_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ):
        result = await db.execute(
            select(Bill)
            .where(
                Bill.tenant_id == tenant_id,
                Bill.customer_id == customer_id,
                Bill.status != "CANCELLED",
            )
            .order_by(Bill.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        bills = list(result.scalars().all())

        credit_bills = []

        for bill in bills:

            paid_amount = await self.get_bill_paid_amount(
                db=db,
                bill_id=bill.id,
            )

            credit_amount = (
                bill.total_amount - paid_amount
            )

            if credit_amount > Decimal("0.00"):
                credit_bills.append(
                    {
                        "bill": bill,
                        "paid_amount": paid_amount,
                        "credit_amount": credit_amount,
                    }
                )

        return credit_bills


customer_repository = CustomerRepository()