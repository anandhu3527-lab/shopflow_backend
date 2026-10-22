from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, engine
from app.api.v1.internal.cloud.auth import verify_cloud_service_token
from app.api.v1.internal.cloud.schemas import (
    BillsOverviewMetrics,
    OverallDashboardMetrics,
    SubscriptionOverviewMetrics,
    SystemHealthResponse,
)
from app.models.bill import Bill
from app.models.payment import Payment
from app.models.subscription import Subscription
from app.models.tenant import Tenant
from app.models.user import User

router = APIRouter(
    prefix="/overview",
    tags=["Cloud Internal - Overview"],
    dependencies=[Depends(verify_cloud_service_token)],
)


@router.get("", response_model=OverallDashboardMetrics)
async def get_overall_dashboard(
    db: AsyncSession = Depends(get_db),
):
    """
    Get aggregate platform KPIs across all shops for CRYVEX Cloud dashboard.
    Uses efficient SQL aggregate queries.
    """
    now_utc = datetime.now(timezone.utc)
    today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = today_start.replace(day=1)

    # 1. Total shops
    total_shops_res = await db.execute(select(func.count(Tenant.id)))
    total_shops = total_shops_res.scalar() or 0

    # 2. Active shops
    active_shops_res = await db.execute(
        select(func.count(Tenant.id)).where(Tenant.status == "ACTIVE")
    )
    active_shops = active_shops_res.scalar() or 0

    # 3. Trial shops (active subscription on TRIAL plan or tenant TRIAL status)
    trial_shops_res = await db.execute(
        select(func.count(func.distinct(Subscription.tenant_id))).where(
            func.upper(Subscription.plan) == "TRIAL"
        )
    )
    trial_shops = trial_shops_res.scalar() or 0

    # 4. Suspended shops
    suspended_shops_res = await db.execute(
        select(func.count(Tenant.id)).where(Tenant.status == "SUSPENDED")
    )
    suspended_shops = suspended_shops_res.scalar() or 0

    # 5. Expired shops
    expired_shops_res = await db.execute(
        select(func.count(Tenant.id)).where(Tenant.status == "EXPIRED")
    )
    expired_shops = expired_shops_res.scalar() or 0

    # 6. New shops this month
    new_shops_res = await db.execute(
        select(func.count(Tenant.id)).where(Tenant.created_at >= month_start)
    )
    new_shops_this_month = new_shops_res.scalar() or 0

    # 7. Active users
    active_users_res = await db.execute(
        select(func.count(User.id)).where(User.status == "ACTIVE")
    )
    active_users = active_users_res.scalar() or 0

    # 8. Bills generated today
    bills_today_res = await db.execute(
        select(func.count(Bill.id)).where(Bill.created_at >= today_start)
    )
    bills_generated_today = bills_today_res.scalar() or 0

    # 9. Monthly revenue (completed payments during current month)
    monthly_rev_res = await db.execute(
        select(func.coalesce(func.sum(Payment.amount), Decimal("0.00"))).where(
            Payment.status == "COMPLETED",
            Payment.created_at >= month_start,
        )
    )
    monthly_revenue = monthly_rev_res.scalar() or Decimal("0.00")

    return OverallDashboardMetrics(
        total_shops=total_shops,
        active_shops=active_shops,
        trial_shops=trial_shops,
        suspended_shops=suspended_shops,
        expired_shops=expired_shops,
        new_shops_this_month=new_shops_this_month,
        active_users=active_users,
        bills_generated_today=bills_generated_today,
        monthly_revenue=monthly_revenue,
    )


@router.get("/health", response_model=SystemHealthResponse)
async def get_overview_health():
    """
    Check API and database connectivity for CRYVEX Cloud monitoring.
    Never exposes internal secrets or connection strings.
    """
    now = datetime.now(timezone.utc)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            val = result.scalar()
            db_ok = (val == 1)
        
        status_val: Literal["ok", "degraded"] = "ok" if db_ok else "degraded"
        return SystemHealthResponse(
            status=status_val,
            database_connected=db_ok,
            service="shopflow-api-internal-cloud",
            timestamp=now,
        )
    except Exception:
        return SystemHealthResponse(
            status="error",
            database_connected=False,
            service="shopflow-api-internal-cloud",
            timestamp=now,
        )


@router.get("/subscriptions", response_model=SubscriptionOverviewMetrics)
async def get_overview_subscriptions(
    db: AsyncSession = Depends(get_db),
):
    """
    Overview of subscription plans, statuses, and upcoming expirations.
    """
    now_utc = datetime.now(timezone.utc)
    in_7_days = now_utc + timedelta(days=7)

    # Total subscriptions
    total_res = await db.execute(select(func.count(Subscription.id)))
    total_subscriptions = total_res.scalar() or 0

    # By plan
    plan_rows = await db.execute(
        select(Subscription.plan, func.count(Subscription.id)).group_by(Subscription.plan)
    )
    by_plan = {row[0]: row[1] for row in plan_rows.fetchall()}

    # By status
    status_rows = await db.execute(
        select(Subscription.status, func.count(Subscription.id)).group_by(Subscription.status)
    )
    by_status = {row[0]: row[1] for row in status_rows.fetchall()}

    # Expiring soon
    expiring_res = await db.execute(
        select(func.count(Subscription.id)).where(
            Subscription.end_date.is_not(None),
            Subscription.end_date >= now_utc,
            Subscription.end_date <= in_7_days,
            Subscription.status == "ACTIVE",
        )
    )
    expiring_soon_count = expiring_res.scalar() or 0

    return SubscriptionOverviewMetrics(
        total_subscriptions=total_subscriptions,
        by_plan=by_plan,
        by_status=by_status,
        expiring_soon_count=expiring_soon_count,
    )


@router.get("/bills", response_model=BillsOverviewMetrics)
async def get_overview_bills(
    db: AsyncSession = Depends(get_db),
):
    """
    Overview of billing metrics across the platform.
    """
    now_utc = datetime.now(timezone.utc)
    today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = today_start.replace(day=1)

    # Total bills all time
    total_res = await db.execute(select(func.count(Bill.id)))
    total_bills = total_res.scalar() or 0

    # Bills today
    today_res = await db.execute(
        select(func.count(Bill.id)).where(Bill.created_at >= today_start)
    )
    bills_today = today_res.scalar() or 0

    # Bills this month
    month_res = await db.execute(
        select(func.count(Bill.id)).where(Bill.created_at >= month_start)
    )
    bills_this_month = month_res.scalar() or 0

    # Total billed amount for completed/non-cancelled bills
    billed_res = await db.execute(
        select(func.coalesce(func.sum(Bill.total_amount), Decimal("0.00"))).where(
            Bill.status != "CANCELLED"
        )
    )
    total_billed = billed_res.scalar() or Decimal("0.00")

    # Total collected revenue
    collected_res = await db.execute(
        select(func.coalesce(func.sum(Payment.amount), Decimal("0.00"))).where(
            Payment.status == "COMPLETED"
        )
    )
    total_collected = collected_res.scalar() or Decimal("0.00")

    # By status
    status_rows = await db.execute(
        select(Bill.status, func.count(Bill.id)).group_by(Bill.status)
    )
    by_status = {row[0]: row[1] for row in status_rows.fetchall()}

    return BillsOverviewMetrics(
        total_bills_all_time=total_bills,
        bills_today=bills_today,
        bills_this_month=bills_this_month,
        total_billed_amount=total_billed,
        total_collected_revenue=total_collected,
        by_status=by_status,
    )
