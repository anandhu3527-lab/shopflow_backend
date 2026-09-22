from decimal import Decimal

from fastapi import HTTPException, status

from app.repositories.customer_repository import customer_repository


class CustomerService:

    async def get_customers(
        self,
        db,
        tenant_id,
        limit,
        offset,
    ):
        return await customer_repository.get_customers(
            db=db,
            tenant_id=tenant_id,
            limit=limit,
            offset=offset,
        )

    async def get_customer_detail(
        self,
        db,
        tenant_id,
        customer_id,
    ):
        customer = await customer_repository.get_customer_by_id(
            db=db,
            tenant_id=tenant_id,
            customer_id=customer_id,
        )

        if customer is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found",
            )

        total_bills = (
            await customer_repository.get_customer_bill_count(
                db=db,
                tenant_id=tenant_id,
                customer_id=customer_id,
            )
        )

        total_purchase_amount = (
            await customer_repository.get_customer_total_purchase(
                db=db,
                tenant_id=tenant_id,
                customer_id=customer_id,
            )
        )

        kadan_account = (
            await customer_repository.get_customer_kadan_account(
                db=db,
                tenant_id=tenant_id,
                customer_id=customer_id,
            )
        )

        total_kadan_amount = Decimal("0.00")

        if kadan_account:
            total_kadan_amount = (
                kadan_account.outstanding_amount
                or Decimal("0.00")
            )

        return {
            "id": customer.id,
            "name": customer.name,
            "phone": customer.phone,
            "status": customer.status,
            "created_at": customer.created_at,
            "summary": {
                "total_bills": total_bills,
                "total_purchase_amount": total_purchase_amount,
                "total_kadan_amount": total_kadan_amount,
                "has_kadan": total_kadan_amount > Decimal("0.00"),
            },
        }

    async def get_customer_bills(
        self,
        db,
        tenant_id,
        customer_id,
        limit,
        offset,
    ):
        customer = await customer_repository.get_customer_by_id(
            db=db,
            tenant_id=tenant_id,
            customer_id=customer_id,
        )

        if customer is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found",
            )

        bills = await customer_repository.get_customer_bills(
            db=db,
            tenant_id=tenant_id,
            customer_id=customer_id,
            limit=limit,
            offset=offset,
        )

        response = []

        for bill in bills:

            paid_amount = (
                await customer_repository.get_bill_paid_amount(
                    db=db,
                    bill_id=bill.id,
                )
            )

            kadan_amount = (
                bill.total_amount - paid_amount
            )

            if kadan_amount < Decimal("0.00"):
                kadan_amount = Decimal("0.00")

            response.append(
                {
                    "bill_id": bill.id,
                    "bill_number": bill.bill_number,
                    "subtotal": bill.subtotal,
                    "discount_amount": bill.discount_amount,
                    "tax_amount": bill.tax_amount,
                    "total_amount": bill.total_amount,
                    "paid_amount": paid_amount,
                    "kadan_amount": kadan_amount,
                    "status": bill.status,
                    "created_at": bill.created_at,
                }
            )

        return response

    async def get_customer_credit_bills(
        self,
        db,
        tenant_id,
        customer_id,
        limit,
        offset,
    ):
        customer = await customer_repository.get_customer_by_id(
            db=db,
            tenant_id=tenant_id,
            customer_id=customer_id,
        )

        if customer is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found",
            )

        credit_bills = (
            await customer_repository.get_customer_credit_bills(
                db=db,
                tenant_id=tenant_id,
                customer_id=customer_id,
                limit=limit,
                offset=offset,
            )
        )

        response = []

        for item in credit_bills:

            bill = item["bill"]

            response.append(
                {
                    "bill_id": bill.id,
                    "bill_number": bill.bill_number,
                    "total_amount": bill.total_amount,
                    "paid_amount": item["paid_amount"],
                    "credit_amount": item["credit_amount"],
                    "status": bill.status,
                    "created_at": bill.created_at,
                }
            )

        return response


customer_service = CustomerService()