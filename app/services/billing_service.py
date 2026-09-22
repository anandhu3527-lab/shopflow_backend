from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta, timezone
import calendar
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bill import Bill
from app.models.bill_item import BillItem
from app.models.payment import Payment
from app.models.kadan_account import KadanAccount
from app.models.kadan_transaction import KadanTransaction

from app.repositories.bill_repository import bill_repository
from app.schemas.bill import BillCreate


MONEY_ZERO = Decimal("0.00")
MONEY_QUANT = Decimal("0.01")


class BillingService:

    async def create_bill(
        self,
        db: AsyncSession,
        tenant_id,
        user_id,
        data: BillCreate,
    ):
        try:
            # ============================================================
            # 1. NORMALIZE PAYMENT DATA
            # ============================================================

            payment_method = data.payment_method.strip().upper()

            paid_amount = Decimal(
                str(data.paid_amount)
            ).quantize(
                MONEY_QUANT,
                rounding=ROUND_HALF_UP,
            )

            # ============================================================
            # 2. VALIDATE PAYMENT METHOD
            # ============================================================

            allowed_methods = {
                "CASH",
                "UPI",
                "KADAN",
            }

            if payment_method not in allowed_methods:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Invalid payment method. "
                        "Use CASH, UPI, or KADAN."
                    ),
                )

            if paid_amount < MONEY_ZERO:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Paid amount cannot be negative.",
                )

            # ============================================================
            # 3. CHECK DUPLICATE VARIANTS
            # ============================================================

            variant_ids = [
                item.variant_id
                for item in data.items
            ]

            if len(variant_ids) != len(set(variant_ids)):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Duplicate product variants are not allowed. "
                        "Increase the quantity instead."
                    ),
                )

            # ============================================================
            # 4. LOAD PRODUCT VARIANTS
            #
            # IMPORTANT:
            # tenant_id comes from authenticated user.
            # Frontend cannot choose another tenant.
            # ============================================================

            variants = await bill_repository.get_variants_for_billing(
                db=db,
                tenant_id=tenant_id,
                variant_ids=variant_ids,
            )

            if len(variants) != len(variant_ids):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "One or more products were not found, "
                        "inactive, or do not belong to this shop."
                    ),
                )

            variant_map = {
                variant.id: variant
                for variant in variants
            }

            # ============================================================
            # 5. CUSTOMER VALIDATION
            # ============================================================

            customer_name = data.customer_name
            customer_phone = data.customer_phone

            if customer_name:
                customer_name = customer_name.strip()

            if customer_phone:
                customer_phone = customer_phone.strip()

            # Name and phone must be provided together
            if (
                customer_name and not customer_phone
            ) or (
                customer_phone and not customer_name
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Customer name and phone number "
                        "must be provided together."
                    ),
                )

            customer = None

            # ============================================================
            # 6. FIND EXISTING CUSTOMER
            # ============================================================

            if customer_name and customer_phone:

                customer = await bill_repository.get_customer_by_phone(
                    db=db,
                    tenant_id=tenant_id,
                    phone=customer_phone,
                )

            # ============================================================
            # 7. CALCULATE BILL
            # ============================================================

            subtotal = MONEY_ZERO
            total_tax = MONEY_ZERO
            total_discount = MONEY_ZERO

            bill_items = []

            for item in data.items:

                # ========================================================
                # GET VARIANT
                # ========================================================

                variant = variant_map.get(
                    item.variant_id
                )

                if variant is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Product variant "
                            f"{item.variant_id} was not found."
                        ),
                    )

                # ========================================================
                # QUANTITY
                # ========================================================

                quantity = Decimal(
                    str(item.quantity)
                )

                if quantity <= MONEY_ZERO:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            "Product quantity must be "
                            "greater than zero."
                        ),
                    )

                # ========================================================
                # STOCK VALIDATION
                # ========================================================

                stock_quantity = Decimal(
                    str(
                        variant.stock_quantity
                        if variant.stock_quantity is not None
                        else MONEY_ZERO
                    )
                )

                if stock_quantity < quantity:
                    product_name = (
                        variant.product.name
                        if variant.product
                        else "Unknown product"
                    )

                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Insufficient stock for "
                            f"'{product_name}'. "
                            f"Available: {stock_quantity}, "
                            f"Requested: {quantity}."
                        ),
                    )

                # ========================================================
                # PRICE SELECTION
                #
                # offer_price = NULL -> selling_price
                # offer_price = 0    -> selling_price
                # offer_price > 0    -> offer_price
                # ========================================================

                selling_price = Decimal(
                    str(
                        variant.selling_price
                        if variant.selling_price is not None
                        else MONEY_ZERO
                    )
                )

                offer_price = (
                    Decimal(str(variant.offer_price))
                    if variant.offer_price is not None
                    else None
                )

                if (
                    offer_price is not None
                    and offer_price > MONEY_ZERO
                ):
                    unit_price = offer_price
                else:
                    unit_price = selling_price

                unit_price = unit_price.quantize(
                    MONEY_QUANT,
                    rounding=ROUND_HALF_UP,
                )

                # ========================================================
                # TAX RATE
                # ========================================================

                tax_rate = Decimal(
                    str(
                        variant.tax_rate
                        if variant.tax_rate is not None
                        else MONEY_ZERO
                    )
                )

                # ========================================================
                # GROSS AMOUNT
                # ========================================================

                gross_amount = (
                    unit_price * quantity
                ).quantize(
                    MONEY_QUANT,
                    rounding=ROUND_HALF_UP,
                )

                # ========================================================
                # TAX AMOUNT
                # ========================================================

                tax_amount = (
                    gross_amount
                    * tax_rate
                    / Decimal("100")
                ).quantize(
                    MONEY_QUANT,
                    rounding=ROUND_HALF_UP,
                )

                # ========================================================
                # LINE TOTAL
                # ========================================================

                line_total = (
                    gross_amount + tax_amount
                ).quantize(
                    MONEY_QUANT,
                    rounding=ROUND_HALF_UP,
                )

                # ========================================================
                # UPDATE BILL TOTALS
                # ========================================================

                subtotal += gross_amount
                total_tax += tax_amount

                # ========================================================
                # CREATE BILL ITEM OBJECT
                # ========================================================

                bill_item = BillItem(
                    product_id=variant.product_id,
                    product_variant_id=variant.id,
                    item_name=(
                        variant.product.name
                        if variant.product
                        else "Unknown product"
                    ),
                    quantity=quantity,
                    unit_price=unit_price,
                    discount_amount=MONEY_ZERO,
                    tax_rate=tax_rate,
                    tax_amount=tax_amount,
                    line_total=line_total,
                )

                bill_items.append(
                    {
                        "model": bill_item,
                        "variant": variant,
                        "quantity": quantity,
                    }
                )

            # ============================================================
            # 8. FINAL BILL TOTAL
            # ============================================================

            total_amount = (
                subtotal
                + total_tax
                - total_discount
            ).quantize(
                MONEY_QUANT,
                rounding=ROUND_HALF_UP,
            )

            # ============================================================
            # 9. PAYMENT VALIDATION
            #
            # IMPORTANT:
            # Validation happens AFTER calculating the real bill total.
            # ============================================================

            # ------------------------------------------------------------
            # RULE 1:
            # Paid amount cannot exceed bill total.
            # ------------------------------------------------------------

            if paid_amount > total_amount:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Paid amount ₹{paid_amount:.2f} "
                        f"cannot be greater than bill total "
                        f"₹{total_amount:.2f}."
                    ),
                )

            # ------------------------------------------------------------
            # RULE 2:
            # KADAN means no payment now.
            # ------------------------------------------------------------

            if payment_method == "KADAN":

                if paid_amount != MONEY_ZERO:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            "Payment method KADAN requires "
                            "paid amount to be ₹0.00."
                        ),
                    )

            # ------------------------------------------------------------
            # RULE 3:
            # CASH / UPI requires payment greater than zero.
            # ------------------------------------------------------------

            if payment_method in {
                "CASH",
                "UPI",
            }:

                if paid_amount <= MONEY_ZERO:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"{payment_method} payment requires "
                            "paid amount greater than ₹0.00."
                        ),
                    )

            # ============================================================
            # 10. CALCULATE KADAN
            # ============================================================

            kadan_amount = (
                total_amount - paid_amount
            ).quantize(
                MONEY_QUANT,
                rounding=ROUND_HALF_UP,
            )

            # ============================================================
            # 11. CUSTOMER REQUIRED FOR KADAN
            # ============================================================

            if kadan_amount > MONEY_ZERO:

                if (
                    not customer_name
                    or not customer_phone
                ):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Customer name and phone number are required for Kadan bills."
                    )

                import re
                if not re.match(r"^[6-9][0-9]{9}$", customer_phone):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="A valid customer phone number is required for Kadan bills."
                    )
            elif customer_phone:
                import re
                if not re.match(r"^[6-9][0-9]{9}$", customer_phone):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="A valid customer phone number is required."
                    )

            # ============================================================
            # 12. FULL PAYMENT CANNOT USE KADAN
            # ============================================================

            if (
                paid_amount == total_amount
                and payment_method == "KADAN"
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "A fully paid bill cannot use "
                        "KADAN payment method."
                    ),
                )

            # ============================================================
            # 13. ZERO PAYMENT ONLY ALLOWED WITH KADAN
            # ============================================================

            if (
                paid_amount == MONEY_ZERO
                and payment_method != "KADAN"
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Paid amount is ₹0.00. "
                        "Use KADAN as the payment method."
                    ),
                )

            # ============================================================
            # 14. CREATE CUSTOMER IF NEW
            # ============================================================

            if (
                customer is None
                and customer_name
                and customer_phone
            ):

                customer = await bill_repository.create_customer(
                    db=db,
                    tenant_id=tenant_id,
                    name=customer_name,
                    phone=customer_phone,
                )

            # ============================================================
            # 15. GENERATE BILL NUMBER
            #
            # Repository returns INTEGER.
            #
            # Example:
            #
            # Database:
            # BILL-000001
            # BILL-000002
            # BILL-000005
            #
            # Repository returns:
            # 5
            #
            # Next:
            # BILL-000006
            # ============================================================

            latest_number = (
                await bill_repository.get_latest_bill_number(
                    db=db,
                    tenant_id=tenant_id,
                )
            )

            if latest_number is None:
                next_number = 1
            else:
                next_number = latest_number + 1

            bill_number = (
                f"BILL-{next_number:06d}"
            )

            # ============================================================
            # 16. CREATE BILL
            # ============================================================

            bill = Bill(
                tenant_id=tenant_id,
                customer_id=(
                    customer.id
                    if customer
                    else None
                ),
                bill_number=bill_number,
                subtotal=subtotal,
                discount_amount=total_discount,
                tax_amount=total_tax,
                total_amount=total_amount,
                status="COMPLETED",
                created_by=user_id,
            )

            await bill_repository.create_bill(
                db=db,
                bill=bill,
            )

            # ============================================================
            # 17. CREATE BILL ITEMS + REDUCE STOCK
            # ============================================================

            for item_data in bill_items:

                bill_item = item_data["model"]
                variant = item_data["variant"]
                quantity = item_data["quantity"]

                bill_item.bill_id = bill.id

                await bill_repository.create_bill_item(
                    db=db,
                    bill_item=bill_item,
                )

                await bill_repository.update_stock(
                    variant=variant,
                    quantity=quantity,
                )

            # ============================================================
            # 18. CREATE PAYMENT
            #
            # Only actual amount paid now goes into payments.
            #
            # Example:
            #
            # Bill       = ₹1000
            # Paid now   = ₹500
            # Kadan      = ₹500
            #
            # payments:
            # ₹500 CASH
            #
            # Kadan:
            # ₹500
            # ============================================================

            if paid_amount > MONEY_ZERO:

                payment = Payment(
                    tenant_id=tenant_id,
                    bill_id=bill.id,
                    amount=paid_amount,
                    payment_method=payment_method,
                    status="COMPLETED",
                    created_by=user_id,
                )

                await bill_repository.create_payment(
                    db=db,
                    payment=payment,
                )

            # ============================================================
            # 19. CREATE / UPDATE KADAN
            # ============================================================

            kadan_summary = None

            if kadan_amount > MONEY_ZERO:

                if customer is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            "Customer is required "
                            "for Kadan."
                        ),
                    )

                # --------------------------------------------------------
                # GET KADAN ACCOUNT WITH ROW LOCK
                # --------------------------------------------------------

                kadan_account = (
                    await bill_repository.get_kadan_account(
                        db=db,
                        tenant_id=tenant_id,
                        customer_id=customer.id,
                        for_update=True,
                    )
                )

                # --------------------------------------------------------
                # CREATE ACCOUNT IF IT DOES NOT EXIST
                # --------------------------------------------------------

                if kadan_account is None:

                    kadan_account = KadanAccount(
                        tenant_id=tenant_id,
                        customer_id=customer.id,
                        outstanding_amount=MONEY_ZERO,
                        status="ACTIVE",
                    )

                    await (
                        bill_repository.create_kadan_account(
                            db=db,
                            kadan_account=kadan_account,
                        )
                    )

                # --------------------------------------------------------
                # CURRENT OUTSTANDING
                # --------------------------------------------------------

                current_outstanding = Decimal(
                    str(
                        kadan_account.outstanding_amount
                        if kadan_account.outstanding_amount
                        is not None
                        else MONEY_ZERO
                    )
                )

                # --------------------------------------------------------
                # NEW OUTSTANDING
                # --------------------------------------------------------

                new_outstanding = (
                    current_outstanding
                    + kadan_amount
                ).quantize(
                    MONEY_QUANT,
                    rounding=ROUND_HALF_UP,
                )

                kadan_account.outstanding_amount = (
                    new_outstanding
                )

                # --------------------------------------------------------
                # CREATE KADAN TRANSACTION
                # --------------------------------------------------------

                transaction = KadanTransaction(
                    tenant_id=tenant_id,
                    kadan_account_id=kadan_account.id,
                    bill_id=bill.id,
                    transaction_type="CREDIT",
                    amount=kadan_amount,
                    balance_after=new_outstanding,
                    created_by=user_id,
                )

                await (
                    bill_repository.create_kadan_transaction(
                        db=db,
                        transaction=transaction,
                    )
                )

                kadan_summary = {
                    "paid_amount": paid_amount,
                    "kadan_amount": kadan_amount,
                    "outstanding_amount": new_outstanding,
                }

            else:

                kadan_summary = {
                    "paid_amount": paid_amount,
                    "kadan_amount": MONEY_ZERO,
                    "outstanding_amount": MONEY_ZERO,
                }

            # ============================================================
            # 20. AUDIT LOGS
            # ============================================================

            from app.services.audit_service import log as audit_log

            if customer is not None and not hasattr(customer, '_sa_instance_state') or getattr(customer, 'id', None) and customer_name and customer_phone: # checking if new customer roughly
                pass # Wait, we can explicitly track if customer was created:

            # Since customer is just the object, we check if we created it. We created it at step 14.
            # We can just check if we called create_customer. Let's just log BILL_CREATED and others which are definitely created here.

            # Bill
            await audit_log(
                db=db,
                tenant_id=tenant_id,
                user_id=user_id,
                action="BILL_CREATED",
                entity_type="bill",
                entity_id=bill.id,
                description=f"Bill {bill.bill_number} created for {total_amount}",
                new_values={"bill_number": bill.bill_number, "total_amount": str(total_amount), "kadan_amount": str(kadan_amount), "paid_amount": str(paid_amount)},
            )

            # Stock Decreased
            for item_data in bill_items:
                variant = item_data["variant"]
                await audit_log(
                    db=db,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    action="STOCK_DECREASED_BY_BILL",
                    entity_type="product_variant",
                    entity_id=variant.id,
                    description=f"Stock decreased by {item_data['quantity']} for bill {bill.bill_number}",
                    new_values={"quantity_decreased": str(item_data["quantity"])}
                )

            # Payment
            if paid_amount > MONEY_ZERO:
                await audit_log(
                    db=db,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    action="PAYMENT_CREATED",
                    entity_type="bill",
                    entity_id=bill.id,
                    description=f"Payment of {paid_amount} via {payment_method} received",
                    new_values={"amount": str(paid_amount), "method": payment_method}
                )
            
            # Kadan
            if kadan_amount > MONEY_ZERO:
                await audit_log(
                    db=db,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    action="KADAN_TRANSACTION_CREATED",
                    entity_type="kadan_account",
                    entity_id=kadan_account.id,
                    description=f"Kadan of {kadan_amount} added from bill {bill.bill_number}",
                    new_values={"kadan_amount": str(kadan_amount)}
                )

            # ============================================================
            # 21. COMMIT
            #
            # Nothing is permanently saved until this point.
            # ============================================================

            await db.commit()

            # ============================================================
            # 21. RELOAD CREATED BILL
            # ============================================================

            created_bill = (
                await bill_repository.get_bill_by_id(
                    db=db,
                    tenant_id=tenant_id,
                    bill_id=bill.id,
                )
            )

            if created_bill is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "Bill was created but "
                        "could not be retrieved."
                    ),
                )

            # ============================================================
            # 22. RETURN
            # ============================================================

            return {
                "bill": created_bill,
                "kadan": kadan_summary,
            }

        # ================================================================
        # EXPECTED VALIDATION / BUSINESS ERROR
        # ================================================================

        except HTTPException:

            await db.rollback()

            raise

        # ================================================================
        # UNEXPECTED ERROR
        # ================================================================

        except Exception as exc:

            await db.rollback()

            # Print complete traceback in development
            import traceback

            print("\n" + "=" * 80)
            print("BILLING SERVICE ERROR")
            print("=" * 80)
            print(f"ERROR TYPE: {type(exc).__name__}")
            print(f"ERROR: {exc}")
            print("=" * 80)

            traceback.print_exc()

            print("=" * 80 + "\n")

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    f"Failed to create bill: {str(exc)}"
                ),
            )

    # ============================================================
    # DATE SUMMARY
    # ============================================================

    async def get_date_summary(
        self,
        db: AsyncSession,
        tenant_id,
        target_date_str: str,
    ):
        try:
            dt = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid date format. Use YYYY-MM-DD",
            )

        ist = timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")
        date_start = datetime(dt.year, dt.month, dt.day, tzinfo=ist)
        date_end = date_start + timedelta(days=1)

        _, last_day = calendar.monthrange(dt.year, dt.month)
        month_start = datetime(dt.year, dt.month, 1, tzinfo=ist)
        month_end = month_start + timedelta(days=last_day)

        month_stats = await bill_repository.get_date_summary_stats(
            db=db,
            tenant_id=tenant_id,
            start_date=month_start,
            end_date=month_end,
        )

        date_stats = await bill_repository.get_date_summary_stats(
            db=db,
            tenant_id=tenant_id,
            start_date=date_start,
            end_date=date_end,
        )

        bills = await bill_repository.get_bills_by_date_range(
            db=db,
            tenant_id=tenant_id,
            start_date=date_start,
            end_date=date_end,
        )

        return {
            "date": target_date_str,
            "month": f"{dt.year}-{dt.month:02d}",
            "month_summary": month_stats,
            "date_summary": date_stats,
            "bills": [
                {
                    "id": b.id,
                    "bill_number": b.bill_number,
                    "total_amount": b.total_amount,
                    "status": b.status,
                    "created_at": b.created_at,
                }
                for b in bills
            ],
        }


billing_service = BillingService()