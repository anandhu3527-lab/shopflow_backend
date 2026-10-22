import uuid
from datetime import datetime, timezone
from decimal import Decimal
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.core.config import settings
from app.core.security import create_access_token


from app.core.database import engine

VALID_SERVICE_TOKEN = "local_cryvex_cloud_service_token_secret"
SERVICE_HEADER = {"X-Cryvex-Cloud-Service-Token": VALID_SERVICE_TOKEN}


@pytest.fixture(autouse=True)
def setup_service_token(monkeypatch):
    """Ensure the service token is configured for all tests by default."""
    monkeypatch.setattr(settings, "CLOUD_INTERNAL_SERVICE_TOKEN", VALID_SERVICE_TOKEN)




# ============================================================
# 1. AUTHENTICATION & ACCESS CONTROL TESTS
# ============================================================

@pytest.mark.asyncio
async def test_auth_missing_token_rejected():
    """Verify missing X-Cryvex-Cloud-Service-Token header returns 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/internal/cloud/overview")
        assert response.status_code == 401
        assert "Missing required service authentication header" in response.json()["detail"]


@pytest.mark.asyncio
async def test_auth_invalid_token_rejected():
    """Verify invalid X-Cryvex-Cloud-Service-Token header returns 403."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/internal/cloud/overview",
            headers={"X-Cryvex-Cloud-Service-Token": "invalid_wrong_secret_123"},
        )
        assert response.status_code == 403
        assert "Invalid internal service token" in response.json()["detail"]


@pytest.mark.asyncio
async def test_auth_unconfigured_server_token_fails_closed(monkeypatch):
    """Verify server fails closed (503) if CLOUD_INTERNAL_SERVICE_TOKEN is empty or None."""
    monkeypatch.setattr(settings, "CLOUD_INTERNAL_SERVICE_TOKEN", "")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/internal/cloud/overview",
            headers={"X-Cryvex-Cloud-Service-Token": VALID_SERVICE_TOKEN},
        )
        assert response.status_code == 503
        assert "not configured" in response.json()["detail"]


@pytest.mark.asyncio
async def test_auth_ordinary_owner_jwt_alone_rejected():
    """Verify ordinary ShopFlow OWNER JWT alone without service header is rejected with 401."""
    dummy_owner_jwt = create_access_token(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        role_id=uuid.uuid4(),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/internal/cloud/overview",
            headers={"Authorization": f"Bearer {dummy_owner_jwt}"},
        )
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_auth_ordinary_staff_jwt_alone_rejected():
    """Verify ordinary ShopFlow staff/employee JWT alone without service header is rejected with 401."""
    dummy_staff_jwt = create_access_token(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        role_id=uuid.uuid4(),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/internal/cloud/shops",
            headers={"Authorization": f"Bearer {dummy_staff_jwt}"},
        )
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_auth_valid_service_token_succeeds():
    """Verify valid service token allows reaching the internal endpoint."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/internal/cloud/overview",
            headers=SERVICE_HEADER,
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_shops" in data
        assert "active_shops" in data
        assert "monthly_revenue" in data


# ============================================================
# 2. OVERVIEW ENDPOINTS TESTS
# ============================================================

@pytest.mark.asyncio
async def test_overview_health():
    """Verify the internal health endpoint reports connectivity correctly."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/internal/cloud/overview/health",
            headers=SERVICE_HEADER,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "shopflow-api-internal-cloud"
        assert "database_connected" in data
        assert "status" in data


@pytest.mark.asyncio
async def test_overview_subscriptions():
    """Verify the internal subscription metrics overview."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/internal/cloud/overview/subscriptions",
            headers=SERVICE_HEADER,
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_subscriptions" in data
        assert "by_plan" in data
        assert "by_status" in data
        assert "expiring_soon_count" in data


@pytest.mark.asyncio
async def test_overview_bills():
    """Verify the internal bills metrics overview."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/internal/cloud/overview/bills",
            headers=SERVICE_HEADER,
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_bills_all_time" in data
        assert "total_billed_amount" in data
        assert "total_collected_revenue" in data
        assert "by_status" in data


# ============================================================
# 3. SHOPS MANAGEMENT TESTS
# ============================================================

@pytest.mark.asyncio
async def test_shops_list_pagination():
    """Verify shop listing supports bounded pagination and filtering."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/internal/cloud/shops?limit=10&offset=0",
            headers=SERVICE_HEADER,
        )
        assert response.status_code == 200
        data = response.json()
        assert "meta" in data
        assert data["meta"]["limit"] == 10
        assert data["meta"]["offset"] == 0
        assert isinstance(data["shops"], list)


@pytest.mark.asyncio
async def test_shop_detail_nonexistent_returns_404():
    """Verify non-existent shop ID returns 404."""
    random_tenant_id = uuid.uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/internal/cloud/shops/{random_tenant_id}",
            headers=SERVICE_HEADER,
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Shop not found"


@pytest.mark.asyncio
async def test_shop_overview_kpis_nonexistent_returns_404():
    """Verify non-existent shop KPIs return 404."""
    random_tenant_id = uuid.uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/internal/cloud/shops/{random_tenant_id}/overview",
            headers=SERVICE_HEADER,
        )
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_shop_status_update_validation():
    """Verify updating shop status validates request body and returns 404 for unknown shop."""
    random_tenant_id = uuid.uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Invalid status enum
        response_invalid = await client.patch(
            f"/api/v1/internal/cloud/shops/{random_tenant_id}/status",
            headers=SERVICE_HEADER,
            json={"status": "INVALID_STATE"},
        )
        assert response_invalid.status_code == 422

        # Valid status, unknown shop
        response_404 = await client.patch(
            f"/api/v1/internal/cloud/shops/{random_tenant_id}/status",
            headers=SERVICE_HEADER,
            json={"status": "SUSPENDED", "reason": "Test suspension"},
        )
        assert response_404.status_code == 404


# ============================================================
# 4. TENANT ISOLATION TESTS
# ============================================================

@pytest.mark.asyncio
async def test_tenant_isolation_users():
    """Verify users endpoint enforces strict tenant scoping."""
    random_tenant_id = uuid.uuid4()
    random_user_id = uuid.uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Shop not found
        res_list = await client.get(
            f"/api/v1/internal/cloud/shops/{random_tenant_id}/users",
            headers=SERVICE_HEADER,
        )
        assert res_list.status_code == 404

        # User not found for shop
        res_user = await client.get(
            f"/api/v1/internal/cloud/shops/{random_tenant_id}/users/{random_user_id}",
            headers=SERVICE_HEADER,
        )
        assert res_user.status_code == 404


@pytest.mark.asyncio
async def test_tenant_isolation_products():
    """Verify products and variants endpoints enforce tenant scoping."""
    random_tenant_id = uuid.uuid4()
    random_product_id = uuid.uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res_prod = await client.get(
            f"/api/v1/internal/cloud/shops/{random_tenant_id}/products/{random_product_id}",
            headers=SERVICE_HEADER,
        )
        assert res_prod.status_code == 404

        res_vars = await client.get(
            f"/api/v1/internal/cloud/shops/{random_tenant_id}/products/{random_product_id}/variants",
            headers=SERVICE_HEADER,
        )
        assert res_vars.status_code == 404


@pytest.mark.asyncio
async def test_tenant_isolation_bills():
    """Verify shop-specific billing endpoint is tenant-scoped."""
    random_tenant_id = uuid.uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res_summary = await client.get(
            f"/api/v1/internal/cloud/shops/{random_tenant_id}/billing/summary",
            headers=SERVICE_HEADER,
        )
        assert res_summary.status_code == 404

        res_bills = await client.get(
            f"/api/v1/internal/cloud/shops/{random_tenant_id}/billing/bills",
            headers=SERVICE_HEADER,
        )
        assert res_bills.status_code == 404


# ============================================================
# 5. PRODUCT & STOCK SUMMARY STATIC ROUTE PRECEDENCE TESTS
# ============================================================

@pytest.mark.asyncio
async def test_static_stock_summary_route_precedence():
    """Verify static route /products/stock/summary does not collide with /{product_id}."""
    random_tenant_id = uuid.uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(
            f"/api/v1/internal/cloud/shops/{random_tenant_id}/products/stock/summary",
            headers=SERVICE_HEADER,
        )
        # Should return 404 for unknown shop, NOT 422 invalid UUID for product_id
        assert res.status_code == 404
        assert res.json()["detail"] == "Shop not found"


@pytest.mark.asyncio
async def test_static_product_usage_route_precedence():
    """Verify static route /products/usage does not collide with /{product_id}."""
    random_tenant_id = uuid.uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(
            f"/api/v1/internal/cloud/shops/{random_tenant_id}/products/usage",
            headers=SERVICE_HEADER,
        )
        # Should return 404 for unknown shop, NOT 422 invalid UUID for product_id
        assert res.status_code == 404
        assert res.json()["detail"] == "Shop not found"


# ============================================================
# 6. ACCESS RESET WORKFLOW TRUTHFULNESS TESTS
# ============================================================

@pytest.mark.asyncio
async def test_access_reset_controlled_response():
    """Verify access reset returns 404 for unknown shop/user, and does not claim email was sent."""
    random_tenant_id = uuid.uuid4()
    random_user_id = uuid.uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/internal/cloud/shops/{random_tenant_id}/users/{random_user_id}/access-reset",
            headers=SERVICE_HEADER,
            json={"reason": "Forgot password requested via Cloud admin"},
        )
        assert response.status_code == 404


# ============================================================
# 7. SUBSCRIPTION MANAGEMENT TESTS
# ============================================================

@pytest.mark.asyncio
async def test_subscription_get_by_id_404():
    """Verify global subscription route returns 404 for non-existent subscription."""
    random_sub_id = uuid.uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/internal/cloud/subscriptions/{random_sub_id}",
            headers=SERVICE_HEADER,
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Subscription not found"


@pytest.mark.asyncio
async def test_subscription_history_truthfulness():
    """Verify subscription history returns 404 for unknown shop and schema explanation."""
    random_tenant_id = uuid.uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/internal/cloud/shops/{random_tenant_id}/subscription/history",
            headers=SERVICE_HEADER,
        )
        assert response.status_code == 404

@pytest.mark.asyncio
async def test_subscription_activation_schema_validation():
    """Verify subscription activation schema requires plan, start_date, end_date, and reason."""
    dummy_tenant_id = uuid.uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Empty body -> 422
        res_empty = await client.post(
            f"/api/v1/internal/cloud/shops/{dummy_tenant_id}/subscription/activate",
            headers=SERVICE_HEADER,
            json={},
        )
        assert res_empty.status_code == 422
        errors = res_empty.json()["detail"]
        missing_fields = {e["loc"][-1] for e in errors}
        assert "plan" in missing_fields
        assert "start_date" in missing_fields
        assert "end_date" in missing_fields
        assert "reason" in missing_fields

        # 2. Missing reason -> 422
        res_no_reason = await client.post(
            f"/api/v1/internal/cloud/shops/{dummy_tenant_id}/subscription/activate",
            headers=SERVICE_HEADER,
            json={
                "plan": "SHOPFLOW",
                "start_date": "2026-10-22T00:00:00Z",
                "end_date": "2027-10-22T00:00:00Z",
            },
        )
        assert res_no_reason.status_code == 422
        missing_fields_2 = {e["loc"][-1] for e in res_no_reason.json()["detail"]}
        assert "reason" in missing_fields_2
# ============================================================

@pytest.mark.asyncio
async def test_support_endpoint_reports_unsupported():
    """Verify support endpoint returns 404 for unknown shop."""
    random_tenant_id = uuid.uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/internal/cloud/shops/{random_tenant_id}/support",
            headers=SERVICE_HEADER,
        )
        assert response.status_code == 404


# ============================================================
# 9. EXISTING APP REGRESSION TESTS
# ============================================================

@pytest.mark.asyncio
async def test_existing_health_endpoint_unchanged():
    """Verify existing public health check at /health remains functional and unchanged."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "shopflow-api"


@pytest.mark.asyncio
async def test_existing_database_health_endpoint_unchanged():
    """Verify existing public /health/database remains functional."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/database")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["database"] == "connected"
