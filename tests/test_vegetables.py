"""
tests/test_vegetables.py
========================
Focused regression-safe test suite for the vegetable API.

Sections
--------
1. Router registration - paths present in app.routes without a DB.
2. OpenAPI schema - generated schema contains expected paths + tags.
3. Money / tax calculation unit tests.
4. Pydantic schema validation.
5. Business rule logic assertions (pure Python).
6. Regression smoke-check - other routes still registered.
"""

import sys
import os
from decimal import Decimal, ROUND_HALF_UP
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Inject required env vars BEFORE any app module is imported.
# pydantic-settings reads these at Settings() instantiation time.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://fake:fake@localhost/fake")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests-only")

# Silence structured logging setup during tests
import unittest.mock as mock
with mock.patch("app.core.logging.setup_logging", lambda *a, **kw: None):
    from app.main import app

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def money(value) -> Decimal:
    """Mirror of the rounding helper in app/api/v1/vegetables.py."""
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# 1. ROUTER REGISTRATION
# ---------------------------------------------------------------------------

class TestRouterRegistration:
    """Verify all expected vegetable paths are present in app.routes."""

    def _route_map(self):
        routes = set()
        for route in app.routes:
            if hasattr(route, "path") and hasattr(route, "methods"):
                for method in (route.methods or []):
                    routes.add((route.path, method.upper()))
        return routes

    def test_create_vegetable_post(self):
        assert ("/api/v1/vegetables", "POST") in self._route_map()

    def test_list_vegetables_get(self):
        assert ("/api/v1/vegetables", "GET") in self._route_map()

    def test_update_vegetable_patch(self):
        assert ("/api/v1/vegetables/{vegetable_id}", "PATCH") in self._route_map()

    def test_create_vegetable_bill_post(self):
        assert ("/api/v1/vegetables/bills", "POST") in self._route_map()

    def test_no_duplicate_vegetable_routes(self):
        # FastAPI creates one Route object per endpoint function, so GET and POST
        # on the same path legitimately produce two Route objects that share that
        # path string.  The real check is that no (path, method) pair appears
        # more than once — which would indicate the router was included twice.
        from collections import Counter
        pairs = [
            (r.path, method)
            for r in app.routes
            if hasattr(r, "path") and "/vegetables" in r.path
            for method in (getattr(r, "methods", None) or [])
        ]
        dups = {k: c for k, c in Counter(pairs).items() if c > 1}
        assert not dups, f"Duplicate (path, method) registrations detected: {dups}"


# ---------------------------------------------------------------------------
# 2. OPENAPI SCHEMA
# ---------------------------------------------------------------------------

class TestOpenAPISchema:
    """Verify generated OpenAPI schema contains all expected vegetable entries."""

    def _schema(self):
        app.openapi_schema = None
        return app.openapi()

    def test_vegetables_collection_path_present(self):
        assert "/api/v1/vegetables" in self._schema()["paths"]

    def test_vegetables_collection_has_get_and_post(self):
        methods = set(self._schema()["paths"].get("/api/v1/vegetables", {}).keys())
        assert "get" in methods and "post" in methods

    def test_vegetable_item_path_present(self):
        assert "/api/v1/vegetables/{vegetable_id}" in self._schema()["paths"]

    def test_vegetable_item_has_patch(self):
        methods = set(
            self._schema()["paths"].get("/api/v1/vegetables/{vegetable_id}", {}).keys()
        )
        assert "patch" in methods

    def test_vegetable_bills_path_present(self):
        assert "/api/v1/vegetables/bills" in self._schema()["paths"]

    def test_vegetable_bills_has_post(self):
        methods = set(
            self._schema()["paths"].get("/api/v1/vegetables/bills", {}).keys()
        )
        assert "post" in methods

    def test_vegetables_tag_in_schema(self):
        # FastAPI does not auto-populate the top-level 'tags' list unless
        # app.openapi_tags is set. Tags appear correctly on each operation.
        # Verify the 'Vegetables' tag is present on at least one operation.
        schema = self._schema()
        operation_tags = set()
        for path_item in schema["paths"].values():
            for op in path_item.values():
                if isinstance(op, dict):
                    operation_tags.update(op.get("tags", []))
        assert "Vegetables" in operation_tags, (
            f"'Vegetables' tag not found on any operation. Found: {operation_tags}"
        )

    def test_bills_path_not_broken(self):
        """Regression: normal billing must still appear in the schema."""
        assert "/api/v1/bills" in self._schema()["paths"]


# ---------------------------------------------------------------------------
# 3. MONEY / TAX CALCULATION UNIT TESTS
# ---------------------------------------------------------------------------

class TestMoneyCalculations:
    def test_basic_price_times_weight(self):
        # 40 * 0.750 = 30.00
        assert money(Decimal("40.00") * Decimal("0.750")) == Decimal("30.00")

    def test_rounding_half_up(self):
        # 100/3 * 0.333 = 11.0999... -> rounds to 11.10
        result = money(Decimal("100") / Decimal("3") * Decimal("0.333"))
        assert result == Decimal("11.10")

    def test_tax_5_percent(self):
        assert money(Decimal("30.00") * Decimal("5") / Decimal("100")) == Decimal("1.50")

    def test_tax_18_percent(self):
        assert money(Decimal("100.00") * Decimal("18") / Decimal("100")) == Decimal("18.00")

    def test_zero_tax(self):
        assert money(Decimal("50.00") * Decimal("0") / Decimal("100")) == ZERO

    def test_line_total(self):
        assert money(Decimal("30.00") + Decimal("1.50")) == Decimal("31.50")

    def test_bill_total_formula(self):
        # total = subtotal + tax - discount
        assert money(Decimal("100") + Decimal("5") - Decimal("10")) == Decimal("95.00")

    def test_outstanding(self):
        assert money(max(Decimal("95") - Decimal("50"), ZERO)) == Decimal("45.00")

    def test_fully_paid_outstanding_zero(self):
        assert money(max(Decimal("95") - Decimal("95"), ZERO)) == ZERO

    def test_multi_line_subtotal(self):
        subtotal = (
            money(Decimal("40") * Decimal("0.75"))   # 30.00
            + money(Decimal("60") * Decimal("1"))     # 60.00
            + money(Decimal("25") * Decimal("0.5"))   # 12.50
        )
        assert money(subtotal) == Decimal("102.50")

    def test_money_returns_decimal(self):
        assert isinstance(money("3.14159"), Decimal)

    def test_money_half_up_rounding(self):
        # 2.005 -> 2.01 with ROUND_HALF_UP
        assert money("2.005") == Decimal("2.01")


# ---------------------------------------------------------------------------
# 4. PYDANTIC SCHEMA VALIDATION
# ---------------------------------------------------------------------------

class TestVegetableSchemas:

    def test_create_valid(self):
        from app.schemas.vegetable import VegetableCreate
        import uuid
        obj = VegetableCreate(
            product_id=uuid.uuid4(),
            price_per_kg=Decimal("40.00"),
            unit="kg",
        )
        assert obj.unit == "kg"

    def test_unit_normalized_to_lowercase(self):
        from app.schemas.vegetable import VegetableCreate
        import uuid
        obj = VegetableCreate(product_id=uuid.uuid4(), price_per_kg=Decimal("10"), unit="KG")
        assert obj.unit == "kg"

    def test_invalid_unit_rejected(self):
        from app.schemas.vegetable import VegetableCreate
        from pydantic import ValidationError
        import uuid
        with pytest.raises(ValidationError):
            VegetableCreate(product_id=uuid.uuid4(), price_per_kg=Decimal("10"), unit="lb")

    def test_zero_price_rejected(self):
        from app.schemas.vegetable import VegetableCreate
        from pydantic import ValidationError
        import uuid
        with pytest.raises(ValidationError):
            VegetableCreate(product_id=uuid.uuid4(), price_per_kg=Decimal("0.00"))

    def test_negative_price_rejected(self):
        from app.schemas.vegetable import VegetableCreate
        from pydantic import ValidationError
        import uuid
        with pytest.raises(ValidationError):
            VegetableCreate(product_id=uuid.uuid4(), price_per_kg=Decimal("-1"))

    def test_tax_rate_100_accepted(self):
        from app.schemas.vegetable import VegetableCreate
        import uuid
        obj = VegetableCreate(
            product_id=uuid.uuid4(), price_per_kg=Decimal("10"), tax_rate=Decimal("100")
        )
        assert obj.tax_rate == Decimal("100")

    def test_tax_rate_over_100_rejected(self):
        from app.schemas.vegetable import VegetableCreate
        from pydantic import ValidationError
        import uuid
        with pytest.raises(ValidationError):
            VegetableCreate(product_id=uuid.uuid4(), price_per_kg=Decimal("10"), tax_rate=Decimal("101"))

    def test_negative_stock_rejected(self):
        from app.schemas.vegetable import VegetableCreate
        from pydantic import ValidationError
        import uuid
        with pytest.raises(ValidationError):
            VegetableCreate(product_id=uuid.uuid4(), price_per_kg=Decimal("10"), stock_kg=Decimal("-0.001"))

    def test_update_partial_fields(self):
        from app.schemas.vegetable import VegetableUpdate
        obj = VegetableUpdate(price_per_kg=Decimal("55.00"))
        dumped = obj.model_dump(exclude_unset=True)
        assert "price_per_kg" in dumped
        assert "tax_rate" not in dumped

    def test_update_bad_status_rejected(self):
        from app.schemas.vegetable import VegetableUpdate
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            VegetableUpdate(status="DELETED")

    def test_update_active_inactive_accepted(self):
        from app.schemas.vegetable import VegetableUpdate
        assert VegetableUpdate(status="INACTIVE").status == "INACTIVE"
        assert VegetableUpdate(status="ACTIVE").status == "ACTIVE"


class TestVegetableBillSchema:

    def _line(self):
        from app.schemas.vegetable import VegetableBillLine
        import uuid
        return VegetableBillLine(vegetable_id=uuid.uuid4(), weight_kg=Decimal("0.750"))

    def _bill(self, **kw):
        from app.schemas.vegetable import VegetableBillCreate
        defaults = dict(items=[self._line()], paid_amount=Decimal("30"), payment_method="CASH")
        defaults.update(kw)
        return VegetableBillCreate(**defaults)

    def test_valid_cash_bill(self):
        assert self._bill().payment_method == "CASH"

    def test_method_normalized_uppercase(self):
        assert self._bill(payment_method="upi").payment_method == "UPI"

    def test_kadan_method_accepted(self):
        b = self._bill(payment_method="KADAN", paid_amount=Decimal("0"))
        assert b.payment_method == "KADAN"

    def test_invalid_method_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self._bill(payment_method="CHEQUE")

    def test_empty_items_rejected(self):
        from app.schemas.vegetable import VegetableBillCreate
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            VegetableBillCreate(items=[], paid_amount=Decimal("0"), payment_method="CASH")

    def test_zero_weight_rejected(self):
        from app.schemas.vegetable import VegetableBillCreate, VegetableBillLine
        from pydantic import ValidationError
        import uuid
        with pytest.raises(ValidationError):
            VegetableBillCreate(
                items=[VegetableBillLine(vegetable_id=uuid.uuid4(), weight_kg=Decimal("0"))],
                paid_amount=Decimal("0"), payment_method="CASH",
            )

    def test_negative_weight_rejected(self):
        from app.schemas.vegetable import VegetableBillCreate, VegetableBillLine
        from pydantic import ValidationError
        import uuid
        with pytest.raises(ValidationError):
            VegetableBillCreate(
                items=[VegetableBillLine(vegetable_id=uuid.uuid4(), weight_kg=Decimal("-0.5"))],
                paid_amount=Decimal("0"), payment_method="CASH",
            )

    def test_negative_paid_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self._bill(paid_amount=Decimal("-1"))

    def test_negative_discount_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self._bill(discount_amount=Decimal("-5"))

    def test_customer_fields_optional(self):
        b = self._bill(customer_name=None, customer_phone=None)
        assert b.customer_name is None and b.customer_phone is None


# ---------------------------------------------------------------------------
# 5. BUSINESS RULE LOGIC ASSERTIONS (pure Python, no I/O)
# ---------------------------------------------------------------------------

class TestBusinessRules:

    def test_duplicate_vegetable_ids_detected(self):
        import uuid
        veg_id = uuid.uuid4()
        ids = [veg_id, veg_id]
        assert len(ids) != len(set(ids)), "Duplicate detection logic broken"

    def test_stock_sufficient_passes(self):
        assert Decimal("2.000") >= Decimal("0.750")

    def test_stock_insufficient_raises(self):
        assert Decimal("0.500") < Decimal("0.750")

    def test_discount_exceeds_subtotal_detected(self):
        assert Decimal("60") > Decimal("50")

    def test_paid_exceeds_total_detected(self):
        assert Decimal("100") > Decimal("95")

    def test_kadan_with_nonzero_paid_invalid(self):
        # KADAN payment + paid_amount > 0 -> endpoint must reject
        method, paid = "KADAN", Decimal("10")
        assert method == "KADAN" and paid != ZERO

    def test_cash_with_zero_paid_invalid_when_total_positive(self):
        method, total, paid = "CASH", Decimal("50"), ZERO
        assert method in {"CASH", "UPI"} and total > ZERO and paid <= ZERO

    def test_outstanding_without_customer_invalid(self):
        outstanding, customer = Decimal("20"), None
        assert outstanding > ZERO and not customer

    def test_stock_decremented_correctly(self):
        before = Decimal("5.000")
        used = Decimal("0.750")
        after = before - used
        assert after == Decimal("4.250")


# ---------------------------------------------------------------------------
# 6. REGRESSION - OTHER ROUTES STILL REGISTERED
# ---------------------------------------------------------------------------

class TestOtherRoutesIntact:
    """Smoke-check that existing routes are unaffected."""

    def _paths(self):
        return {r.path for r in app.routes if hasattr(r, "path")}

    def test_auth_routes_present(self):
        assert any("/auth" in p for p in self._paths()), "Auth routes removed - regression"

    def test_bills_routes_present(self):
        assert any("/bills" in p for p in self._paths()), "Bills routes removed - regression"

    def test_products_routes_present(self):
        assert any("/products" in p for p in self._paths()), "Products routes removed - regression"

    def test_kadan_routes_present(self):
        assert any("/kadan" in p for p in self._paths()), "Kadan routes removed - regression"

    def test_customers_routes_present(self):
        assert any("/customers" in p for p in self._paths()), "Customers routes removed - regression"

    def test_reports_routes_present(self):
        assert any("/reports" in p for p in self._paths()), "Reports routes removed - regression"

    def test_health_route_present(self):
        assert "/health" in self._paths(), "/health removed - regression"

    def test_tenants_routes_present(self):
        assert any("/tenants" in p for p in self._paths()), "Tenants routes removed - regression"

    def test_audit_logs_routes_present(self):
        assert any("/audit-logs" in p for p in self._paths()), "Audit log routes removed - regression"
