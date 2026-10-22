import calendar
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.report_repository import report_repository
from app.schemas.reports import (
    BillDetailResponse,
    CustomerKadanSummaryResponse,
    DailyBreakdownResponse,
    KadanCurrentSummaryResponse,
    KadanPeriodSummaryResponse,
    KadanReportResponse,
    KadanTransactionDetailResponse,
    PaymentSummaryResponse,
    ReportPeriodResponse,
    ReportResponse,
    ReportSummaryResponse,
)


class ReportService:

    async def _generate_report(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        report_type: Literal["MONTHLY", "WEEKLY"],
        start_date: datetime,
        end_date: datetime,
    ) -> ReportResponse:

        bills = await report_repository.get_bills_for_period(
            db, tenant_id, start_date, end_date
        )

        kadan_txs = await report_repository.get_kadan_transactions_for_period(
            db, tenant_id, start_date, end_date
        )

        # ------------------------------------------------------------
        # INITIALIZE DAILY BREAKDOWN
        # ------------------------------------------------------------
        daily_map = {}
        curr = start_date
        while curr < end_date:
            daily_map[curr.date()] = {
                "total_bills": 0,
                "total_sales": Decimal("0.00"),
                "total_paid": Decimal("0.00"),
                "total_credit": Decimal("0.00"),
            }
            curr += timedelta(days=1)

        # ------------------------------------------------------------
        # PROCESS BILLS
        # ------------------------------------------------------------
        total_bills_count = len(bills)
        valid_bills_count = 0
        total_sales = Decimal("0.00")
        total_subtotal = Decimal("0.00")
        total_discount = Decimal("0.00")
        total_tax = Decimal("0.00")
        total_paid = Decimal("0.00")
        total_credit_generated = Decimal("0.00")

        payments_by_method = defaultdict(Decimal)
        total_payment_transactions = 0

        bill_details = []
        customer_ids = set()
        customers_who_purchased = set()

        for bill in bills:
            # Customer track
            if bill.customer_id:
                customer_ids.add(bill.customer_id)
                if bill.status != "CANCELLED":
                    customers_who_purchased.add(bill.customer_id)

            # Payment logic
            bill_paid_amount = sum(
                [p.amount for p in bill.payments if p.status == "COMPLETED"],
                Decimal("0.00")
            )
            bill_credit_amount = bill.total_amount - bill_paid_amount
            if bill_credit_amount < Decimal("0.00"):
                bill_credit_amount = Decimal("0.00")

            if bill.status != "CANCELLED":
                valid_bills_count += 1
                total_sales += bill.total_amount
                total_subtotal += bill.subtotal
                total_discount += bill.discount_amount
                total_tax += bill.tax_amount
                total_paid += bill_paid_amount
                total_credit_generated += bill_credit_amount

                for payment in bill.payments:
                    if payment.status == "COMPLETED":
                        payments_by_method[payment.payment_method] += payment.amount
                        total_payment_transactions += 1

                # Daily Breakdown Update
                b_date = bill.created_at.date()
                if b_date in daily_map:
                    daily_map[b_date]["total_bills"] += 1
                    daily_map[b_date]["total_sales"] += bill.total_amount
                    daily_map[b_date]["total_paid"] += bill_paid_amount
                    daily_map[b_date]["total_credit"] += bill_credit_amount

            # Append to Details regardless of CANCELLED, but mark it
            bill_details.append(
                BillDetailResponse(
                    bill_id=bill.id,
                    bill_number=bill.bill_number,
                    customer_id=bill.customer_id,
                    customer_name=bill.customer.name if bill.customer else None,
                    subtotal=bill.subtotal,
                    discount_amount=bill.discount_amount,
                    tax_amount=bill.tax_amount,
                    total_amount=bill.total_amount,
                    paid_amount=bill_paid_amount,
                    credit_amount=bill_credit_amount,
                    status=bill.status,
                    created_at=bill.created_at,
                )
            )

        avg_bill = (total_sales / valid_bills_count).quantize(Decimal("0.01")) if valid_bills_count > 0 else Decimal("0.00")

        # ------------------------------------------------------------
        # PROCESS KADAN TRANSACTIONS
        # ------------------------------------------------------------
        k_credit_gen = Decimal("0.00")
        k_credit_txs = 0
        k_collected = Decimal("0.00")
        k_repay_txs = 0

        customers_received_credit = set()
        kadan_tx_details = []

        customer_kadan_period_map = defaultdict(lambda: {"credit": Decimal("0.00"), "paid": Decimal("0.00")})

        for tx in kadan_txs:
            customer = tx.kadan_account.customer
            customer_ids.add(customer.id)

            if tx.transaction_type == "CREDIT":
                k_credit_gen += tx.amount
                k_credit_txs += 1
                customers_received_credit.add(customer.id)
                customer_kadan_period_map[customer.id]["credit"] += tx.amount
            elif tx.transaction_type == "DEBIT":
                k_collected += tx.amount
                k_repay_txs += 1
                customer_kadan_period_map[customer.id]["paid"] += tx.amount

            kadan_tx_details.append(
                KadanTransactionDetailResponse(
                    transaction_id=tx.id,
                    customer_id=customer.id,
                    customer_name=customer.name,
                    customer_phone=customer.phone,
                    account_id=tx.kadan_account_id,
                    transaction_type=tx.transaction_type,
                    amount=tx.amount,
                    balance_after=tx.balance_after,
                    bill_id=tx.bill_id,
                    bill_number=tx.bill.bill_number if tx.bill else None,
                    notes=tx.notes,
                    created_by=tx.created_by,
                    created_at=tx.created_at,
                )
            )

        # ------------------------------------------------------------
        # CURRENT KADAN OUTSTANDING
        # ------------------------------------------------------------
        kadan_accounts = await report_repository.get_current_kadan_accounts(
            db, tenant_id, list(customer_ids)
        )

        total_current_outstanding = Decimal("0.00")
        customers_with_outstanding = 0
        customer_details_map = {}

        for acc in kadan_accounts:
            total_current_outstanding += acc.outstanding_amount
            if acc.outstanding_amount > Decimal("0.00"):
                customers_with_outstanding += 1

            c = acc.customer
            customer_details_map[c.id] = {
                "name": c.name,
                "phone": c.phone,
                "current_outstanding": acc.outstanding_amount
            }

        # Build customer kadan summary
        customer_kadan_summaries = []
        for cid in customer_ids:
            if cid in customer_details_map or cid in customer_kadan_period_map:
                name = customer_details_map.get(cid, {}).get("name")
                phone = customer_details_map.get(cid, {}).get("phone")
                out = customer_details_map.get(cid, {}).get("current_outstanding", Decimal("0.00"))
                cred = customer_kadan_period_map[cid]["credit"]
                paid = customer_kadan_period_map[cid]["paid"]

                customer_kadan_summaries.append(
                    CustomerKadanSummaryResponse(
                        customer_id=cid,
                        customer_name=name,
                        customer_phone=phone,
                        credit_generated=cred,
                        kadan_paid=paid,
                        current_outstanding=out,
                    )
                )

        daily_breakdown_list = [
            DailyBreakdownResponse(
                date=d.strftime("%Y-%m-%d"),
                total_bills=stats["total_bills"],
                total_sales=stats["total_sales"],
                total_paid=stats["total_paid"],
                total_credit=stats["total_credit"],
            )
            for d, stats in sorted(daily_map.items())
        ]

        return ReportResponse(
            report_type=report_type,
            period=ReportPeriodResponse(
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d"),
                timezone="Asia/Kolkata",
            ),
            summary=ReportSummaryResponse(
                total_bills=total_bills_count,
                total_sales=total_sales,
                total_subtotal=total_subtotal,
                total_discount=total_discount,
                total_tax=total_tax,
                total_paid=total_paid,
                total_credit_generated=total_credit_generated,
                average_bill_value=avg_bill,
                total_customers=len(customers_who_purchased),
            ),
            payments=PaymentSummaryResponse(
                total_amount=total_paid,
                transaction_count=total_payment_transactions,
                by_method=dict(payments_by_method),
            ),
            daily_breakdown=daily_breakdown_list,
            bills=bill_details,
            kadan=KadanReportResponse(
                period=KadanPeriodSummaryResponse(
                    credit_generated=k_credit_gen,
                    credit_transactions=k_credit_txs,
                    collected=k_collected,
                    repayment_transactions=k_repay_txs,
                ),
                current=KadanCurrentSummaryResponse(
                    outstanding_amount=total_current_outstanding,
                    customers_with_outstanding=customers_with_outstanding,
                ),
                transactions=kadan_tx_details,
                customers=customer_kadan_summaries,
            )
        )

    async def get_monthly_report(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        month_str: str,
    ) -> ReportResponse:
        try:
            dt = datetime.strptime(month_str, "%Y-%m").date()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid month format. Use YYYY-MM",
            )

        ist = timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")
        start_date = datetime(dt.year, dt.month, 1, tzinfo=ist)
        _, last_day = calendar.monthrange(dt.year, dt.month)
        end_date = start_date + timedelta(days=last_day)

        return await self._generate_report(db, tenant_id, "MONTHLY", start_date, end_date)

    async def get_weekly_report(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        week_start_str: str,
    ) -> ReportResponse:
        try:
            dt = datetime.strptime(week_start_str, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid date format. Use YYYY-MM-DD",
            )

        # Normalize to Monday
        dt = dt - timedelta(days=dt.weekday())

        ist = timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")
        start_date = datetime(dt.year, dt.month, dt.day, tzinfo=ist)
        end_date = start_date + timedelta(days=7)

        return await self._generate_report(db, tenant_id, "WEEKLY", start_date, end_date)

    # ----------------------------------------------------------
    # MOST-SOLD PRODUCT — MONTHLY
    # ----------------------------------------------------------

    async def get_most_sold_product(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        month_str: str,
    ):
        """
        Return the product variant that sold the highest quantity during the
        selected month (Asia/Kolkata timezone).

        month_str: "YYYY-MM"

        Returns MostSoldProductResponse with data=None when the month has no
        completed sales. Never raises HTTP 404 for an empty result.

        Ranking is based exclusively on SUM(bill_items.quantity).
        Historical pricing (bill_items.unit_price / line_total) is used;
        the current variant selling_price is NOT used in any calculation.
        """
        # ── Validate month format ───────────────────────────────
        try:
            dt = datetime.strptime(month_str, "%Y-%m").date()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid month format. Use YYYY-MM",
            )

        # ── Compute IST-aware half-open date range ──────────────
        ist = timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")
        month_start = datetime(dt.year, dt.month, 1, 0, 0, 0, tzinfo=ist)

        # Advance to the first day of the next month
        if dt.month == 12:
            next_month_start = datetime(dt.year + 1, 1, 1, 0, 0, 0, tzinfo=ist)
        else:
            next_month_start = datetime(dt.year, dt.month + 1, 1, 0, 0, 0, tzinfo=ist)

        # ── Query repository ────────────────────────────────────
        row = await report_repository.get_most_sold_variant_for_period(
            db=db,
            tenant_id=tenant_id,
            start_date=month_start,
            end_date=next_month_start,
        )

        # ── Empty month ─────────────────────────────────────────
        if row is None:
            from app.schemas.reports import MostSoldProductResponse
            return MostSoldProductResponse(
                type="success",
                message="No sales found for the selected month",
                data=None,
            )

        # ── Build response ──────────────────────────────────────
        from app.schemas.reports import MostSoldProductResponse, MostSoldVariantData
        return MostSoldProductResponse(
            type="success",
            message="Most sold product fetched successfully",
            data=MostSoldVariantData(
                product_id=row["product_id"],
                variant_id=row["variant_id"],
                product_name=row["product_name"],
                package_quantity=row["package_quantity"],
                unit=row["unit"],
                barcode=row["barcode"],
                sku=row["sku"],
                quantity_sold=row["quantity_sold"],
                total_sales_value=row["total_sales_value"],
                average_selling_price=row["average_selling_price"],
            ),
        )

    # ----------------------------------------------------------
    # MOST-SOLD PRODUCT — LAST 3 MONTHS
    # ----------------------------------------------------------

    async def get_last_3_months_most_sold(
        self,
        db: AsyncSession,
        tenant_id: UUID,
    ):
        """
        Return a month-by-month analysis of the top-selling variant for each
        of the last 3 calendar months (Asia/Kolkata), plus the single overall
        top-selling variant across the full 3-month window.

        "Last 3 months" = current month + 2 preceding months.
        Example: if today is September 2026 → July, August, September 2026.

        Total queries fired: 4
            • 3  × per-month aggregation (one per month window)
            • 1  × full-window aggregation (overall top variant)
        No Python-side iteration over bills or bill_items.
        """
        from app.schemas.reports import (
            Last3MonthsData,
            Last3MonthsResponse,
            MonthlyMostSoldEntry,
            OverallTopSellingVariant,
        )

        # ── Determine current month in IST ──────────────────────
        ist = timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")
        now_ist = datetime.now(tz=ist)

        # Build list of (year, month) tuples oldest → newest
        months = []
        year, month = now_ist.year, now_ist.month
        for _ in range(3):
            months.append((year, month))
            # Go back one month
            if month == 1:
                month = 12
                year -= 1
            else:
                month -= 1
        months.reverse()  # [oldest, middle, current]

        # ── Helper: compute half-open IST bounds for (year, month) ─
        def month_bounds(y: int, m: int):
            start = datetime(y, m, 1, 0, 0, 0, tzinfo=ist)
            if m == 12:
                end = datetime(y + 1, 1, 1, 0, 0, 0, tzinfo=ist)
            else:
                end = datetime(y, m + 1, 1, 0, 0, 0, tzinfo=ist)
            return start, end

        # ── Full 3-month window bounds ──────────────────────────
        window_start, _ = month_bounds(*months[0])   # start of oldest month
        _, window_end = month_bounds(*months[-1])     # end of newest month

        # ── Per-month queries (3 queries) ───────────────────────
        monthly_entries = []
        for y, m in months:
            start, end = month_bounds(y, m)
            row = await report_repository.get_most_sold_variant_for_period(
                db=db,
                tenant_id=tenant_id,
                start_date=start,
                end_date=end,
            )
            month_label = f"{y:04d}-{m:02d}"

            if row is not None:
                monthly_entries.append(
                    MonthlyMostSoldEntry(
                        month=month_label,
                        product_id=row["product_id"],
                        variant_id=row["variant_id"],
                        product_name=row["product_name"],
                        package_quantity=row["package_quantity"],
                        unit=row["unit"],
                        barcode=row["barcode"],
                        sku=row["sku"],
                        quantity_sold=row["quantity_sold"],
                        total_sales_value=row["total_sales_value"],
                        average_selling_price=row["average_selling_price"],
                    )
                )
            # Months with no sales are omitted from the list.
            # (Frontend should handle missing months gracefully.)

        # ── Overall top variant across full window (1 query) ────
        overall_row = await report_repository.get_most_sold_variant_overall(
            db=db,
            tenant_id=tenant_id,
            start_date=window_start,
            end_date=window_end,
        )

        overall = None
        if overall_row is not None:
            overall = OverallTopSellingVariant(
                product_id=overall_row["product_id"],
                variant_id=overall_row["variant_id"],
                product_name=overall_row["product_name"],
                package_quantity=overall_row["package_quantity"],
                unit=overall_row["unit"],
                barcode=overall_row["barcode"],
                sku=overall_row["sku"],
                quantity_sold=overall_row["quantity_sold"],
                total_sales_value=overall_row["total_sales_value"],
                average_selling_price=overall_row["average_selling_price"],
            )

        return Last3MonthsResponse(
            type="success",
            message="Last 3 months sales analysis fetched successfully",
            data=Last3MonthsData(
                months=monthly_entries,
                overall_top_selling_variant=overall,
            ),
        )


report_service = ReportService()
