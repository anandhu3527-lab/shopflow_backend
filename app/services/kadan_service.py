from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kadan_transaction import KadanTransaction

from app.repositories.kadan_repository import (
    kadan_repository,
)

from app.schemas.kadan import (
    KadanPaymentCreate,
)


class KadanService:

    # ========================================================
    # MONEY
    # ========================================================

    @staticmethod
    def money(value: Decimal) -> Decimal:

        return value.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    # ========================================================
    # SUMMARY
    # ========================================================

    async def get_summary(
        self,
        db: AsyncSession,
        tenant_id: UUID,
    ):

        return await kadan_repository.get_kadan_summary(
            db=db,
            tenant_id=tenant_id,
        )

    # ========================================================
    # ALL ACCOUNTS
    # ========================================================

    async def get_accounts(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        limit: int,
        offset: int,
    ):

        accounts = await kadan_repository.get_accounts(
            db=db,
            tenant_id=tenant_id,
            limit=limit,
            offset=offset,
        )

        response = []

        for account in accounts:

            customer = account.customer

            response.append(
                {
                    "account_id": account.id,
                    "customer_id": account.customer_id,
                    "customer_name": customer.name,
                    "customer_phone": customer.phone,
                    "outstanding_amount": (
                        account.outstanding_amount
                        or Decimal("0.00")
                    ),
                    "status": account.status,
                    "created_at": account.created_at,
                }
            )

        return response

    # ========================================================
    # SINGLE CUSTOMER ACCOUNT
    # ========================================================

    async def get_customer_account(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        customer_id: UUID,
    ):

        account = await kadan_repository.get_customer_account(
            db=db,
            tenant_id=tenant_id,
            customer_id=customer_id,
        )

        if account is None:

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Kadan account not found for this customer",
            )

        customer = account.customer

        outstanding = (
            account.outstanding_amount
            or Decimal("0.00")
        )

        return {
            "account_id": account.id,
            "customer_id": account.customer_id,
            "customer_name": customer.name,
            "customer_phone": customer.phone,
            "total_kadan_amount": outstanding,
            "outstanding_amount": outstanding,
            "status": account.status,
            "created_at": account.created_at,
        }

    # ========================================================
    # CUSTOMER TRANSACTIONS
    # ========================================================

    async def get_customer_transactions(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        customer_id: UUID,
        limit: int,
        offset: int,
    ):

        account = await kadan_repository.get_customer_account(
            db=db,
            tenant_id=tenant_id,
            customer_id=customer_id,
        )

        if account is None:

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Kadan account not found for this customer",
            )

        transactions = (
            await kadan_repository.get_customer_transactions(
                db=db,
                tenant_id=tenant_id,
                customer_id=customer_id,
                limit=limit,
                offset=offset,
            )
        )

        response = []

        for transaction in transactions:

            account = transaction.kadan_account
            customer = account.customer

            bill_number = None

            if transaction.bill is not None:
                bill_number = transaction.bill.bill_number

            response.append(
                {
                    "transaction_id": transaction.id,
                    "account_id": account.id,
                    "customer_id": customer.id,
                    "customer_name": customer.name,
                    "customer_phone": customer.phone,
                    "transaction_type": transaction.transaction_type,
                    "amount": transaction.amount,
                    "balance_after": transaction.balance_after,
                    "bill_id": transaction.bill_id,
                    "bill_number": bill_number,
                    "notes": transaction.notes,
                    "created_by": transaction.created_by,
                    "created_at": transaction.created_at,
                }
            )

        return response

    # ========================================================
    # SINGLE TRANSACTION
    # ========================================================

    async def get_transaction(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        transaction_id: UUID,
    ):

        transaction = (
            await kadan_repository.get_transaction_by_id(
                db=db,
                tenant_id=tenant_id,
                transaction_id=transaction_id,
            )
        )

        if transaction is None:

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Kadan transaction not found",
            )

        account = transaction.kadan_account
        customer = account.customer

        bill_number = None

        if transaction.bill is not None:
            bill_number = transaction.bill.bill_number

        return {
            "transaction_id": transaction.id,
            "account_id": account.id,
            "customer_id": customer.id,
            "customer_name": customer.name,
            "customer_phone": customer.phone,
            "transaction_type": transaction.transaction_type,
            "amount": transaction.amount,
            "balance_after": transaction.balance_after,
            "bill_id": transaction.bill_id,
            "bill_number": bill_number,
            "notes": transaction.notes,
            "created_by": transaction.created_by,
            "created_at": transaction.created_at,
        }

    # ========================================================
    # RECEIVE KADAN PAYMENT
    # ========================================================

    async def receive_payment(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        customer_id: UUID,
        user_id: UUID,
        data: KadanPaymentCreate,
    ):

        try:

            # ------------------------------------------------
            # Lock account
            # ------------------------------------------------

            account = (
                await kadan_repository.get_customer_account(
                    db=db,
                    tenant_id=tenant_id,
                    customer_id=customer_id,
                    for_update=True,
                )
            )

            if account is None:

                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Kadan account not found for this customer",
                )

            current_balance = self.money(
                account.outstanding_amount
                or Decimal("0.00")
            )

            payment_amount = self.money(
                data.amount
            )

            # ------------------------------------------------
            # Validate balance
            # ------------------------------------------------

            if current_balance <= Decimal("0.00"):

                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Customer has no outstanding Kadan",
                )

            if payment_amount > current_balance:

                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Payment amount cannot be greater "
                        f"than outstanding Kadan of "
                        f"{current_balance}"
                    ),
                )

            # ------------------------------------------------
            # Calculate new balance
            # ------------------------------------------------

            new_balance = self.money(
                current_balance - payment_amount
            )

            # ------------------------------------------------
            # Update account
            # ------------------------------------------------

            account.outstanding_amount = new_balance

            if new_balance == Decimal("0.00"):

                account.status = "SETTLED"

            else:

                account.status = "ACTIVE"

            # ------------------------------------------------
            # Create DEBIT transaction
            # ------------------------------------------------

            transaction = KadanTransaction(
                tenant_id=tenant_id,
                kadan_account_id=account.id,
                bill_id=None,
                transaction_type="DEBIT",
                amount=payment_amount,
                balance_after=new_balance,
                notes=(
                    data.notes
                    or "Kadan payment received"
                ),
                created_by=user_id,
            )

            await kadan_repository.create_transaction(
                db=db,
                transaction=transaction,
            )

            # ------------------------------------------------
            # Audit Log
            # ------------------------------------------------

            from app.services.audit_service import log as audit_log
            await audit_log(
                db=db,
                tenant_id=tenant_id,
                user_id=user_id,
                action="KADAN_PAYMENT",
                entity_type="kadan_transaction",
                entity_id=transaction.id,
                description=f"Received Kadan payment of {payment_amount}",
                new_values={"amount": str(payment_amount), "method": data.payment_method}
            )

            # ------------------------------------------------
            # Commit
            # ------------------------------------------------

            await db.commit()

            # ------------------------------------------------
            # Return
            # ------------------------------------------------

            return {
                "transaction_id": transaction.id,
                "customer_id": customer_id,
                "account_id": account.id,
                "previous_outstanding": current_balance,
                "paid_amount": payment_amount,
                "remaining_outstanding": new_balance,
                "payment_method": data.payment_method,
                "notes": (
                    data.notes
                    or "Kadan payment received"
                ),
                "created_at": transaction.created_at,
            }

        except HTTPException:

            await db.rollback()

            raise

        except Exception:

            await db.rollback()

            raise


# ============================================================
# SERVICE INSTANCE
# ============================================================

kadan_service = KadanService()