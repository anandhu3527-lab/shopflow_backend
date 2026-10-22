import uuid
from datetime import datetime, timezone
from decimal import Decimal
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import app
from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine
from app.models.tenant import Tenant
from app.models.user import User
from app.models.role import Role
from app.models.user_role import UserRole
from app.models.subscription import Subscription
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.customer import Customer
from app.models.bill import Bill
from app.models.payment import Payment
from app.models.audit_log import AuditLog

VALID_SERVICE_TOKEN = "local_cryvex_cloud_service_token_secret"
SERVICE_HEADER = {"X-Cryvex-Cloud-Service-Token": VALID_SERVICE_TOKEN}


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    monkeypatch.setattr(settings, "CLOUD_INTERNAL_SERVICE_TOKEN", VALID_SERVICE_TOKEN)



@pytest.fixture
async def seed_data():
    """Seed test tenants, users, products, variants, bills and subscriptions."""
    async with AsyncSessionLocal() as session:
        # 1. Tenant A
        tenant_a = Tenant(
            id=uuid.uuid4(),
            name="Test Shop Alpha",
            business_name="Alpha Retail Ltd",
            phone="9876543210",
            email="alpha@test.com",
            status="ACTIVE",
        )
        session.add(tenant_a)

        # 2. Tenant B (for cross-tenant isolation testing)
        tenant_b = Tenant(
            id=uuid.uuid4(),
            name="Test Shop Beta",
            business_name="Beta Retail Ltd",
            phone="9876543211",
            email="beta@test.com",
            status="ACTIVE",
        )
        session.add(tenant_b)

        # 3. User for Tenant A
        user_a = User(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            name="Alice Owner",
            phone="9876543210",
            email="alice@test.com",
            password_hash="$argon2id$v=19$m=65536,t=3,p=4$dummyhash",
            status="ACTIVE",
        )
        session.add(user_a)

        # Role
        role_res = await session.execute(select(Role).where(Role.name == "OWNER"))
        role = role_res.scalar_one_or_none()
        if not role:
            role = Role(id=uuid.uuid4(), name="OWNER", description="Shop Owner")
            session.add(role)
            await session.flush()

        user_role_a = UserRole(user_id=user_a.id, role_id=role.id)
        session.add(user_role_a)

        # 4. Subscription for Tenant A
        sub_a = Subscription(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            plan="TRIAL",
            status="ACTIVE",
            start_date=datetime.now(timezone.utc),
        )
        session.add(sub_a)

        # 5. Product & Variant for Tenant A
        prod_a = Product(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            name="Organic Coffee Beans",
            description="Premium roast",
            status="ACTIVE",
        )
        session.add(prod_a)
        await session.flush()

        var_a = ProductVariant(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            product_id=prod_a.id,
            package_quantity=Decimal("1.000"),
            unit="KG",
            barcode="8901234567890",
            selling_price=Decimal("450.00"),
            tax_rate=Decimal("5.00"),
            stock_quantity=Decimal("50.000"),
            low_stock_threshold=Decimal("10.000"),
            status="ACTIVE",
        )
        session.add(var_a)

        # 6. Customer for Tenant A
        cust_a = Customer(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            name="John Doe",
            phone="9988776655",
            status="ACTIVE",
        )
        session.add(cust_a)
        await session.flush()

        # 7. Bill for Tenant A
        bill_a = Bill(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            customer_id=cust_a.id,
            bill_number=f"BILL-{uuid.uuid4().hex[:6].upper()}",
            subtotal=Decimal("450.00"),
            discount_amount=Decimal("0.00"),
            tax_amount=Decimal("22.50"),
            total_amount=Decimal("472.50"),
            status="COMPLETED",
            created_by=user_a.id,
        )
        session.add(bill_a)
        await session.flush()

        # 8. Payment for Bill A
        payment_a = Payment(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            bill_id=bill_a.id,
            amount=Decimal("472.50"),
            payment_method="UPI",
            status="COMPLETED",
            created_by=user_a.id,
        )
        session.add(payment_a)

        await session.commit()

        yield {
            "tenant_a": tenant_a,
            "tenant_b": tenant_b,
            "user_a": user_a,
            "sub_a": sub_a,
            "prod_a": prod_a,
            "var_a": var_a,
            "cust_a": cust_a,
            "bill_a": bill_a,
            "payment_a": payment_a,
        }

        # Cleanup
        async with AsyncSessionLocal() as clean_session:
            # Delete in reverse foreign key order
            await clean_session.execute(Payment.__table__.delete().where(Payment.tenant_id.in_([tenant_a.id, tenant_b.id])))
            await clean_session.execute(Bill.__table__.delete().where(Bill.tenant_id.in_([tenant_a.id, tenant_b.id])))
            await clean_session.execute(Customer.__table__.delete().where(Customer.tenant_id.in_([tenant_a.id, tenant_b.id])))
            await clean_session.execute(ProductVariant.__table__.delete().where(ProductVariant.tenant_id.in_([tenant_a.id, tenant_b.id])))
            await clean_session.execute(Product.__table__.delete().where(Product.tenant_id.in_([tenant_a.id, tenant_b.id])))
            await clean_session.execute(Subscription.__table__.delete().where(Subscription.tenant_id.in_([tenant_a.id, tenant_b.id])))
            await clean_session.execute(AuditLog.__table__.delete().where(AuditLog.tenant_id.in_([tenant_a.id, tenant_b.id])))
            await clean_session.execute(UserRole.__table__.delete().where(UserRole.user_id == user_a.id))
            await clean_session.execute(User.__table__.delete().where(User.tenant_id.in_([tenant_a.id, tenant_b.id])))
            await clean_session.execute(Tenant.__table__.delete().where(Tenant.id.in_([tenant_a.id, tenant_b.id])))
            await clean_session.commit()


# ============================================================
# INTEGRATION TESTS: DATA ACCESS & ISOLATION
# ============================================================

@pytest.mark.asyncio
async def test_integration_shop_lifecycle(seed_data):
    """Test retrieving shop details, updating status, and auditing."""
    tenant_a = seed_data["tenant_a"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Get Shop Detail
        res = await client.get(
            f"/api/v1/internal/cloud/shops/{tenant_a.id}",
            headers=SERVICE_HEADER,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == str(tenant_a.id)
        assert data["name"] == "Test Shop Alpha"
        assert data["subscription"]["plan"] == "TRIAL"

        # Update Shop Status to SUSPENDED
        res_patch = await client.patch(
            f"/api/v1/internal/cloud/shops/{tenant_a.id}/status",
            headers=SERVICE_HEADER,
            json={"status": "SUSPENDED", "reason": "Billing overdue"},
        )
        assert res_patch.status_code == 200
        patch_data = res_patch.json()
        assert patch_data["previous_status"] == "ACTIVE"
        assert patch_data["new_status"] == "SUSPENDED"

        # Check Activity Log contains the status change
        res_activity = await client.get(
            f"/api/v1/internal/cloud/shops/{tenant_a.id}/activity",
            headers=SERVICE_HEADER,
        )
        assert res_activity.status_code == 200
        activity_data = res_activity.json()
        assert activity_data["meta"]["total"] >= 1
        actions = [a["action"] for a in activity_data["activity"]]
        assert "CLOUD_SHOP_STATUS_CHANGED" in actions


@pytest.mark.asyncio
async def test_integration_user_and_cross_tenant_isolation(seed_data):
    """Test user management and verify Tenant B cannot access or modify Tenant A's user."""
    tenant_a = seed_data["tenant_a"]
    tenant_b = seed_data["tenant_b"]
    user_a = seed_data["user_a"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # List users for Tenant A
        res_users_a = await client.get(
            f"/api/v1/internal/cloud/shops/{tenant_a.id}/users",
            headers=SERVICE_HEADER,
        )
        assert res_users_a.status_code == 200
        assert len(res_users_a.json()["users"]) == 1
        assert res_users_a.json()["users"][0]["name"] == "Alice Owner"

        # Tenant B tries to access Tenant A's user -> MUST 404
        res_cross_get = await client.get(
            f"/api/v1/internal/cloud/shops/{tenant_b.id}/users/{user_a.id}",
            headers=SERVICE_HEADER,
        )
        assert res_cross_get.status_code == 404

        # Tenant B tries to modify Tenant A's user -> MUST 404
        res_cross_patch = await client.patch(
            f"/api/v1/internal/cloud/shops/{tenant_b.id}/users/{user_a.id}/status",
            headers=SERVICE_HEADER,
            json={"status": "INACTIVE"},
        )
        assert res_cross_patch.status_code == 404

        # Access reset for Tenant A's user
        res_reset = await client.post(
            f"/api/v1/internal/cloud/shops/{tenant_a.id}/users/{user_a.id}/access-reset",
            headers=SERVICE_HEADER,
            json={"reason": "Customer lost credentials"},
        )
        assert res_reset.status_code == 200
        assert res_reset.json()["status"] == "pending_integration"
        assert res_reset.json()["notification_delivery_supported"] is False


@pytest.mark.asyncio
async def test_integration_products_and_stock_summary(seed_data):
    """Test product listing, stock summary, and product detail with variants."""
    tenant_a = seed_data["tenant_a"]
    tenant_b = seed_data["tenant_b"]
    prod_a = seed_data["prod_a"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Stock summary for Tenant A
        res_stock = await client.get(
            f"/api/v1/internal/cloud/shops/{tenant_a.id}/products/stock/summary",
            headers=SERVICE_HEADER,
        )
        assert res_stock.status_code == 200
        stock_data = res_stock.json()
        assert stock_data["total_products"] == 1
        assert stock_data["total_variants"] == 1
        assert Decimal(str(stock_data["total_stock_units"])) == Decimal("50.000")
        assert Decimal(str(stock_data["total_inventory_value"])) == Decimal("22500.00")  # 50 * 450

        # Product detail
        res_prod = await client.get(
            f"/api/v1/internal/cloud/shops/{tenant_a.id}/products/{prod_a.id}",
            headers=SERVICE_HEADER,
        )
        assert res_prod.status_code == 200
        prod_data = res_prod.json()
        assert prod_data["name"] == "Organic Coffee Beans"
        assert len(prod_data["variants"]) == 1
        assert prod_data["variants"][0]["barcode"] == "8901234567890"

        # Tenant B tries to access Tenant A's product -> MUST 404
        res_cross_prod = await client.get(
            f"/api/v1/internal/cloud/shops/{tenant_b.id}/products/{prod_a.id}",
            headers=SERVICE_HEADER,
        )
        assert res_cross_prod.status_code == 404


@pytest.mark.asyncio
async def test_integration_billing_and_revenue(seed_data):
    """Test shop billing summary and bills listing."""
    tenant_a = seed_data["tenant_a"]
    tenant_b = seed_data["tenant_b"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Billing summary for Tenant A
        res_summary = await client.get(
            f"/api/v1/internal/cloud/shops/{tenant_a.id}/billing/summary",
            headers=SERVICE_HEADER,
        )
        assert res_summary.status_code == 200
        sum_data = res_summary.json()
        assert sum_data["total_bills_count"] == 1
        assert sum_data["completed_bills_count"] == 1
        assert Decimal(str(sum_data["total_billed_amount"])) == Decimal("472.50")
        assert Decimal(str(sum_data["total_collected_amount"])) == Decimal("472.50")

        # Tenant B bills should be empty (no cross-shop leakage)
        res_bills_b = await client.get(
            f"/api/v1/internal/cloud/shops/{tenant_b.id}/billing/bills",
            headers=SERVICE_HEADER,
        )
        assert res_bills_b.status_code == 200
        assert len(res_bills_b.json()["bills"]) == 0

        # Global bills endpoint returns Tenant A bill
        res_global_bills = await client.get(
            "/api/v1/internal/cloud/billing/bills",
            headers=SERVICE_HEADER,
        )
        assert res_global_bills.status_code == 200
        assert res_global_bills.json()["meta"]["total"] >= 1


@pytest.mark.asyncio
async def test_integration_subscription_lifecycle(seed_data):
    """Test upgrading, suspending, activating, and downgrading subscriptions."""
    tenant_a = seed_data["tenant_a"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Upgrade to SHOPFLOW
        res_up = await client.post(
            f"/api/v1/internal/cloud/shops/{tenant_a.id}/subscription/upgrade",
            headers=SERVICE_HEADER,
            json={"new_plan": "SHOPFLOW", "reason": "Customer upgraded to ShopFlow plan"},
        )
        assert res_up.status_code == 200
        assert res_up.json()["plan"] == "SHOPFLOW"
        assert res_up.json()["status"] == "ACTIVE"

        # Suspend
        res_sus = await client.post(
            f"/api/v1/internal/cloud/shops/{tenant_a.id}/subscription/suspend",
            headers=SERVICE_HEADER,
            json={"reason": "Suspended for testing"},
        )
        assert res_sus.status_code == 200
        assert res_sus.json()["status"] == "SUSPENDED"

        # Attempting activation on tenant_a (which already has an existing subscription) -> 409 Conflict
        res_act_dup = await client.post(
            f"/api/v1/internal/cloud/shops/{tenant_a.id}/subscription/activate",
            headers=SERVICE_HEADER,
            json={
                "plan": "SHOPFLOW",
                "status": "ACTIVE",
                "start_date": "2026-10-22T00:00:00Z",
                "end_date": "2027-10-22T00:00:00Z",
                "reason": "Duplicate activation attempt on tenant_a",
            },
        )
        assert res_act_dup.status_code == 409
        assert "already has a subscription" in res_act_dup.json()["detail"]

        # Downgrade to TRIAL
        res_down = await client.post(
            f"/api/v1/internal/cloud/shops/{tenant_a.id}/subscription/downgrade",
            headers=SERVICE_HEADER,
            json={"new_plan": "TRIAL", "reason": "Downgraded per customer request"},
        )
        assert res_down.status_code == 200
        assert res_down.json()["plan"] == "TRIAL"

        # Verify audit records for subscription operations on tenant_a
        res_audit = await client.get(
            f"/api/v1/internal/cloud/shops/{tenant_a.id}/audit-logs?entity_type=subscription",
            headers=SERVICE_HEADER,
        )
        assert res_audit.status_code == 200
        audit_items = res_audit.json()["audit_logs"]
        actions = [item["action"] for item in audit_items]
        assert "CLOUD_SUBSCRIPTION_UPGRADED" in actions
        assert "CLOUD_SUBSCRIPTION_SUSPENDED" in actions
        assert "CLOUD_SUBSCRIPTION_DOWNGRADED" in actions


@pytest.mark.asyncio
async def test_subscription_activation_validation_and_audit(seed_data):
    """
    Comprehensive tests for the CRYVEX Cloud internal subscription activation endpoint:
    - 404 on missing tenant
    - 422 on unsupported plan
    - 422 on unsupported/arbitrary status
    - 422 on naive start_date / end_date
    - 422 on end_date <= start_date
    - 422 on missing or empty reason
    - 200 on successful activation of tenant without subscription
    - Explicit response schema verification
    - 409 Conflict on duplicate subscription activation attempt
    - Verification of audit log entry
    """
    tenant_b = seed_data["tenant_b"]  # Created without subscription

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Non-existent tenant -> 404 Not Found
        random_tenant_id = uuid.uuid4()
        res_404 = await client.post(
            f"/api/v1/internal/cloud/shops/{random_tenant_id}/subscription/activate",
            headers=SERVICE_HEADER,
            json={
                "plan": "SHOPFLOW",
                "status": "ACTIVE",
                "start_date": "2026-10-22T00:00:00Z",
                "end_date": "2027-10-22T00:00:00Z",
                "reason": "Activating non-existent shop",
            },
        )
        assert res_404.status_code == 404

        # 2. Unsupported plan -> 422 Unprocessable Entity
        res_bad_plan = await client.post(
            f"/api/v1/internal/cloud/shops/{tenant_b.id}/subscription/activate",
            headers=SERVICE_HEADER,
            json={
                "plan": "GOLD_ULTRA_TIER",
                "status": "ACTIVE",
                "start_date": "2026-10-22T00:00:00Z",
                "end_date": "2027-10-22T00:00:00Z",
                "reason": "Attempting invalid plan",
            },
        )
        assert res_bad_plan.status_code == 422
        assert "Unsupported plan" in str(res_bad_plan.json())

        # Also confirm previously existing plans like PRO are now rejected
        res_pro_rejected = await client.post(
            f"/api/v1/internal/cloud/shops/{tenant_b.id}/subscription/activate",
            headers=SERVICE_HEADER,
            json={
                "plan": "PRO",
                "status": "ACTIVE",
                "start_date": "2026-10-22T00:00:00Z",
                "end_date": "2027-10-22T00:00:00Z",
                "reason": "Attempting removed plan PRO",
            },
        )
        assert res_pro_rejected.status_code == 422
        assert "Unsupported plan" in str(res_pro_rejected.json())

        # 3. Arbitrary/unpermitted status -> 422 Unprocessable Entity
        res_bad_status = await client.post(
            f"/api/v1/internal/cloud/shops/{tenant_b.id}/subscription/activate",
            headers=SERVICE_HEADER,
            json={
                "plan": "SHOPFLOW",
                "status": "EXPIRED",
                "start_date": "2026-10-22T00:00:00Z",
                "end_date": "2027-10-22T00:00:00Z",
                "reason": "Attempting invalid status",
            },
        )
        assert res_bad_status.status_code == 422
        assert "status" in str(res_bad_status.json())

        # 4. Naive start_date (missing timezone) -> 422 Unprocessable Entity
        res_naive_start = await client.post(
            f"/api/v1/internal/cloud/shops/{tenant_b.id}/subscription/activate",
            headers=SERVICE_HEADER,
            json={
                "plan": "SHOPFLOW",
                "status": "ACTIVE",
                "start_date": "2026-10-22T00:00:00",
                "end_date": "2027-10-22T00:00:00Z",
                "reason": "Naive start date",
            },
        )
        assert res_naive_start.status_code == 422
        assert "timezone-aware" in str(res_naive_start.json())

        # 5. Naive end_date (missing timezone) -> 422 Unprocessable Entity
        res_naive_end = await client.post(
            f"/api/v1/internal/cloud/shops/{tenant_b.id}/subscription/activate",
            headers=SERVICE_HEADER,
            json={
                "plan": "SHOPFLOW",
                "status": "ACTIVE",
                "start_date": "2026-10-22T00:00:00Z",
                "end_date": "2027-10-22T00:00:00",
                "reason": "Naive end date",
            },
        )
        assert res_naive_end.status_code == 422
        assert "timezone-aware" in str(res_naive_end.json())

        # 6. end_date <= start_date -> 422 Unprocessable Entity
        res_invalid_range = await client.post(
            f"/api/v1/internal/cloud/shops/{tenant_b.id}/subscription/activate",
            headers=SERVICE_HEADER,
            json={
                "plan": "SHOPFLOW",
                "status": "ACTIVE",
                "start_date": "2027-10-22T00:00:00Z",
                "end_date": "2026-10-22T00:00:00Z",
                "reason": "End before start date",
            },
        )
        assert res_invalid_range.status_code == 422
        assert "end_date must be strictly later than start_date" in str(res_invalid_range.json())

        # 7. Empty / whitespace-only reason -> 422 Unprocessable Entity
        res_empty_reason = await client.post(
            f"/api/v1/internal/cloud/shops/{tenant_b.id}/subscription/activate",
            headers=SERVICE_HEADER,
            json={
                "plan": "SHOPFLOW",
                "status": "ACTIVE",
                "start_date": "2026-10-22T00:00:00Z",
                "end_date": "2027-10-22T00:00:00Z",
                "reason": "   ",
            },
        )
        assert res_empty_reason.status_code == 422
        assert "reason" in str(res_empty_reason.json())

        # 8. Successful activation of tenant_b
        res_success = await client.post(
            f"/api/v1/internal/cloud/shops/{tenant_b.id}/subscription/activate",
            headers=SERVICE_HEADER,
            json={
                "plan": "shopflow",  # Normalized to SHOPFLOW
                "status": "ACTIVE",
                "start_date": "2026-10-22T10:00:00Z",
                "end_date": "2027-10-22T10:00:00Z",
                "reason": "Initial activation for shop B by cloud admin",
            },
        )
        assert res_success.status_code == 200
        data = res_success.json()
        assert data["success"] is True
        assert data["tenant_id"] == str(tenant_b.id)
        assert data["plan"] == "SHOPFLOW"
        assert data["status"] == "ACTIVE"
        assert "start_date" in data and data["start_date"].startswith("2026-10-22")
        assert "end_date" in data and data["end_date"].startswith("2027-10-22")
        assert "subscription_id" in data and data["subscription_id"] is not None
        assert "created_at" in data and data["created_at"] is not None
        assert "updated_at" in data and data["updated_at"] is not None
        assert data["message"] == "Subscription activated successfully"

        # 9. Duplicate subscription activation -> 409 Conflict
        res_duplicate = await client.post(
            f"/api/v1/internal/cloud/shops/{tenant_b.id}/subscription/activate",
            headers=SERVICE_HEADER,
            json={
                "plan": "TRIAL",
                "status": "ACTIVE",
                "start_date": "2026-10-22T10:00:00Z",
                "end_date": "2027-10-22T10:00:00Z",
                "reason": "Attempting second activation",
            },
        )
        assert res_duplicate.status_code == 409
        assert "already has a subscription" in res_duplicate.json()["detail"]

        # 10. Audit log verification
        res_audit = await client.get(
            f"/api/v1/internal/cloud/shops/{tenant_b.id}/audit-logs?entity_type=subscription",
            headers=SERVICE_HEADER,
        )
        assert res_audit.status_code == 200
        audit_items = res_audit.json()["audit_logs"]
        assert len(audit_items) >= 1
        act_event = next(
            (item for item in audit_items if item["action"] == "CLOUD_SUBSCRIPTION_ACTIVATED"),
            None,
        )
        assert act_event is not None
        assert act_event["new_values"]["reason"] == "Initial activation for shop B by cloud admin"
        assert act_event["new_values"]["actor"] == "CRYVEX_CLOUD_SERVICE"
        assert act_event["new_values"]["plan"] == "SHOPFLOW"
        assert act_event["new_values"]["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_integration_usage_and_support(seed_data):
    """Test shop usage metrics and support inquiry for existing shop."""
    tenant_a = seed_data["tenant_a"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Usage
        res_usage = await client.get(
            f"/api/v1/internal/cloud/shops/{tenant_a.id}/usage",
            headers=SERVICE_HEADER,
        )
        assert res_usage.status_code == 200
        usage = res_usage.json()
        assert usage["total_bills"] == 1
        assert usage["total_products"] == 1
        assert usage["total_users"] == 1
        assert usage["total_customers"] == 1

        # Support endpoint reports truthfully
        res_support = await client.get(
            f"/api/v1/internal/cloud/shops/{tenant_a.id}/support",
            headers=SERVICE_HEADER,
        )
        assert res_support.status_code == 200
        support = res_support.json()
        assert support["supported"] is False
        assert "does not currently have an in-database customer support ticket model" in support["message"]


@pytest.mark.asyncio
async def test_integration_customers_and_user_activity(seed_data):
    """Test customer listing, tenant isolation for customers, and user activity."""
    tenant_a = seed_data["tenant_a"]
    tenant_b = seed_data["tenant_b"]
    user_a = seed_data["user_a"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Customers list for Tenant A
        res_cust_a = await client.get(
            f"/api/v1/internal/cloud/shops/{tenant_a.id}/customers",
            headers=SERVICE_HEADER,
        )
        assert res_cust_a.status_code == 200
        cust_data = res_cust_a.json()
        assert cust_data["meta"]["total"] == 1
        assert cust_data["customers"][0]["name"] == "John Doe"

        # Tenant B customer list should be empty
        res_cust_b = await client.get(
            f"/api/v1/internal/cloud/shops/{tenant_b.id}/customers",
            headers=SERVICE_HEADER,
        )
        assert res_cust_b.status_code == 200
        assert res_cust_b.json()["meta"]["total"] == 0

        # User activity for user_a
        res_u_act = await client.get(
            f"/api/v1/internal/cloud/shops/{tenant_a.id}/users/{user_a.id}/activity",
            headers=SERVICE_HEADER,
        )
        assert res_u_act.status_code == 200
        assert "activity" in res_u_act.json()

        # Subscription cancel
        res_cancel = await client.post(
            f"/api/v1/internal/cloud/shops/{tenant_a.id}/subscription/cancel",
            headers=SERVICE_HEADER,
            json={"reason": "Customer requested cancellation"},
        )
        assert res_cancel.status_code == 200
        assert res_cancel.json()["status"] == "CANCELLED"


@pytest.mark.asyncio
async def test_shops_without_subscription_discovery(seed_data):
    """Test discovery of shops without subscriptions or with incomplete subscriptions."""
    tenant_a = seed_data["tenant_a"]
    tenant_b = seed_data["tenant_b"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Auth check
        res_no_auth = await client.get("/api/v1/internal/cloud/shops/without-subscription")
        assert res_no_auth.status_code == 401

        res_bad_auth = await client.get(
            "/api/v1/internal/cloud/shops/without-subscription",
            headers={"X-Cryvex-Cloud-Service-Token": "bad_token"},
        )
        assert res_bad_auth.status_code == 403

        # 2. Query with valid service token
        res = await client.get(
            "/api/v1/internal/cloud/shops/without-subscription",
            headers=SERVICE_HEADER,
        )
        assert res.status_code == 200
        data = res.json()
        assert "meta" in data
        assert "shops" in data

        # Tenant B must be present with configuration status MISSING
        tenant_b_items = [s for s in data["shops"] if s["tenant_id"] == str(tenant_b.id)]
        assert len(tenant_b_items) == 1
        assert tenant_b_items[0]["subscription_configuration_status"] == "MISSING"
        assert tenant_b_items[0]["subscription_id"] is None
        assert "subscription_record" in tenant_b_items[0]["missing_fields"]
        assert tenant_b_items[0]["name"] == "Test Shop Beta"

        # Tenant A has a valid active subscription and must NOT be in the results
        tenant_a_items = [s for s in data["shops"] if s["tenant_id"] == str(tenant_a.id)]
        assert len(tenant_a_items) == 0

    # 3. Add an incomplete subscription (blank plan) to verify INCOMPLETE handling
    async with AsyncSessionLocal() as session:
        tenant_c = Tenant(
            id=uuid.uuid4(),
            name="Test Shop Gamma",
            business_name="Gamma Retail Ltd",
            phone="9876543212",
            status="ACTIVE",
        )
        session.add(tenant_c)
        await session.flush()

        sub_c = Subscription(
            id=uuid.uuid4(),
            tenant_id=tenant_c.id,
            plan="",  # Blank plan -> incomplete
            status="ACTIVE",
            start_date=datetime.now(timezone.utc),
        )
        session.add(sub_c)
        await session.commit()

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res_c = await client.get(
                "/api/v1/internal/cloud/shops/without-subscription",
                headers=SERVICE_HEADER,
            )
            assert res_c.status_code == 200
            data_c = res_c.json()
            gamma_items = [s for s in data_c["shops"] if s["tenant_id"] == str(tenant_c.id)]
            assert len(gamma_items) == 1
            assert gamma_items[0]["subscription_configuration_status"] == "INCOMPLETE"
            assert gamma_items[0]["subscription_id"] == str(sub_c.id)
            assert "plan" in gamma_items[0]["missing_fields"]
    finally:
        async with AsyncSessionLocal() as clean_session:
            await clean_session.execute(Subscription.__table__.delete().where(Subscription.tenant_id == tenant_c.id))
            await clean_session.execute(Tenant.__table__.delete().where(Tenant.id == tenant_c.id))
            await clean_session.commit()


@pytest.mark.asyncio
async def test_all_subscriptions_discovery(seed_data):
    """Test retrieving all shop subscriptions with pagination, filtering, and tenant joins."""
    tenant_a = seed_data["tenant_a"]
    tenant_b = seed_data["tenant_b"]
    sub_a = seed_data["sub_a"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Auth check
        res_no_auth = await client.get("/api/v1/internal/cloud/subscriptions")
        assert res_no_auth.status_code == 401

        res_bad_auth = await client.get(
            "/api/v1/internal/cloud/subscriptions",
            headers={"X-Cryvex-Cloud-Service-Token": "bad_token"},
        )
        assert res_bad_auth.status_code == 403

        # 2. Get all subscriptions
        res = await client.get(
            "/api/v1/internal/cloud/subscriptions",
            headers=SERVICE_HEADER,
        )
        assert res.status_code == 200
        data = res.json()
        assert "meta" in data
        assert "subscriptions" in data

        # Tenant A's subscription must be present with joined tenant details
        sub_items = [s for s in data["subscriptions"] if s["id"] == str(sub_a.id)]
        assert len(sub_items) == 1
        sub_record = sub_items[0]
        assert sub_record["tenant_id"] == str(tenant_a.id)
        assert sub_record["shop_name"] == "Test Shop Alpha"
        assert sub_record["business_name"] == "Alpha Retail Ltd"
        assert sub_record["shop_status"] == "ACTIVE"
        assert sub_record["plan"] == "TRIAL"
        assert sub_record["status"] == "ACTIVE"
        assert "start_date" in sub_record
        assert "created_at" in sub_record

        # Tenant B has no subscription and must NOT appear in subscriptions list
        tenant_b_subs = [s for s in data["subscriptions"] if s["tenant_id"] == str(tenant_b.id)]
        assert len(tenant_b_subs) == 0

        # 3. Filter by plan
        res_plan = await client.get(
            "/api/v1/internal/cloud/subscriptions?plan=TRIAL",
            headers=SERVICE_HEADER,
        )
        assert res_plan.status_code == 200
        for s in res_plan.json()["subscriptions"]:
            assert s["plan"].upper() == "TRIAL"

        # 4. Filter by status
        res_status = await client.get(
            "/api/v1/internal/cloud/subscriptions?status=ACTIVE",
            headers=SERVICE_HEADER,
        )
        assert res_status.status_code == 200
        for s in res_status.json()["subscriptions"]:
            assert s["status"].upper() == "ACTIVE"

        # 5. Filter with non-matching plan returns HTTP 200 with empty list
        res_empty = await client.get(
            "/api/v1/internal/cloud/subscriptions?plan=NONEXISTENT_PLAN_XYZ",
            headers=SERVICE_HEADER,
        )
        assert res_empty.status_code == 200
        assert res_empty.json()["meta"]["total"] == 0
        assert res_empty.json()["subscriptions"] == []

        # 6. Bounded pagination
        res_page = await client.get(
            "/api/v1/internal/cloud/subscriptions?limit=1&offset=0",
            headers=SERVICE_HEADER,
        )
        assert res_page.status_code == 200
        assert res_page.json()["meta"]["limit"] == 1
        assert len(res_page.json()["subscriptions"]) <= 1


