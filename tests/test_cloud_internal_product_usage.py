import uuid
from datetime import datetime, timezone
from decimal import Decimal
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.main import app
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.bill import Bill
from app.models.bill_item import BillItem
from app.models.customer import Customer
from app.models.payment import Payment
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.role import Role
from app.models.tenant import Tenant
from app.models.user import User
from app.models.user_role import UserRole

VALID_SERVICE_TOKEN = "local_cryvex_cloud_service_token_secret"
SERVICE_HEADER = {"X-Cryvex-Cloud-Service-Token": VALID_SERVICE_TOKEN}


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """Ensure the cloud internal service token is configured."""
    monkeypatch.setattr(settings, "CLOUD_INTERNAL_SERVICE_TOKEN", VALID_SERVICE_TOKEN)


# ============================================================
# 1. REPRODUCE ORIGINAL INVALID-FIELD ERROR SCENARIO
# ============================================================

def test_reproduce_original_invalid_bill_item_attribute():
    """
    Reproduce the reported issue:
    `AttributeError: type object 'BillItem' has no attribute 'total_amount'`
    
    Verifies that BillItem does not have `total_amount` (which belongs to Bill),
    and that attempting to construct a query referencing BillItem.total_amount
    raises AttributeError.
    """
    assert not hasattr(BillItem, "total_amount")
    assert hasattr(BillItem, "line_total")

    with pytest.raises(AttributeError) as exc_info:
        _ = BillItem.total_amount

    assert "total_amount" in str(exc_info.value)


# ============================================================
# FIXTURES FOR PRODUCT USAGE TESTS
# ============================================================

@pytest.fixture
async def usage_test_data():
    """
    Seed isolated test tenants, products, variants, bills, and bill items
    following ShopFlow billing semantics.
    """
    async with AsyncSessionLocal() as session:
        # Tenant A (Primary test shop)
        tenant_a = Tenant(
            id=uuid.uuid4(),
            name="Usage Shop Alpha",
            business_name="Alpha Retail Ltd",
            phone="9876543220",
            email="usage_alpha@test.com",
            status="ACTIVE",
        )
        session.add(tenant_a)

        # Tenant B (For cross-tenant isolation)
        tenant_b = Tenant(
            id=uuid.uuid4(),
            name="Usage Shop Beta",
            business_name="Beta Retail Ltd",
            phone="9876543221",
            email="usage_beta@test.com",
            status="ACTIVE",
        )
        session.add(tenant_b)

        # Tenant C (Empty shop: 0 products, 0 bills)
        tenant_c = Tenant(
            id=uuid.uuid4(),
            name="Usage Shop Gamma",
            business_name="Gamma Retail Ltd",
            phone="9876543222",
            email="usage_gamma@test.com",
            status="ACTIVE",
        )
        session.add(tenant_c)

        # Users
        user_a = User(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            name="Alice Alpha",
            phone="9876543220",
            email="alice_usage@test.com",
            password_hash="$dummy$",
            status="ACTIVE",
        )
        user_b = User(
            id=uuid.uuid4(),
            tenant_id=tenant_b.id,
            name="Bob Beta",
            phone="9876543221",
            email="bob_usage@test.com",
            password_hash="$dummy$",
            status="ACTIVE",
        )
        session.add_all([user_a, user_b])
        await session.flush()

        # Tenant A: Products
        # Prod 1: Coffee (2 variants)
        prod_a1 = Product(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            name="Coffee Beans",
            status="ACTIVE",
        )
        # Prod 2: Green Tea (1 variant)
        prod_a2 = Product(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            name="Green Tea",
            status="ACTIVE",
        )
        # Prod 3: Honey (1 variant, never sold - catalog only)
        prod_a3 = Product(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            name="Wild Honey",
            status="ACTIVE",
        )

        # Tenant B: Products
        prod_b1 = Product(
            id=uuid.uuid4(),
            tenant_id=tenant_b.id,
            name="Beta Exclusive Widget",
            status="ACTIVE",
        )
        session.add_all([prod_a1, prod_a2, prod_a3, prod_b1])
        await session.flush()

        # Variants
        # Coffee 250g
        var_a1_1 = ProductVariant(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            product_id=prod_a1.id,
            package_quantity=Decimal("0.250"),
            unit="KG",
            barcode="A1_1_" + uuid.uuid4().hex[:8],
            selling_price=Decimal("150.00"),
            tax_rate=Decimal("5.00"),
            stock_quantity=Decimal("50.000"),
            low_stock_threshold=Decimal("5.000"),
            status="ACTIVE",
        )
        # Coffee 1kg
        var_a1_2 = ProductVariant(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            product_id=prod_a1.id,
            package_quantity=Decimal("1.000"),
            unit="KG",
            barcode="A1_2_" + uuid.uuid4().hex[:8],
            selling_price=Decimal("500.00"),
            tax_rate=Decimal("5.00"),
            stock_quantity=Decimal("20.000"),
            low_stock_threshold=Decimal("2.000"),
            status="ACTIVE",
        )
        # Green Tea Box
        var_a2_1 = ProductVariant(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            product_id=prod_a2.id,
            package_quantity=Decimal("1.000"),
            unit="BOX",
            barcode="A2_1_" + uuid.uuid4().hex[:8],
            selling_price=Decimal("200.00"),
            tax_rate=Decimal("0.00"),
            stock_quantity=Decimal("30.000"),
            low_stock_threshold=Decimal("5.000"),
            status="ACTIVE",
        )
        # Honey Jar
        var_a3_1 = ProductVariant(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            product_id=prod_a3.id,
            package_quantity=Decimal("0.500"),
            unit="KG",
            barcode="A3_1_" + uuid.uuid4().hex[:8],
            selling_price=Decimal("300.00"),
            tax_rate=Decimal("5.00"),
            stock_quantity=Decimal("10.000"),
            low_stock_threshold=Decimal("2.000"),
            status="ACTIVE",
        )
        # Tenant B Variant
        var_b1_1 = ProductVariant(
            id=uuid.uuid4(),
            tenant_id=tenant_b.id,
            product_id=prod_b1.id,
            package_quantity=Decimal("1.000"),
            unit="PCS",
            barcode="B1_1_" + uuid.uuid4().hex[:8],
            selling_price=Decimal("1000.00"),
            tax_rate=Decimal("18.00"),
            stock_quantity=Decimal("100.000"),
            low_stock_threshold=Decimal("10.000"),
            status="ACTIVE",
        )
        session.add_all([var_a1_1, var_a1_2, var_a2_1, var_a3_1, var_b1_1])
        await session.flush()

        # Bills for Tenant A
        # Bill 1 (COMPLETED):
        # Item 1: Coffee 250g, qty=2, unit_price=150.00, gross=300.00, tax_rate=5%, tax=15.00, line_total=315.00
        # Item 2: Green Tea, qty=1, unit_price=200.00, gross=200.00, tax_rate=0%, tax=0.00, line_total=200.00
        bill_a1 = Bill(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            bill_number=f"BILL-A1-{uuid.uuid4().hex[:4].upper()}",
            subtotal=Decimal("500.00"),
            discount_amount=Decimal("0.00"),
            tax_amount=Decimal("15.00"),
            total_amount=Decimal("515.00"),
            status="COMPLETED",
            created_by=user_a.id,
        )
        session.add(bill_a1)
        await session.flush()

        item_a1_1 = BillItem(
            id=uuid.uuid4(),
            bill_id=bill_a1.id,
            product_id=prod_a1.id,
            product_variant_id=var_a1_1.id,
            item_name="Coffee Beans",
            quantity=Decimal("2.000"),
            unit_price=Decimal("150.00"),
            discount_amount=Decimal("0.00"),
            tax_rate=Decimal("5.00"),
            tax_amount=Decimal("15.00"),
            line_total=Decimal("315.00"),
        )
        item_a1_2 = BillItem(
            id=uuid.uuid4(),
            bill_id=bill_a1.id,
            product_id=prod_a2.id,
            product_variant_id=var_a2_1.id,
            item_name="Green Tea",
            quantity=Decimal("1.000"),
            unit_price=Decimal("200.00"),
            discount_amount=Decimal("0.00"),
            tax_rate=Decimal("0.00"),
            tax_amount=Decimal("0.00"),
            line_total=Decimal("200.00"),
        )
        session.add_all([item_a1_1, item_a1_2])

        # Bill 2 (COMPLETED) for Tenant A:
        # Item 3: Coffee 1kg, qty=1, unit_price=500.00, gross=500.00, tax_rate=5%, tax=25.00, line_total=525.00
        bill_a2 = Bill(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            bill_number=f"BILL-A2-{uuid.uuid4().hex[:4].upper()}",
            subtotal=Decimal("500.00"),
            discount_amount=Decimal("0.00"),
            tax_amount=Decimal("25.00"),
            total_amount=Decimal("525.00"),
            status="COMPLETED",
            created_by=user_a.id,
        )
        session.add(bill_a2)
        await session.flush()

        item_a2_1 = BillItem(
            id=uuid.uuid4(),
            bill_id=bill_a2.id,
            product_id=prod_a1.id,
            product_variant_id=var_a1_2.id,
            item_name="Coffee Beans",
            quantity=Decimal("1.000"),
            unit_price=Decimal("500.00"),
            discount_amount=Decimal("0.00"),
            tax_rate=Decimal("5.00"),
            tax_amount=Decimal("25.00"),
            line_total=Decimal("525.00"),
        )
        session.add(item_a2_1)

        # Bill 3 (CANCELLED) for Tenant A:
        # Should NOT count towards sales, revenue, or distinct products sold
        bill_a3_cancelled = Bill(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            bill_number=f"BILL-A3-{uuid.uuid4().hex[:4].upper()}",
            subtotal=Decimal("300.00"),
            discount_amount=Decimal("0.00"),
            tax_amount=Decimal("15.00"),
            total_amount=Decimal("315.00"),
            status="CANCELLED",
            created_by=user_a.id,
        )
        session.add(bill_a3_cancelled)
        await session.flush()

        item_a3_cancelled = BillItem(
            id=uuid.uuid4(),
            bill_id=bill_a3_cancelled.id,
            product_id=prod_a3.id,
            product_variant_id=var_a3_1.id,
            item_name="Wild Honey",
            quantity=Decimal("1.000"),
            unit_price=Decimal("300.00"),
            discount_amount=Decimal("0.00"),
            tax_rate=Decimal("5.00"),
            tax_amount=Decimal("15.00"),
            line_total=Decimal("315.00"),
        )
        session.add(item_a3_cancelled)

        # Bill 4 for Tenant B:
        bill_b1 = Bill(
            id=uuid.uuid4(),
            tenant_id=tenant_b.id,
            bill_number=f"BILL-B1-{uuid.uuid4().hex[:4].upper()}",
            subtotal=Decimal("2000.00"),
            discount_amount=Decimal("0.00"),
            tax_amount=Decimal("360.00"),
            total_amount=Decimal("2360.00"),
            status="COMPLETED",
            created_by=user_b.id,
        )
        session.add(bill_b1)
        await session.flush()

        item_b1_1 = BillItem(
            id=uuid.uuid4(),
            bill_id=bill_b1.id,
            product_id=prod_b1.id,
            product_variant_id=var_b1_1.id,
            item_name="Beta Exclusive Widget",
            quantity=Decimal("2.000"),
            unit_price=Decimal("1000.00"),
            discount_amount=Decimal("0.00"),
            tax_rate=Decimal("18.00"),
            tax_amount=Decimal("360.00"),
            line_total=Decimal("2360.00"),
        )
        session.add(item_b1_1)

        await session.commit()

        test_data = {
            "tenant_a": tenant_a,
            "tenant_b": tenant_b,
            "tenant_c": tenant_c,
            "user_a": user_a,
            "user_b": user_b,
            "prod_a1": prod_a1,
            "prod_a2": prod_a2,
            "prod_a3": prod_a3,
            "prod_b1": prod_b1,
        }

    yield test_data

    # Cleanup after tests
    async with AsyncSessionLocal() as clean_session:
        tenant_ids = [tenant_a.id, tenant_b.id, tenant_c.id]
        # Delete BillItems
        bill_ids_stmt = select(Bill.id).where(Bill.tenant_id.in_(tenant_ids))
        bill_ids_res = await clean_session.execute(bill_ids_stmt)
        bill_ids = bill_ids_res.scalars().all()
        if bill_ids:
            await clean_session.execute(
                BillItem.__table__.delete().where(BillItem.bill_id.in_(bill_ids))
            )
        await clean_session.execute(
            Bill.__table__.delete().where(Bill.tenant_id.in_(tenant_ids))
        )
        await clean_session.execute(
            ProductVariant.__table__.delete().where(ProductVariant.tenant_id.in_(tenant_ids))
        )
        await clean_session.execute(
            Product.__table__.delete().where(Product.tenant_id.in_(tenant_ids))
        )
        await clean_session.execute(
            User.__table__.delete().where(User.tenant_id.in_(tenant_ids))
        )
        await clean_session.execute(
            Tenant.__table__.delete().where(Tenant.id.in_(tenant_ids))
        )
        await clean_session.commit()


# ============================================================
# 2. SUCCESSFUL RESPONSE & REVENUE CALCULATION TESTS
# ============================================================

@pytest.mark.asyncio
async def test_product_usage_success_and_revenue_calculation(usage_test_data):
    """
    Verifies:
    1. Endpoint returns 200 with CloudProductUsageResponse.
    2. Revenue calculation matches actual ShopFlow billing semantics (SUM(BillItem.line_total)).
    3. Coffee Beans revenue combines both variants (315.00 + 525.00 = 840.00) and units (2 + 1 = 3.000).
    4. Green Tea revenue is 200.00 and units is 1.000.
    5. Order by revenue descending places Coffee Beans first, then Green Tea.
    6. Cancelled bills are excluded (Wild Honey has 0 sales).
    7. Total catalog products = 3, distinct sold = 2, utilization = 66.67%.
    """
    tenant_a = usage_test_data["tenant_a"]
    prod_a1 = usage_test_data["prod_a1"]
    prod_a2 = usage_test_data["prod_a2"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(
            f"/api/v1/internal/cloud/shops/{tenant_a.id}/products/usage",
            headers=SERVICE_HEADER,
        )
        assert res.status_code == 200
        data = res.json()

        # Contract verification
        assert data["tenant_id"] == str(tenant_a.id)
        assert "top_selling_products" in data
        assert "total_distinct_products_sold" in data
        assert "total_catalog_products" in data
        assert "catalog_utilization_percent" in data

        # Product count and utilization
        assert data["total_catalog_products"] == 3
        assert data["total_distinct_products_sold"] == 2
        # 2 / 3 * 100 = 66.67%
        assert Decimal(str(data["catalog_utilization_percent"])) == Decimal("66.67")

        # Top selling items verification
        top_items = data["top_selling_products"]
        assert len(top_items) == 2

        # 1st item: Coffee Beans (combined across 2 variants)
        assert top_items[0]["product_id"] == str(prod_a1.id)
        assert top_items[0]["product_name"] == "Coffee Beans"
        assert Decimal(str(top_items[0]["units_sold"])) == Decimal("3.000")
        assert Decimal(str(top_items[0]["revenue_generated"])) == Decimal("840.00")

        # 2nd item: Green Tea
        assert top_items[1]["product_id"] == str(prod_a2.id)
        assert top_items[1]["product_name"] == "Green Tea"
        assert Decimal(str(top_items[1]["units_sold"])) == Decimal("1.000")
        assert Decimal(str(top_items[1]["revenue_generated"])) == Decimal("200.00")


# ============================================================
# 3. TENANT ISOLATION TESTS
# ============================================================

@pytest.mark.asyncio
async def test_product_usage_tenant_isolation(usage_test_data):
    """
    Verifies:
    1. Tenant A only sees Tenant A's products and revenue.
    2. Tenant B only sees Tenant B's products and revenue.
    3. Beta's 2360.00 revenue never leaks into Alpha's analytics.
    """
    tenant_a = usage_test_data["tenant_a"]
    tenant_b = usage_test_data["tenant_b"]
    prod_b1 = usage_test_data["prod_b1"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Check Tenant B
        res_b = await client.get(
            f"/api/v1/internal/cloud/shops/{tenant_b.id}/products/usage",
            headers=SERVICE_HEADER,
        )
        assert res_b.status_code == 200
        data_b = res_b.json()

        assert data_b["tenant_id"] == str(tenant_b.id)
        assert data_b["total_catalog_products"] == 1
        assert data_b["total_distinct_products_sold"] == 1
        assert Decimal(str(data_b["catalog_utilization_percent"])) == Decimal("100.00")

        top_b = data_b["top_selling_products"]
        assert len(top_b) == 1
        assert top_b[0]["product_id"] == str(prod_b1.id)
        assert top_b[0]["product_name"] == "Beta Exclusive Widget"
        assert Decimal(str(top_b[0]["revenue_generated"])) == Decimal("2360.00")
        assert Decimal(str(top_b[0]["units_sold"])) == Decimal("2.000")

        # Check Tenant A does NOT contain Beta's product
        res_a = await client.get(
            f"/api/v1/internal/cloud/shops/{tenant_a.id}/products/usage",
            headers=SERVICE_HEADER,
        )
        assert res_a.status_code == 200
        data_a = res_a.json()
        product_ids_a = [item["product_id"] for item in data_a["top_selling_products"]]
        assert str(prod_b1.id) not in product_ids_a


# ============================================================
# 4. EMPTY RESULT BEHAVIOR TESTS
# ============================================================

@pytest.mark.asyncio
async def test_product_usage_empty_shop(usage_test_data):
    """
    Verifies that a shop with 0 catalog products and 0 bills returns safely:
    - top_selling_products: []
    - total_distinct_products_sold: 0
    - total_catalog_products: 0
    - catalog_utilization_percent: 0.00
    """
    tenant_c = usage_test_data["tenant_c"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(
            f"/api/v1/internal/cloud/shops/{tenant_c.id}/products/usage",
            headers=SERVICE_HEADER,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["tenant_id"] == str(tenant_c.id)
        assert data["top_selling_products"] == []
        assert data["total_distinct_products_sold"] == 0
        assert data["total_catalog_products"] == 0
        assert Decimal(str(data["catalog_utilization_percent"])) == Decimal("0.00")


@pytest.mark.asyncio
async def test_product_usage_nonexistent_shop():
    """Verifies that an unknown tenant returns 404 Shop not found."""
    non_existent_id = uuid.uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(
            f"/api/v1/internal/cloud/shops/{non_existent_id}/products/usage",
            headers=SERVICE_HEADER,
        )
        assert res.status_code == 404
        assert res.json()["detail"] == "Shop not found"


# ============================================================
# 5. READ-ONLY VERIFICATION (NO MUTATIONS)
# ============================================================

@pytest.mark.asyncio
async def test_product_usage_is_strictly_read_only(usage_test_data):
    """
    Confirms that calling GET /products/usage does not modify or create
    any database records.
    """
    tenant_a = usage_test_data["tenant_a"]

    async with AsyncSessionLocal() as session:
        # Snapshot table counts before request
        bills_before = (await session.execute(select(func.count(Bill.id)))).scalar()
        items_before = (await session.execute(select(func.count(BillItem.id)))).scalar()
        prods_before = (await session.execute(select(func.count(Product.id)))).scalar()
        vars_before = (await session.execute(select(func.count(ProductVariant.id)))).scalar()
        tenants_before = (await session.execute(select(func.count(Tenant.id)))).scalar()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(
            f"/api/v1/internal/cloud/shops/{tenant_a.id}/products/usage",
            headers=SERVICE_HEADER,
        )
        assert res.status_code == 200

    async with AsyncSessionLocal() as session:
        # Verify counts are identical after request
        bills_after = (await session.execute(select(func.count(Bill.id)))).scalar()
        items_after = (await session.execute(select(func.count(BillItem.id)))).scalar()
        prods_after = (await session.execute(select(func.count(Product.id)))).scalar()
        vars_after = (await session.execute(select(func.count(ProductVariant.id)))).scalar()
        tenants_after = (await session.execute(select(func.count(Tenant.id)))).scalar()

    assert bills_after == bills_before
    assert items_after == items_before
    assert prods_after == prods_before
    assert vars_after == vars_before
    assert tenants_after == tenants_before
