from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta, timezone
import calendar
import re
import logging

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bill import Bill
from app.models.bill_item import BillItem
from app.models.payment import Payment
from app.models.kadan_account import KadanAccount
from app.models.kadan_transaction import KadanTransaction

from app.repositories.bill_repository import bill_repository
from app.schemas.bill import BillCreate


# ============================================================
# CONSTANTS
# ============================================================

MONEY_ZERO = Decimal("0.00")
MONEY_QUANT = Decimal("0.01")

logger = logging.getLogger(__name__)


# ============================================================
# BILLING SERVICE
# ============================================================

class BillingService:

    # ========================================================
    # CREATE BILL
    # ========================================================

    async def create_bill(
        self,
        db: AsyncSession,
        tenant_id,
        user_id,
        data: BillCreate,
    ):
        try:

            # ====================================================
            # 1. NORMALIZE PAYMENT DATA
            # ====================================================

            payment_method = (
                data.payment_method
                .strip()
                .upper()
            )

            paid_amount = Decimal(
                str(data.paid_amount)
            ).quantize(
                MONEY_QUANT,
                rounding=ROUND_HALF_UP,
            )

            discount_amount = Decimal(
                str(data.discount_amount)
            ).quantize(
                MONEY_QUANT,
                rounding=ROUND_HALF_UP,
            )

            # ====================================================
            # 2. VALIDATE PAYMENT METHOD
            # ====================================================

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

            if discount_amount < MONEY_ZERO:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Discount amount cannot be negative.",
                )

            # ====================================================
            # 3. CHECK DUPLICATE VARIANTS
            # ====================================================

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

            # ====================================================
            # 4. LOAD PRODUCT VARIANTS
            # ====================================================

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

            # ====================================================
            # 5. CUSTOMER VALIDATION
            # ====================================================

            customer_name = data.customer_name
            customer_phone = data.customer_phone

            if customer_name:
                customer_name = customer_name.strip()

            if customer_phone:
                customer_phone = (
                    customer_phone
                    .strip()
                    .replace(" ", "")
                    .replace("-", "")
                )

                if customer_phone.startswith("+91"):
                    customer_phone = customer_phone[3:]

            # Name and phone must be provided together.
            if (
                customer_name
                and not customer_phone
            ) or (
                customer_phone
                and not customer_name
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Customer name and phone number "
                        "must be provided together."
                    ),
                )

            customer = None

            # ====================================================
            # 6. FIND EXISTING CUSTOMER
            # ====================================================

            if customer_name and customer_phone:

                customer = (
                    await bill_repository.get_customer_by_phone(
                        db=db,
                        tenant_id=tenant_id,
                        phone=customer_phone,
                    )
                )

            # ====================================================
            # 7. CALCULATE BILL
            # ====================================================

            subtotal = MONEY_ZERO
            total_tax = MONEY_ZERO

            bill_items = []

            for item in data.items:

                # =================================================
                # GET VARIANT
                # =================================================

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

                # =================================================
                # QUANTITY
                # =================================================

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

                # =================================================
                # STOCK VALIDATION
                # =================================================

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

                # =================================================
                # PRICE SELECTION
                # =================================================
                #
                # offer_price > 0 -> use offer price
                # otherwise -> selling price
                #
                # =================================================

                selling_price = Decimal(
                    str(
                        variant.selling_price
                        if variant.selling_price is not None
                        else MONEY_ZERO
                    )
                )

                offer_price = (
                    Decimal(
                        str(variant.offer_price)
                    )
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

                # =================================================
                # TAX RATE
                # =================================================

                tax_rate = Decimal(
                    str(
                        variant.tax_rate
                        if variant.tax_rate is not None
                        else MONEY_ZERO
                    )
                )

                if tax_rate < MONEY_ZERO:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Tax rate cannot be negative.",
                    )

                # =================================================
                # GROSS AMOUNT
                # =================================================

                gross_amount = (
                    unit_price * quantity
                ).quantize(
                    MONEY_QUANT,
                    rounding=ROUND_HALF_UP,
                )

                # =================================================
                # TAX AMOUNT
                # =================================================
                #
                # Preserve the existing ShopFlow tax behavior:
                # tax is calculated on the item gross amount.
                #
                # Bill-level discount is applied after tax.
                #
                # =================================================

                tax_amount = (
                    gross_amount
                    * tax_rate
                    / Decimal("100")
                ).quantize(
                    MONEY_QUANT,
                    rounding=ROUND_HALF_UP,
                )

                # =================================================
                # LINE TOTAL
                # =================================================

                line_total = (
                    gross_amount + tax_amount
                ).quantize(
                    MONEY_QUANT,
                    rounding=ROUND_HALF_UP,
                )

                # =================================================
                # UPDATE BILL TOTALS
                # =================================================

                subtotal += gross_amount
                total_tax += tax_amount

                # =================================================
                # CREATE BILL ITEM
                # =================================================

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

                    # The discount is a BILL-LEVEL discount.
                    # Therefore bill item discount remains zero.
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

            # ====================================================
            # 8. VALIDATE DISCOUNT
            # ====================================================
            #
            # Discount cannot exceed subtotal.
            #
            # Example:
            # subtotal = 300
            # discount = 30 -> valid
            #
            # subtotal = 300
            # discount = 350 -> invalid
            #
            # ====================================================

            if discount_amount > subtotal:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Discount amount ₹{discount_amount:.2f} "
                        f"cannot be greater than subtotal "
                        f"₹{subtotal:.2f}."
                    ),
                )

            # ====================================================
            # 9. FINAL BILL TOTAL
            # ====================================================
            #
            # IMPORTANT:
            #
            # final total =
            # subtotal
            # + tax
            # - discount
            #
            # Discount is NOT a payment.
            # Discount is NOT Kadan.
            #
            # ====================================================

            total_amount = (
                subtotal
                + total_tax
                - discount_amount
            ).quantize(
                MONEY_QUANT,
                rounding=ROUND_HALF_UP,
            )

            if total_amount < MONEY_ZERO:
                total_amount = MONEY_ZERO

            # ====================================================
            # 10. PAYMENT VALIDATION
            # ====================================================

            if paid_amount > total_amount:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Paid amount ₹{paid_amount:.2f} "
                        f"cannot be greater than bill total "
                        f"₹{total_amount:.2f}."
                    ),
                )

            # ====================================================
            # 11. KADAN PAYMENT METHOD
            # ====================================================

            if payment_method == "KADAN":

                if paid_amount != MONEY_ZERO:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            "Payment method KADAN requires "
                            "paid amount to be ₹0.00."
                        ),
                    )

            # ====================================================
            # 12. CASH / UPI VALIDATION
            # ====================================================
            #
            # If the final bill is greater than zero,
            # CASH / UPI must have a positive payment.
            #
            # Zero-value bills created by a 100% discount
            # are allowed.
            #
            # ====================================================

            if (
                payment_method in {"CASH", "UPI"}
                and total_amount > MONEY_ZERO
                and paid_amount <= MONEY_ZERO
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"{payment_method} payment requires "
                        "paid amount greater than ₹0.00."
                    ),
                )

            # ====================================================
            # 13. CALCULATE KADAN
            # ====================================================
            #
            # THIS IS THE MOST IMPORTANT RULE:
            #
            # Kadan =
            #
            # FINAL DISCOUNTED TOTAL - ACTUAL PAYMENT
            #
            # NOT:
            #
            # subtotal - payment
            #
            # NOT:
            #
            # discount amount
            #
            # ====================================================

            kadan_amount = (
                total_amount - paid_amount
            ).quantize(
                MONEY_QUANT,
                rounding=ROUND_HALF_UP,
            )

            if kadan_amount < MONEY_ZERO:
                kadan_amount = MONEY_ZERO

            # ====================================================
            # 14. CUSTOMER REQUIRED FOR KADAN
            # ====================================================

            if kadan_amount > MONEY_ZERO:

                if (
                    not customer_name
                    or not customer_phone
                ):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            "Customer name and phone number "
                            "are required for Kadan bills."
                        ),
                    )

                if not re.match(
                    r"^[6-9][0-9]{9}$",
                    customer_phone,
                ):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            "A valid customer phone number "
                            "is required for Kadan bills."
                        ),
                    )

            elif customer_phone:

                if not re.match(
                    r"^[6-9][0-9]{9}$",
                    customer_phone,
                ):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            "A valid customer phone number "
                            "is required."
                        ),
                    )

            # ====================================================
            # 15. FULL PAYMENT CANNOT USE KADAN
            # ====================================================

            if (
                paid_amount == total_amount
                and payment_method == "KADAN"
                and total_amount > MONEY_ZERO
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "A fully paid bill cannot use "
                        "KADAN payment method."
                    ),
                )

            # ====================================================
            # 16. CREATE CUSTOMER IF NEW
            # ====================================================

            if (
                customer is None
                and customer_name
                and customer_phone
            ):
                customer = (
                    await bill_repository.create_customer(
                        db=db,
                        tenant_id=tenant_id,
                        name=customer_name,
                        phone=customer_phone,
                    )
                )

            # ====================================================
            # 17. GENERATE BILL NUMBER
            # ====================================================

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

            # ====================================================
            # 18. CREATE BILL
            # ====================================================

            bill = Bill(
                tenant_id=tenant_id,

                customer_id=(
                    customer.id
                    if customer
                    else None
                ),

                bill_number=bill_number,

                subtotal=subtotal,

                # IMPORTANT:
                # Store the actual bill-level discount.
                discount_amount=discount_amount,

                tax_amount=total_tax,

                # This is the final discounted total.
                total_amount=total_amount,

                status="COMPLETED",

                created_by=user_id,
            )

            await bill_repository.create_bill(
                db=db,
                bill=bill,
            )

            # ====================================================
            # 19. CREATE BILL ITEMS + REDUCE STOCK
            # ====================================================

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

            # ====================================================
            # 20. CREATE PAYMENT
            # ====================================================
            #
            # Only money actually received is stored
            # in the payments table.
            #
            # Discount is NEVER stored as a payment.
            #
            # ====================================================

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

            # ====================================================
            # 21. CREATE / UPDATE KADAN
            # ====================================================

            kadan_summary = None
            kadan_account = None

            if kadan_amount > MONEY_ZERO:

                if customer is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            "Customer is required "
                            "for Kadan."
                        ),
                    )

                # ------------------------------------------------
                # GET ACCOUNT WITH ROW LOCK
                # ------------------------------------------------

                kadan_account = (
                    await bill_repository.get_kadan_account(
                        db=db,
                        tenant_id=tenant_id,
                        customer_id=customer.id,
                        for_update=True,
                    )
                )

                # ------------------------------------------------
                # CREATE ACCOUNT
                # ------------------------------------------------

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

                # ------------------------------------------------
                # CURRENT OUTSTANDING
                # ------------------------------------------------

                current_outstanding = Decimal(
                    str(
                        kadan_account.outstanding_amount
                        if kadan_account.outstanding_amount
                        is not None
                        else MONEY_ZERO
                    )
                )

                # ------------------------------------------------
                # NEW OUTSTANDING
                # ------------------------------------------------

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

                # ------------------------------------------------
                # CREATE KADAN TRANSACTION
                # ------------------------------------------------

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

            # ====================================================
            # 22. AUDIT LOGS
            # ====================================================

            from app.services.audit_service import log as audit_log

            await audit_log(
                db=db,
                tenant_id=tenant_id,
                user_id=user_id,
                action="BILL_CREATED",
                entity_type="bill",
                entity_id=bill.id,
                description=(
                    f"Bill {bill.bill_number} created"
                ),
                new_values={
                    "bill_number": bill.bill_number,
                    "subtotal": str(subtotal),
                    "discount_amount": str(
                        discount_amount
                    ),
                    "tax_amount": str(total_tax),
                    "total_amount": str(
                        total_amount
                    ),
                    "paid_amount": str(
                        paid_amount
                    ),
                    "kadan_amount": str(
                        kadan_amount
                    ),
                },
            )

            # ----------------------------------------------------
            # STOCK AUDIT
            # ----------------------------------------------------

            for item_data in bill_items:

                variant = item_data["variant"]

                await audit_log(
                    db=db,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    action="STOCK_DECREASED_BY_BILL",
                    entity_type="product_variant",
                    entity_id=variant.id,
                    description=(
                        f"Stock decreased by "
                        f"{item_data['quantity']} "
                        f"for bill {bill.bill_number}"
                    ),
                    new_values={
                        "quantity_decreased": str(
                            item_data["quantity"]
                        ),
                    },
                )

            # ----------------------------------------------------
            # PAYMENT AUDIT
            # ----------------------------------------------------

            if paid_amount > MONEY_ZERO:

                await audit_log(
                    db=db,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    action="PAYMENT_CREATED",
                    entity_type="bill",
                    entity_id=bill.id,
                    description=(
                        f"Payment of ₹{paid_amount:.2f} "
                        f"via {payment_method} received"
                    ),
                    new_values={
                        "amount": str(paid_amount),
                        "method": payment_method,
                    },
                )

            # ----------------------------------------------------
            # KADAN AUDIT
            # ----------------------------------------------------

            if kadan_amount > MONEY_ZERO:

                await audit_log(
                    db=db,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    action="KADAN_TRANSACTION_CREATED",
                    entity_type="kadan_account",
                    entity_id=kadan_account.id,
                    description=(
                        f"Kadan of ₹{kadan_amount:.2f} "
                        f"added from bill "
                        f"{bill.bill_number}"
                    ),
                    new_values={
                        "kadan_amount": str(
                            kadan_amount
                        ),
                    },
                )

            # ====================================================
            # 23. COMMIT
            # ====================================================

            await db.commit()

            # ====================================================
            # 24. RELOAD CREATED BILL
            # ====================================================

            created_bill = (
                await bill_repository.get_bill_by_id(
                    db=db,
                    tenant_id=tenant_id,
                    bill_id=bill.id,
                )
            )

            if created_bill is None:
                raise HTTPException(
                    status_code=(
                        status.HTTP_500_INTERNAL_SERVER_ERROR
                    ),
                    detail=(
                        "Bill was created but "
                        "could not be retrieved."
                    ),
                )

            # ====================================================
            # 25. RETURN
            # ====================================================

            return {
                "bill": created_bill,
                "kadan": kadan_summary,
            }

        # ========================================================
        # EXPECTED BUSINESS ERROR
        # ========================================================

        except HTTPException:
            await db.rollback()
            raise

        # ========================================================
        # UNEXPECTED ERROR
        # ========================================================

        except Exception as exc:

            await db.rollback()

            logger.exception(
                "Failed to create bill"
            )

            raise HTTPException(
                status_code=(
                    status.HTTP_500_INTERNAL_SERVER_ERROR
                ),
                detail=(
                    "Failed to create bill. "
                    "Please try again."
                ),
            ) from exc

    # ========================================================
    # DATE SUMMARY
    # ========================================================

    async def get_date_summary(
        self,
        db: AsyncSession,
        tenant_id,
        target_date_str: str,
    ):
        try:
            dt = datetime.strptime(
                target_date_str,
                "%Y-%m-%d",
            ).date()

        except ValueError:

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Invalid date format. "
                    "Use YYYY-MM-DD"
                ),
            )

        # ====================================================
        # ASIA / KOLKATA
        # ====================================================

        ist = timezone(
            timedelta(hours=5, minutes=30),
            name="Asia/Kolkata",
        )

        date_start = datetime(
            dt.year,
            dt.month,
            dt.day,
            tzinfo=ist,
        )

        date_end = (
            date_start
            + timedelta(days=1)
        )

        # ====================================================
        # MONTH RANGE
        # ====================================================

        _, last_day = calendar.monthrange(
            dt.year,
            dt.month,
        )

        month_start = datetime(
            dt.year,
            dt.month,
            1,
            tzinfo=ist,
        )

        month_end = month_start + timedelta(
            days=last_day
        )

        # ====================================================
        # MONTH STATS
        # ====================================================

        month_stats = (
            await bill_repository.get_date_summary_stats(
                db=db,
                tenant_id=tenant_id,
                start_date=month_start,
                end_date=month_end,
            )
        )

        # ====================================================
        # DATE STATS
        # ====================================================

        date_stats = (
            await bill_repository.get_date_summary_stats(
                db=db,
                tenant_id=tenant_id,
                start_date=date_start,
                end_date=date_end,
            )
        )

        # ====================================================
        # BILLS
        # ====================================================

        bills = (
            await bill_repository.get_bills_by_date_range(
                db=db,
                tenant_id=tenant_id,
                start_date=date_start,
                end_date=date_end,
            )
        )

        return {
            "date": target_date_str,

            "month": (
                f"{dt.year}-{dt.month:02d}"
            ),

            "month_summary": month_stats,

            "date_summary": date_stats,

            "bills": [
                {
                    "id": bill.id,
                    "bill_number": bill.bill_number,
                    "total_amount": bill.total_amount,
                    "status": bill.status,
                    "created_at": bill.created_at,
                }
                for bill in bills
            ],
        }


# ============================================================
# SERVICE INSTANCE
# ============================================================

billing_service = BillingService()
