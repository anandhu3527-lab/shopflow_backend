from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.kadan_account import KadanAccount
from app.models.kadan_transaction import KadanTransaction
from app.models.customer import Customer
from app.models.bill import Bill


class KadanRepository:

    # ========================================================
    # SUMMARY
    # ========================================================

    async def get_kadan_summary(
        self,
        db: AsyncSession,
        tenant_id: UUID,
    ):

        # ----------------------------------------------------
        # Total outstanding Kadan
        # ----------------------------------------------------

        total_result = await db.execute(
            select(
                func.coalesce(
                    func.sum(
                        KadanAccount.outstanding_amount
                    ),
                    Decimal("0.00"),
                )
            )
            .where(
                KadanAccount.tenant_id == tenant_id,
                KadanAccount.status == "ACTIVE",
            )
        )

        total_kadan_amount = (
            total_result.scalar_one()
            or Decimal("0.00")
        )

        # ----------------------------------------------------
        # Total accounts
        # ----------------------------------------------------

        accounts_result = await db.execute(
            select(
                func.count(KadanAccount.id)
            )
            .where(
                KadanAccount.tenant_id == tenant_id,
            )
        )

        total_kadan_accounts = (
            accounts_result.scalar_one()
            or 0
        )

        # ----------------------------------------------------
        # Active accounts
        # ----------------------------------------------------

        active_result = await db.execute(
            select(
                func.count(KadanAccount.id)
            )
            .where(
                KadanAccount.tenant_id == tenant_id,
                KadanAccount.status == "ACTIVE",
                KadanAccount.outstanding_amount > 0,
            )
        )

        active_kadan_accounts = (
            active_result.scalar_one()
            or 0
        )

        # ----------------------------------------------------
        # Settled accounts
        # ----------------------------------------------------

        settled_result = await db.execute(
            select(
                func.count(KadanAccount.id)
            )
            .where(
                KadanAccount.tenant_id == tenant_id,
                KadanAccount.outstanding_amount <= 0,
            )
        )

        settled_kadan_accounts = (
            settled_result.scalar_one()
            or 0
        )

        return {
            "total_kadan_amount": total_kadan_amount,
            "total_customers_with_kadan": active_kadan_accounts,
            "total_kadan_accounts": total_kadan_accounts,
            "active_kadan_accounts": active_kadan_accounts,
            "settled_kadan_accounts": settled_kadan_accounts,
        }

    # ========================================================
    # ALL KADAN ACCOUNTS
    # ========================================================

    async def get_accounts(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ):

        result = await db.execute(
            select(KadanAccount)
            .options(
                selectinload(
                    KadanAccount.customer
                )
            )
            .where(
                KadanAccount.tenant_id == tenant_id,
            )
            .order_by(
                KadanAccount.outstanding_amount.desc()
            )
            .limit(limit)
            .offset(offset)
        )

        return list(
            result.scalars().unique().all()
        )

    # ========================================================
    # CUSTOMER ACCOUNT
    # ========================================================

    async def get_customer_account(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        customer_id: UUID,
        for_update: bool = False,
    ):

        query = (
            select(KadanAccount)
            .options(
                selectinload(
                    KadanAccount.customer
                )
            )
            .where(
                KadanAccount.tenant_id == tenant_id,
                KadanAccount.customer_id == customer_id,
            )
        )

        if for_update:
            query = query.with_for_update()

        result = await db.execute(query)

        return result.scalar_one_or_none()

    # ========================================================
    # TRANSACTIONS FOR CUSTOMER
    # ========================================================

    async def get_customer_transactions(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        customer_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ):

        result = await db.execute(
            select(KadanTransaction)
            .join(
                KadanAccount,
                KadanTransaction.kadan_account_id
                == KadanAccount.id,
            )
            .join(
                Customer,
                KadanAccount.customer_id
                == Customer.id,
            )
            .outerjoin(
                Bill,
                KadanTransaction.bill_id
                == Bill.id,
            )
            .where(
                KadanTransaction.tenant_id == tenant_id,
                KadanAccount.tenant_id == tenant_id,
                KadanAccount.customer_id == customer_id,
            )
            .options(
                selectinload(
                    KadanTransaction.kadan_account
                ).selectinload(
                    KadanAccount.customer
                ),
                selectinload(
                    KadanTransaction.bill
                ),
            )
            .order_by(
                KadanTransaction.created_at.desc()
            )
            .limit(limit)
            .offset(offset)
        )

        return list(
            result.scalars().unique().all()
        )

    # ========================================================
    # SINGLE TRANSACTION
    # ========================================================

    async def get_transaction_by_id(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        transaction_id: UUID,
    ):

        result = await db.execute(
            select(KadanTransaction)
            .join(
                KadanAccount,
                KadanTransaction.kadan_account_id
                == KadanAccount.id,
            )
            .where(
                KadanTransaction.id == transaction_id,
                KadanTransaction.tenant_id == tenant_id,
                KadanAccount.tenant_id == tenant_id,
            )
            .options(
                selectinload(
                    KadanTransaction.kadan_account
                ).selectinload(
                    KadanAccount.customer
                ),
                selectinload(
                    KadanTransaction.bill
                ),
            )
        )

        return result.scalar_one_or_none()

    # ========================================================
    # CREATE TRANSACTION
    # ========================================================

    async def create_transaction(
        self,
        db: AsyncSession,
        transaction: KadanTransaction,
    ):

        db.add(transaction)

        await db.flush()

        return transaction


# ============================================================
# REPOSITORY INSTANCE
# ============================================================

kadan_repository = KadanRepository()